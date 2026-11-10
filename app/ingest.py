"""Pull card catalogue + prices from the Pokemon TCG API into SQLite and fingerprint images.
Usage: python -m app.ingest [max_cards]   (set POKEMONTCG_API_KEY for higher rate limits)"""
import os, sys, time, io, json, requests
from concurrent.futures import ThreadPoolExecutor
from PIL import Image
from .db import conn
from .matcher import fingerprint, to_blob, embed_many

API = "https://api.pokemontcg.io/v2/cards"
PAGE = 25   # deep pages 500/502 with larger sizes
HDR = {"X-Api-Key": os.environ["POKEMONTCG_API_KEY"]} if os.environ.get("POKEMONTCG_API_KEY") else {}

def best_price(tcg):
    p = (tcg or {}).get("prices") or {}
    vals = [v.get("market") for v in p.values() if v.get("market")]
    return max(vals) if vals else None

def load_img(url):
    for i in range(3):
        try:
            r = requests.get(url, timeout=30); r.raise_for_status()
            return Image.open(io.BytesIO(r.content)).convert("RGB")
        except Exception as e:
            time.sleep(1 + i)
    print("img fail", url); return None

def get_page(page, tries=8):
    for i in range(tries):
        try:
            r = requests.get(API, headers=HDR, timeout=90, params={
                "page": page, "pageSize": PAGE,
                "select": "id,name,number,rarity,set,images,tcgplayer"})
            r.raise_for_status()
            return r.json()["data"]
        except Exception as e:
            print("retry", page, e); time.sleep(min(30, 2 ** i))
    raise SystemExit("API unavailable, rerun later (it resumes; INSERT OR REPLACE)")

def main(limit=None):
    db, done = conn(), 0
    have = db.execute("SELECT COUNT(*) FROM cards WHERE emb IS NOT NULL").fetchone()[0]
    page = max(1, have // PAGE - 2)          # resume near where we stopped
    while True:
        data = get_page(page)
        if not data: break
        known = {r[0] for r in db.execute("SELECT id FROM cards WHERE emb IS NOT NULL")}
        for c in data:                                       # always refresh prices
            if c["id"] in known:
                db.execute("UPDATE cards SET market=?, prices_json=? WHERE id=?", (
                    best_price(c.get("tcgplayer")), json.dumps((c.get("tcgplayer") or {}).get("prices")), c["id"]))
        todo = [c for c in data if c["id"] not in known]     # resumable: skip finished cards
        with ThreadPoolExecutor(12) as ex:
            imgs = list(ex.map(lambda c: load_img(c["images"]["small"]), todo))
        pairs = [(c, im) for c, im in zip(todo, imgs) if im is not None]
        embs = embed_many([im for _, im in pairs]) if pairs else []
        for (c, im), e in zip(pairs, embs):
            h = to_blob(fingerprint(im))
            db.execute("INSERT OR REPLACE INTO cards VALUES(?,?,?,?,?,?,?,?,?,?)", (
                c["id"], c["name"], c["set"]["name"], c["number"], c.get("rarity"),
                c["images"]["small"], best_price(c.get("tcgplayer")),
                json.dumps((c.get("tcgplayer") or {}).get("prices")), h, to_blob(e)))
        db.commit(); done += len(data); print("ingested", done, flush=True)
        if limit and done >= limit: break
        page += 1

if __name__ == "__main__":
    main(int(sys.argv[1]) if len(sys.argv) > 1 else None)
