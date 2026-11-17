"""Hosting support: load the card catalogue on first start, and keep it topped up with new sets."""
import os, gzip, shutil, sqlite3, tempfile, threading, time, pathlib, requests
from .db import conn, DATA

COLS = "id,name,set_name,number,rarity,image_url,market,prices_json,emb,price_day"

def _fetch(src, dest):
    if src.startswith(("http://", "https://")):
        with requests.get(src, stream=True, timeout=300, headers={"User-Agent": "CardTrackerPersonal/0.1"}) as r:
            r.raise_for_status()
            with open(dest, "wb") as f: shutil.copyfileobj(_Reader(r), f)
    else:
        shutil.copyfile(src.replace("file://", ""), dest)

class _Reader:
    """Adapt requests' chunk iterator to a file-like object for copyfileobj."""
    def __init__(self, r): self.it = r.iter_content(1 << 20); self.buf = b""
    def read(self, n=-1):
        if not self.buf:
            self.buf = next(self.it, b"")
        out, self.buf = self.buf, b""
        return out

def ensure_catalog():
    """If the catalogue is empty and CATALOG_URL is set, import it. Never touches existing cards or any user data."""
    db = conn()
    try:
        if db.execute("SELECT COUNT(*) FROM cards").fetchone()[0] > 0: return "already loaded"
        url = os.environ.get("CATALOG_URL")
        if not url: return "no CATALOG_URL set"
        print("Loading card catalogue from", url, flush=True)
        with tempfile.TemporaryDirectory(dir=DATA) as d:
            gz, raw = pathlib.Path(d) / "c.db.gz", pathlib.Path(d) / "c.db"
            _fetch(url, gz)
            with gzip.open(gz, "rb") as a, open(raw, "wb") as b: shutil.copyfileobj(a, b)
            db.execute("ATTACH DATABASE ? AS cat", (str(raw),))
            db.execute(f"INSERT OR IGNORE INTO main.cards({COLS}) SELECT {COLS} FROM cat.cards")
            db.commit(); db.execute("DETACH DATABASE cat")
        n = db.execute("SELECT COUNT(*) FROM cards").fetchone()[0]
        print("Catalogue loaded:", n, "cards", flush=True); return f"loaded {n}"
    finally: db.close()

def start_topup(every_hours=24, first_delay=300):
    """Background: pull any new cards/sets from the Pokemon TCG API (resumable, tolerant of its outages)."""
    def loop():
        time.sleep(first_delay)
        while True:
            try:
                from . import ingest
                ingest.main()
            except BaseException as e:           # ingest exits via SystemExit when the API is down; try again later
                print("catalogue top-up paused:", repr(e)[:120], flush=True)
            time.sleep(every_hours * 3600)
    threading.Thread(target=loop, daemon=True).start()
