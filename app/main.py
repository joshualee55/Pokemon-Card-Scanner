import io
from fastapi import FastAPI, UploadFile, File, HTTPException
from pydantic import BaseModel
from PIL import Image
from .db import conn
from .matcher import Index
from .condition import estimate, MULT

import pathlib
from fastapi.staticfiles import StaticFiles
from fastapi import APIRouter
app = FastAPI(title="Card Tracker")
INDEX = Index()

# Optional password: set APP_PASSWORD to require a login (browser shows a sign-in box).
import os, base64, secrets
from fastapi import Request
from fastapi.responses import Response
@app.middleware("http")
async def password_gate(request: Request, call_next):
    pw = os.environ.get("APP_PASSWORD")
    if pw:
        sent = request.headers.get("authorization", "")
        ok = False
        if sent.startswith("Basic "):
            try: ok = secrets.compare_digest(base64.b64decode(sent[6:]).decode().partition(":")[2], pw)
            except Exception: pass
        if not ok:
            return Response("Login required", 401, headers={"WWW-Authenticate": 'Basic realm="Card Tracker"'})
    return await call_next(request)
api = APIRouter(prefix="/api")

def card_dict(r, cond="NM"):
    m = r["market"]
    return {"id": r["id"], "name": r["name"], "set": r["set_name"], "number": r["number"],
            "rarity": r["rarity"], "image": r["image_url"], "market": m,
            "adjusted_value": round(m * MULT[cond], 2) if m else None}

IMG_DIR = pathlib.Path(__file__).parent.parent / "data" / "images"

def reference(row):
    """Fetch (and cache on disk) the matched card's official image for comparison."""
    f = IMG_DIR / (row["id"] + ".png")
    try:
        IMG_DIR.mkdir(parents=True, exist_ok=True)
        if not f.exists():
            import requests
            f.write_bytes(requests.get(row["image_url"], timeout=15).content)
        return Image.open(f)
    except Exception:
        return None

@api.post("/scan")
async def scan(file: UploadFile = File(...)):
    img = Image.open(io.BytesIO(await file.read()))
    idx = INDEX.load(conn())
    if not idx.rows: raise HTTPException(503, "Run `python -m app.ingest` first")
    res = idx.search(img, k=5, w_fp=0.0)
    cond = estimate(img, reference(res[0][0]))
    return {"condition": cond,
            "matches": [{**card_dict(r, cond["condition"]), "confidence": round(s, 3)} for r, s in res]}

@api.get("/search")
def search(q: str, limit: int = 20):
    rows = conn().execute("SELECT * FROM cards WHERE name LIKE ? LIMIT ?", (f"%{q}%", limit)).fetchall()
    return [card_dict(r) for r in rows]

class Add(BaseModel):
    card_id: str; condition: str = "NM"; qty: int = 1

@api.post("/collection")
def add(a: Add):
    check_cond(a.condition); db = conn(); db.execute("INSERT INTO collection(card_id,condition,qty) VALUES(?,?,?)", (a.card_id, a.condition, a.qty)); db.commit()
    return {"ok": True}

@api.get("/collection")
def collection():
    rows = conn().execute("SELECT c.*, k.id entry_id, k.condition cond, k.qty FROM collection k JOIN cards c ON c.id=k.card_id").fetchall()
    items = [{**card_dict(r, r["cond"]), "entry_id": r["entry_id"], "condition": r["cond"], "qty": r["qty"]} for r in rows]
    return {"total_value": round(sum((i["adjusted_value"] or 0) * i["qty"] for i in items), 2), "items": items}

class Edit(BaseModel):
    condition: str | None = None; qty: int | None = None

def check_cond(c):
    if c is not None and c not in MULT: raise HTTPException(422, f"condition must be one of {list(MULT)}")

@api.patch("/collection/{entry_id}")
def edit(entry_id: int, e: Edit):
    check_cond(e.condition); db = conn()
    if e.condition: db.execute("UPDATE collection SET condition=? WHERE id=?", (e.condition, entry_id))
    if e.qty: db.execute("UPDATE collection SET qty=? WHERE id=?", (max(1, e.qty), entry_id))
    db.commit(); return {"ok": True}

@api.delete("/collection/{entry_id}")
def remove(entry_id: int):
    db = conn(); db.execute("DELETE FROM collection WHERE id=?", (entry_id,)); db.commit(); return {"ok": True}

@api.get("/meta")
def meta(): return {"conditions": [{"code": k, "multiplier": v, "label": L} for (k, v), L in zip(MULT.items(),
    ["Near Mint", "Lightly Played", "Moderately Played", "Heavily Played", "Damaged"])]}

class Side(BaseModel):
    card_id: str; condition: str = "NM"; qty: int = 1
class Trade(BaseModel):
    give: list[Side]; get: list[Side]

@api.post("/trade")
def trade(t: Trade):
    db = conn()
    def total(side):
        out, s = [], 0.0
        for x in side:
            r = db.execute("SELECT * FROM cards WHERE id=?", (x.card_id,)).fetchone()
            if not r: raise HTTPException(404, x.card_id)
            v = (r["market"] or 0) * MULT[x.condition] * x.qty; s += v
            out.append({"name": r["name"], "condition": x.condition, "qty": x.qty, "value": round(v, 2)})
        return out, round(s, 2)
    g, gt = total(t.give); r_, rt = total(t.get)
    diff = round(rt - gt, 2)
    verdict = "fair" if abs(diff) <= 0.05 * max(gt, rt, 1) else ("you win" if diff > 0 else "you lose")
    return {"give": g, "give_total": gt, "get": r_, "get_total": rt, "difference": diff, "verdict": verdict}

app.include_router(api)
app.mount("/", StaticFiles(directory=pathlib.Path(__file__).parent.parent / "web", html=True), name="web")
