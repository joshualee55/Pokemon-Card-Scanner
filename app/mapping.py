"""Match our cards to TCGplayer products using TCGCSV's product list (set + card number + name).
Independent of the pokemontcg.io price links (which are missing/flaky for promos and the newest sets).
Per set we pick the TCGplayer set whose cards match best, so differences like 'Base' vs 'Base Set' don't matter."""
import re, json, gzip, time, unicodedata, collections, difflib, requests
from .db import conn, DATA

UA = {"User-Agent": "CardTrackerPersonal/0.1 (personal collection tracker)"}
BASE = "https://tcgcsv.com/tcgplayer/3"          # category 3 = Pokemon
CACHE = DATA / "tcgcsv_products.json.gz"
MAX_AGE = 3 * 86400

def norm_num(n):
    """'001/102' -> '1', 'SWSH001' -> 'SWSH1', 'TG01/TG30' -> 'TG1'"""
    x = (n or "").split("/")[0].strip().upper()
    return re.sub(r"(?<!\d)0+(?=\d)", "", x)

def norm_name(s):
    s = unicodedata.normalize("NFKD", s or "").encode("ascii", "ignore").decode().lower()
    s = re.sub(r"['`]", "", s)                                   # TCGplayer drops apostrophes: Blaine's -> Blaines
    return re.sub(r"[^a-z0-9]+", " ", s).strip()

def related(a, b):
    """Loose name relation for names that already share a card number (TCGplayer appends numbers/descriptors)."""
    if a == b: return 2
    if not a or not b: return 0
    if a.startswith(b + " ") or b.startswith(a + " "): return 1          # 'bulbasaur' vs 'bulbasaur holo common'
    ta, tb = a.split(), b.split()
    return 1 if ta[0] == tb[0] and len(ta[0]) >= 4 else 0                # same first word

def _get(url, tries=4):
    for i in range(tries):
        try:
            r = requests.get(url, headers=UA, timeout=60); r.raise_for_status(); return r.json()["results"]
        except Exception: time.sleep(1 + i)
    return None

def load_products(force=False, max_age=MAX_AGE):
    """{'groups': {gid: name}, 'products': {gid: [{'p': productId, 'n': cleanName, 'u': number}, ...]}} (cached on disk)."""
    if CACHE.exists() and not force and (max_age is None or time.time() - CACHE.stat().st_mtime < max_age):
        return json.loads(gzip.decompress(CACHE.read_bytes()))
    groups = _get(f"{BASE}/groups")
    if not groups: return json.loads(gzip.decompress(CACHE.read_bytes())) if CACHE.exists() else None
    out = {"groups": {str(g["groupId"]): g["name"] for g in groups}, "products": {}}
    for g in groups:
        ps = _get(f"{BASE}/{g['groupId']}/products")
        if ps is None: continue
        out["products"][str(g["groupId"])] = [
            {"p": p["productId"], "n": p.get("cleanName") or p["name"],
             "u": next((e["value"] for e in p["extendedData"] if e["name"] == "Number"), None)}
            for p in ps if any(e["name"] == "Number" for e in p["extendedData"])]   # skips sealed product
        time.sleep(0.2)
    if len(out["products"]) < len(groups) * 0.9 and CACHE.exists():       # partial download: keep the old cache
        return json.loads(gzip.decompress(CACHE.read_bytes()))
    CACHE.parent.mkdir(parents=True, exist_ok=True)
    CACHE.write_bytes(gzip.compress(json.dumps(out).encode())); return out

def match(cards, idx):
    """cards: rows with id,name,number. Returns {card_id: (product_id, group_id)}."""
    by_num = collections.defaultdict(list)                     # number -> [(group, product, normalized name)]
    for gid, plist in idx["products"].items():
        for p in plist: by_num[norm_num(p["u"])].append((int(gid), p["p"], norm_name(p["n"])))
    by_set = collections.defaultdict(list); set_names = {}
    for c in cards:
        sid = c["id"].rsplit("-", 1)[0]; by_set[sid].append(c)
        try: set_names[sid] = c["set_name"]
        except (KeyError, IndexError): pass
    out = {}
    for sid, cs in by_set.items():
        votes, cand = collections.Counter(), {}
        for c in cs:
            nm = norm_name(c["name"]); hits = []
            for gid, pid, pn in by_num.get(norm_num(c["number"]), ()):
                r = related(nm, pn)
                if r: hits.append((gid, pid, r))
            cand[c["id"]] = hits
            for g in {h[0] for h in hits}: votes[g] += 1
        best = votes.most_common(1)
        best_g = None
        if best and best[0][1] >= max(1, 0.4 * len(cs)):
            tied = [g for g, v in votes.items() if v == best[0][1]]
            if len(tied) > 1:      # e.g. 'Base Set' vs 'Base Set (Shadowless)': take the group named most like the set
                sname = norm_name(set_names.get(sid, ""))
                tied.sort(key=lambda g: (-difflib.SequenceMatcher(None, sname, norm_name(idx["groups"].get(str(g), ""))).ratio(), g))
            best_g = tied[0]
        for c in cs:
            hits = cand[c["id"]]; chosen = None
            if best_g is not None:
                inb = sorted((h for h in hits if h[0] == best_g), key=lambda h: -h[2])   # exact name beats loose
                chosen = inb[0] if inb else None
            if chosen is None:
                strict = [h for h in hits if h[2] == 2]
                if len({h[1] for h in strict}) == 1: chosen = strict[0]                   # unambiguous anywhere
            if chosen: out[c["id"]] = (chosen[1], chosen[0])
    return out

def build(db=None, idx=None, max_age=None):
    """Fill card_product for every card we can match. Existing links from pokemontcg.io are kept (authoritative)."""
    own = db is None; db = db or conn()
    try:
        idx = idx or load_products(max_age=max_age)      # default: any cached copy; downloads only if none exists
        if not idx: return None
        cards = db.execute("SELECT id,name,number,set_name FROM cards").fetchall()
        known = {r[0]: r[1] for r in db.execute("SELECT card_id, product_id FROM card_product")}
        m = match(cards, idx); added = agree = disagree = 0
        for cid, (pid, gid) in m.items():
            if known.get(cid):
                agree += known[cid] == pid; disagree += known[cid] != pid; continue
            db.execute("INSERT OR REPLACE INTO card_product(card_id, product_id, group_id, checked) VALUES(?,?,?,?)", (cid, pid, gid, time.time()))
            added += 1
        db.commit()
        return {"cards": len(cards), "matched": len(m), "added": added, "agree": agree, "disagree": disagree}
    finally:
        if own: db.close()

def report():
    """Price coverage of YOUR database:  python -m app.mapping   (or double-click check_prices.bat)"""
    db = conn()
    print("Matching cards to TCGplayer products (downloads the product list the first time, 2-3 minutes)...")
    st = build(db)
    if not st: raise SystemExit("Could not reach TCGCSV. Try again later.")
    total = db.execute("SELECT COUNT(*) FROM cards").fetchone()[0]
    mapped = db.execute("SELECT COUNT(*) FROM card_product WHERE product_id IS NOT NULL").fetchone()[0]
    priced = db.execute("SELECT COUNT(*) FROM cards WHERE prices_json IS NOT NULL AND prices_json <> 'null'").fetchone()[0]
    hist = db.execute("SELECT COUNT(DISTINCT card_id) FROM price_history").fetchone()[0]
    track = db.execute("SELECT COUNT(*) FROM (SELECT card_id FROM tracked UNION SELECT card_id FROM collection)").fetchone()[0]
    print(f"\nCards in your database:           {total}")
    print(f"Matched to a TCGplayer product:   {mapped}  ({100*mapped//max(total,1)}%)")
    print(f"Have a current price:             {priced}  ({100*priced//max(total,1)}%)  <- the app fills the rest in daily")
    print(f"Cards being tracked (yours/opened): {track}  | with price history so far: {hist}")
    un = db.execute("SELECT c.set_name, COUNT(*) n FROM cards c LEFT JOIN card_product p ON p.card_id=c.id AND p.product_id IS NOT NULL "
                    "WHERE p.card_id IS NULL GROUP BY c.set_name ORDER BY n DESC LIMIT 12").fetchall()
    if un:
        print("\nSets with unmatched cards (these have no price history):")
        for r in un: print(f"   {r['n']:4d}  {r['set_name']}")
    db.close()

if __name__ == "__main__": report()
