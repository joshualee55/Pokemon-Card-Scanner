"""Daily TCGplayer prices + history from TCGCSV (https://tcgcsv.com) - free, and its FAQ explicitly welcomes
scripts that identify themselves. Each day has one small archive; we read only the rows for cards people
track. Every history point is dated by the archive day it came from."""
import os, re, json, time, tempfile, pathlib, threading, datetime, requests
from .db import conn
from . import prices as P
from . import mapping

UA = {"User-Agent": "CardTrackerPersonal/0.1 (personal collection tracker)"}
BASE = "https://tcgcsv.com"
DAILY_DAYS = 14                                         # every day for the last two weeks...
WEEKS = int(os.environ.get("BACKFILL_WEEKS", "26"))     # ...then one point a week back this far
EARLIEST = datetime.date(2024, 2, 8)                    # first day TCGCSV archived
_lock = threading.Lock()

_SUB = {v.lower(): k for k, v in P.LABELS.items()}      # "reverse holofoil" -> reverseHolofoil
def code_for(sub):
    k = (sub or "").strip().lower()
    if k in _SUB: return _SUB[k]
    w = re.split(r"[\s/-]+", sub.strip()); return w[0].lower() + "".join(x.capitalize() for x in w[1:])

def schedule(today=None):
    t = today or datetime.datetime.now(datetime.timezone.utc).date()
    days = [t - datetime.timedelta(i) for i in range(DAILY_DAYS)]
    days += [t - datetime.timedelta(DAILY_DAYS + 7 * k) for k in range(max(0, WEEKS - 1))]
    return [d for d in days if d >= EARLIEST]

def _product_from_redirect(card_id):
    """TCGplayer product number for a pokemontcg.io card id. Returns int, None (no link), or raises on network error."""
    if not P._ID.match(card_id): return None
    r = requests.get(f"https://prices.pokemontcg.io/tcgplayer/{card_id}", headers=UA, allow_redirects=False, timeout=15)
    if r.status_code >= 500: raise requests.RequestException(f"link service error {r.status_code}")   # temporary: never remember it
    m = re.search(r"/product/(\d+)", r.headers.get("location", ""))
    return int(m.group(1)) if m else None                                                            # 404 etc: genuinely no link

def resolve_products(db, ids, limit=40):
    """Make sure each card has a TCGplayer product. 1) match by set+number+name (mapping.py), 2) the pokemontcg.io
    link as a backup. Temporary errors are retried later and never remembered as 'no link'."""
    mapping.build(db)                                           # cheap; fills every card it can match
    mapped = {r[0]: r[1] for r in db.execute("SELECT card_id, product_id FROM card_product")}
    checked = {r[0]: r[1] or 0 for r in db.execute("SELECT card_id, checked FROM card_product")}
    n = 0
    for cid in ids:
        if mapped.get(cid): continue                            # already have a product
        if cid in mapped and time.time() - checked[cid] < 86400: continue    # confirmed 'no link' within the last day
        if n >= limit: break
        try: pid = _product_from_redirect(cid)
        except requests.RequestException: continue              # temporary: try again next time, don't cache
        db.execute("INSERT OR REPLACE INTO card_product(card_id, product_id, group_id, checked) VALUES(?,?,NULL,?)", (cid, pid, time.time()))
        db.commit(); n += 1; time.sleep(0.3)

def fetch_day(day, want):
    """-> ('ok', {product_id: {'group': gid, 'prices': {variant: {market, low, mid}}}}) | ('missing', None) | ('error', None)"""
    import py7zr
    url = f"{BASE}/archive/tcgplayer/prices-{day.isoformat()}.ppmd.7z"
    try:
        r = requests.get(url, headers=UA, timeout=120)
        if r.status_code == 404: return "missing", None
        r.raise_for_status()
        out = {}
        with tempfile.TemporaryDirectory() as d:
            f = pathlib.Path(d) / "a.7z"; f.write_bytes(r.content)
            with py7zr.SevenZipFile(f) as z:
                names = [n for n in z.getnames() if re.search(r"/3/\d+/prices$", n)]    # category 3 = Pokemon
                z.extract(path=d, targets=names)
            for pf in pathlib.Path(d).rglob("prices"):
                if pf.parent.parent.name != "3": continue
                gid = int(pf.parent.name)
                for row in json.loads(pf.read_text()).get("results", []):
                    if row["productId"] in want and row.get("marketPrice") is not None:
                        e = out.setdefault(row["productId"], {"group": gid, "prices": {}})
                        e["prices"][code_for(row["subTypeName"])] = {"market": row["marketPrice"], "low": row.get("lowPrice"), "mid": row.get("midPrice")}
        return "ok", out
    except Exception:
        return "error", None

def _apply_current(db, cid, day, info):
    cur = db.execute("SELECT price_day FROM cards WHERE id=?", (cid,)).fetchone()
    if cur is None or (cur["price_day"] and cur["price_day"] > day): return     # keep the newer price we already have
    pr = {v: d for v, d in info["prices"].items()}
    db.execute("UPDATE cards SET prices_json=?, market=?, price_day=? WHERE id=?",
               (json.dumps(pr), max(d["market"] for d in pr.values()), day, cid))

def sync(max_archives=6, only=None):
    """Fetch up to max_archives missing days for tracked cards. Returns {'done': n, 'errors': n}."""
    if not _lock.acquire(blocking=False): return {"done": 0, "errors": 0, "busy": True}
    db = conn(); res = {"done": 0, "errors": 0}
    try:
        ids = list(only) if only else P.tracked_ids()
        resolve_products(db, ids)
        prod = {r["card_id"]: r["product_id"] for r in db.execute("SELECT card_id, product_id FROM card_product WHERE product_id IS NOT NULL") if r["card_id"] in ids}
        got_data = set()
        for day in sorted(schedule(), reverse=True):                                  # newest first
            if res["done"] >= max_archives: break
            ds = day.isoformat()
            need = [c for c in prod if not db.execute("SELECT 1 FROM tcg_checked WHERE day=? AND card_id=?", (ds, c)).fetchone()]
            if not need: continue
            status, got = fetch_day(day, {prod[c] for c in need})
            if status == "error": res["errors"] += 1; continue
            if status == "missing": continue                                           # not published (yet)
            for c in need:
                info = got.get(prod[c])
                if info:
                    for v, d in info["prices"].items():
                        db.execute("INSERT OR REPLACE INTO price_history(card_id,variant,day,market) VALUES(?,?,?,?)", (c, v, ds, d["market"]))
                    db.execute("UPDATE card_product SET group_id=? WHERE card_id=?", (info["group"], c))
                    _apply_current(db, c, ds, info); got_data.add(c)
                db.execute("INSERT OR IGNORE INTO tcg_checked VALUES(?,?)", (ds, c))
            db.commit(); res["done"] += 1; time.sleep(1)
        for c in got_data:     # TCGCSV is now this card's history: drop leftover points from the old, stale feed
            db.execute("DELETE FROM price_history WHERE card_id=? AND day NOT IN (SELECT day FROM tcg_checked WHERE card_id=?)", (c, c))
        db.commit()
    finally:
        db.close(); _lock.release()
    return res

def refresh_all_current():
    """Update the CURRENT price of every matched card from the newest published day (one ~4 MB download).
    Fixes cards whose old price feed is stale or missing (e.g. the newest sets). No history is stored here."""
    if not _lock.acquire(blocking=False): return 0
    db = conn()
    try:
        prod = {r["card_id"]: r["product_id"] for r in db.execute("SELECT card_id, product_id FROM card_product WHERE product_id IS NOT NULL")}
        if not prod: return 0
        today = datetime.datetime.now(datetime.timezone.utc).date()
        for back in range(0, 4):                                   # newest published day: today, else yesterday...
            day = today - datetime.timedelta(back); ds = day.isoformat()
            if P.get_meta("all_current_day") == ds: return 0         # already up to date
            status, got = fetch_day(day, set(prod.values()))
            if status == "ok": break
        else: return 0
        n = 0
        for cid, pid in prod.items():
            info = got.get(pid)
            if info: _apply_current(db, cid, ds, info); n += 1
        db.commit(); P.set_meta("all_current_day", ds); return n
    finally:
        db.close(); _lock.release()

def sync_all(only=None):
    tot = {"done": 0, "errors": 0}
    while True:
        r = sync(6, only)
        tot["done"] += r["done"]; tot["errors"] += r["errors"]
        if r.get("busy"): tot["busy"] = True; return tot
        if r["done"] == 0: return tot
        P.set_meta("last_refresh", time.time())

def pending(card_id):
    """True while this card still has scheduled days to fetch (or hasn't been looked up yet)."""
    db = conn()
    try:
        row = db.execute("SELECT product_id FROM card_product WHERE card_id=?", (card_id,)).fetchone()
        if row is None: return True
        if row[0] is None: return False
        done = {r[0] for r in db.execute("SELECT day FROM tcg_checked WHERE card_id=?", (card_id,))}
        today = datetime.datetime.now(datetime.timezone.utc).date()
        return any(d.isoformat() not in done for d in schedule() if d != today)       # today's archive isn't out until evening
    finally: db.close()

_kicked = set()
def no_link(card_id):
    db = conn()
    try:
        r = db.execute("SELECT product_id FROM card_product WHERE card_id=?", (card_id,)).fetchone()
        return r is not None and r[0] is None
    finally: db.close()

def kick(card_id):
    """Start fetching one card's history in the background (non-blocking; waits its turn if a sync is running)."""
    if card_id in _kicked: return
    _kicked.add(card_id)
    def run():
        try:
            for _ in range(120):
                if not sync_all([card_id]).get("busy"): break
                time.sleep(5)
        finally: _kicked.discard(card_id)
    threading.Thread(target=run, daemon=True).start()
