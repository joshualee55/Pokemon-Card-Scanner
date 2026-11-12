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

import os, sqlite3
from fastapi import Request
from fastapi.responses import JSONResponse
from . import auth

PUBLIC = {"/api/signup", "/api/login", "/api/logout", "/api/me", "/api/meta"}

@app.middleware("http")
async def auth_gate(request: Request, call_next):
    tok = request.cookies.get("session")
    request.state.user = auth.user_for_token(tok) if tok else None
    path = request.url.path
    if path.startswith("/api/") and path not in PUBLIC and not request.state.user:
        return JSONResponse({"detail": "Please sign in"}, status_code=401)
    return await call_next(request)

def uid(request: Request) -> int: return request.state.user["id"]
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
def add(a: Add, request: Request):
    check_cond(a.condition); db = conn()
    if not db.execute("SELECT 1 FROM cards WHERE id=?", (a.card_id,)).fetchone(): raise HTTPException(404, "Unknown card")
    db.execute("INSERT INTO collection(card_id,condition,qty,user_id) VALUES(?,?,?,?)", (a.card_id, a.condition, max(1, a.qty), uid(request))); db.commit()
    return {"ok": True}

@api.get("/collection")
def collection(request: Request):
    rows = conn().execute("SELECT c.*, k.id entry_id, k.condition cond, k.qty FROM collection k JOIN cards c ON c.id=k.card_id WHERE k.user_id=?", (uid(request),)).fetchall()
    items = [{**card_dict(r, r["cond"]), "entry_id": r["entry_id"], "condition": r["cond"], "qty": r["qty"]} for r in rows]
    return {"total_value": round(sum((i["adjusted_value"] or 0) * i["qty"] for i in items), 2), "items": items}

class Edit(BaseModel):
    condition: str | None = None; qty: int | None = None

def check_cond(c):
    if c is not None and c not in MULT: raise HTTPException(422, f"condition must be one of {list(MULT)}")

@api.patch("/collection/{entry_id}")
def edit(entry_id: int, e: Edit, request: Request):
    check_cond(e.condition); db = conn(); me_ = uid(request)
    if not db.execute("SELECT 1 FROM collection WHERE id=? AND user_id=?", (entry_id, me_)).fetchone(): raise HTTPException(404, "Not found")
    if e.condition: db.execute("UPDATE collection SET condition=? WHERE id=? AND user_id=?", (e.condition, entry_id, me_))
    if e.qty: db.execute("UPDATE collection SET qty=? WHERE id=? AND user_id=?", (max(1, e.qty), entry_id, me_))
    db.commit(); return {"ok": True}

@api.delete("/collection/{entry_id}")
def remove(entry_id: int, request: Request):
    db = conn(); db.execute("DELETE FROM collection WHERE id=? AND user_id=?", (entry_id, uid(request))); db.commit(); return {"ok": True}

class Creds(BaseModel):
    username: str; password: str; invite: str = ""

def _client(request): return (request.headers.get("cf-connecting-ip") or (request.client.host if request.client else "?"))

def _cookie(request, resp, token):
    https = request.headers.get("x-forwarded-proto") == "https" or request.url.scheme == "https"
    resp.set_cookie("session", token, httponly=True, samesite="lax", secure=https, max_age=auth.SESSION_DAYS * 86400)

@api.post("/signup")
def signup(c: Creds, request: Request):
    code = os.environ.get("SIGNUP_CODE")
    if code and c.invite.strip() != code: raise HTTPException(403, "Wrong invite code")
    if auth.throttled("signup:" + _client(request)): raise HTTPException(429, "Too many attempts, try later")
    if (e := auth.check_new(c.username, c.password)): raise HTTPException(422, e)
    if auth.user_count() >= auth.MAX_USERS: raise HTTPException(403, "Sorry, this app is full")
    auth.note_fail("signup:" + _client(request))          # also caps signup spam
    try: user_id = auth.create_user(c.username, c.password)
    except sqlite3.IntegrityError: raise HTTPException(409, "That username is taken")
    resp = JSONResponse({"user": {"id": user_id, "username": c.username}})
    _cookie(request, resp, auth.new_session(user_id)); return resp

@api.post("/login")
def login(c: Creds, request: Request):
    key = "login:" + _client(request) + ":" + c.username.lower()
    if auth.throttled(key): raise HTTPException(429, "Too many attempts, wait 15 minutes")
    user_id = auth.login(c.username, c.password)
    if user_id is None:
        auth.note_fail(key); raise HTTPException(401, "Wrong username or password")
    resp = JSONResponse({"user": {"id": user_id, "username": c.username}})
    _cookie(request, resp, auth.new_session(user_id)); return resp

@api.post("/logout")
def logout(request: Request):
    tok = request.cookies.get("session")
    if tok: auth.end_session(tok)
    resp = JSONResponse({"ok": True}); resp.delete_cookie("session"); return resp

@api.get("/me")
def me(request: Request): return {"user": request.state.user}

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
