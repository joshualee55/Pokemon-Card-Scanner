import sqlite3, pathlib, os
DB = pathlib.Path(os.environ.get("CARDS_DB") or pathlib.Path(__file__).parent.parent / "data" / "cards.db")

def conn():
    DB.parent.mkdir(parents=True, exist_ok=True)
    c = sqlite3.connect(DB)
    c.row_factory = sqlite3.Row
    c.executescript("""
    CREATE TABLE IF NOT EXISTS cards(
      id TEXT PRIMARY KEY, name TEXT, set_name TEXT, number TEXT, rarity TEXT,
      image_url TEXT, market REAL, prices_json TEXT, hash BLOB);
    CREATE TABLE IF NOT EXISTS collection(
      id INTEGER PRIMARY KEY AUTOINCREMENT, card_id TEXT, condition TEXT DEFAULT 'NM', qty INTEGER DEFAULT 1);
    CREATE TABLE IF NOT EXISTS price_history(
      card_id TEXT NOT NULL, variant TEXT NOT NULL, day TEXT NOT NULL, market REAL NOT NULL, PRIMARY KEY(card_id, variant, day));
    CREATE TABLE IF NOT EXISTS tracked(card_id TEXT PRIMARY KEY);
    CREATE TABLE IF NOT EXISTS meta(key TEXT PRIMARY KEY, value TEXT);
    CREATE TABLE IF NOT EXISTS users(
      id INTEGER PRIMARY KEY AUTOINCREMENT, username TEXT UNIQUE COLLATE NOCASE NOT NULL,
      pw_hash TEXT NOT NULL, created REAL NOT NULL);
    CREATE TABLE IF NOT EXISTS sessions(
      token_hash TEXT PRIMARY KEY, user_id INTEGER NOT NULL, created REAL NOT NULL);
    """)
    cols = [r[1] for r in c.execute("PRAGMA table_info(collection)")]
    if "variant" not in cols: c.execute("ALTER TABLE collection ADD COLUMN variant TEXT")     # NULL = the card's default variant
    if "user_id" not in cols: c.execute("ALTER TABLE collection ADD COLUMN user_id INTEGER")  # NULL = unclaimed (pre-accounts)
    cols = [r[1] for r in c.execute("PRAGMA table_info(cards)")]
    if "emb" not in cols: c.execute("ALTER TABLE cards ADD COLUMN emb BLOB")
    if "price_day" not in cols: c.execute("ALTER TABLE cards ADD COLUMN price_day TEXT")   # date the source says the price is from
    if "variant" not in [r[1] for r in c.execute("PRAGMA table_info(price_history)")]:
        # old history was one 'highest variant' series. Replace it with per-variant history, re-seeded from
        # the latest prices we already hold (each dated by the source), so nothing real is lost.
        import json
        c.execute("DROP TABLE price_history")
        c.execute("CREATE TABLE price_history(card_id TEXT NOT NULL, variant TEXT NOT NULL, day TEXT NOT NULL, market REAL NOT NULL, PRIMARY KEY(card_id, variant, day))")
        for r in c.execute("SELECT id, prices_json, price_day FROM cards WHERE price_day IS NOT NULL AND prices_json IS NOT NULL").fetchall():
            for v, d in (json.loads(r["prices_json"]) or {}).items():
                if isinstance(d, dict) and d.get("market"):
                    c.execute("INSERT OR REPLACE INTO price_history VALUES(?,?,?,?)", (r["id"], v, r["price_day"], d["market"]))
    c.commit()
    return c
