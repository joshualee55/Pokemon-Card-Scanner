"""Price snapshots. Every point is stamped with the date the *source* says the price is from
(tcgplayer.updatedAt), so a chart never pretends a stale price is fresh."""
import os, re, json, time, threading, datetime, requests
from .db import conn

API = "https://api.pokemontcg.io/v2/cards"
HDR = {"X-Api-Key": os.environ["POKEMONTCG_API_KEY"]} if os.environ.get("POKEMONTCG_API_KEY") else {}
_ID = re.compile(r"^[A-Za-z0-9._-]{1,40}$")

def best_price(tcg):
    p = (tcg or {}).get("prices") or {}
    vals = [v.get("market") for v in p.values() if v.get("market")]
    return max(vals) if vals else None          # highest variant's market price

def day_of(tcg):
    try: return datetime.datetime.strptime((tcg or {}).get("updatedAt", ""), "%Y/%m/%d").strftime("%Y-%m-%d")
    except ValueError: return None

VARIANT_ORDER = ["normal", "holofoil", "unlimitedHolofoil", "1stEditionNormal", "1stEditionHolofoil", "reverseHolofoil"]
LABELS = {"normal": "Normal", "holofoil": "Holofoil", "reverseHolofoil": "Reverse Holofoil",
          "1stEditionHolofoil": "1st Edition Holofoil", "1stEditionNormal": "1st Edition Normal",
          "unlimitedHolofoil": "Unlimited Holofoil", "unlimitedNormal": "Unlimited Normal"}

def label(v):
    return LABELS.get(v) or re.sub(r"(?<!^)(?=[A-Z])", " ", v or "").title()

def vp_from_prices(prices):
    """{variant: market price} from a tcgplayer 'prices' dict (variants with no market price are skipped)."""
    return {k: v["market"] for k, v in (prices or {}).items() if isinstance(v, dict) and v.get("market")}

def variant_prices(tcg): return vp_from_prices((tcg or {}).get("prices"))

def ordered(vp):
    return sorted(vp, key=lambda k: (VARIANT_ORDER.index(k) if k in VARIANT_ORDER else 99, k))

def default_variant(vp):
    o = ordered(vp); return o[0] if o else None

def record_variants(db, card_id, tcg, day):
    """One history point per variant, dated by the source."""
    if not day: return
    for v, m in variant_prices(tcg).items():
        db.execute("INSERT OR REPLACE INTO price_history(card_id,variant,day,market) VALUES(?,?,?,?)", (card_id, v, day, m))

def fetch(ids, timeout=30, tries=3):
    """{card_id: tcgplayer-block} for up to ~20 ids, or None if the API is down."""
    ids = [i for i in ids if _ID.match(i)]
    if not ids: return {}
    q = " OR ".join(f'id:"{i}"' for i in ids)
    for k in range(tries):
        try:
            r = requests.get(API, headers=HDR, timeout=timeout, params={"q": q, "select": "id,tcgplayer", "pageSize": 250})
            r.raise_for_status()
            return {c["id"]: c.get("tcgplayer") for c in r.json()["data"]}
        except Exception:
            if k < tries - 1: time.sleep(2 ** k)
    return None

def refresh(ids, timeout=30, tries=3):
    """Update current price + add a history point for each card. Returns how many cards updated."""
    db, n = conn(), 0
    try:
        for i in range(0, len(ids), 20):
            got = fetch(ids[i:i + 20], timeout, tries)
            if got is None: continue
            for cid, tcg in got.items():
                m, d = best_price(tcg), day_of(tcg)
                if m is None: continue
                db.execute("UPDATE cards SET market=?, prices_json=?, price_day=? WHERE id=?",
                           (m, json.dumps((tcg or {}).get("prices")), d, cid))
                record_variants(db, cid, tcg, d); n += 1
        db.commit()
    finally: db.close()
    return n

def get_meta(key):
    db = conn()
    try:
        r = db.execute("SELECT value FROM meta WHERE key=?", (key,)).fetchone(); return r[0] if r else None
    finally: db.close()

def set_meta(key, value):
    db = conn()
    try: db.execute("INSERT OR REPLACE INTO meta VALUES(?,?)", (key, str(value))); db.commit()
    finally: db.close()

def tracked_ids():
    db = conn()
    try: return [r[0] for r in db.execute("SELECT card_id FROM tracked UNION SELECT card_id FROM collection")]
    finally: db.close()

def refresh_tracked():
    ids = tracked_ids(); n = refresh(ids)
    if n or not ids: set_meta("last_refresh", time.time())      # only count it as done if something worked
    return n

def start_background(every_hours=12):
    def loop():
        while True:
            try:
                if time.time() - float(get_meta("last_refresh") or 0) > every_hours * 3600: refresh_tracked()
            except Exception as e: print("price refresh failed:", e)
            time.sleep(1800)
    threading.Thread(target=loop, daemon=True).start()
