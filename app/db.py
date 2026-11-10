import sqlite3, pathlib
DB = pathlib.Path(__file__).parent.parent / "data" / "cards.db"

def conn():
    c = sqlite3.connect(DB)
    c.row_factory = sqlite3.Row
    c.executescript("""
    CREATE TABLE IF NOT EXISTS cards(
      id TEXT PRIMARY KEY, name TEXT, set_name TEXT, number TEXT, rarity TEXT,
      image_url TEXT, market REAL, prices_json TEXT, hash BLOB);
    CREATE TABLE IF NOT EXISTS collection(
      id INTEGER PRIMARY KEY AUTOINCREMENT, card_id TEXT, condition TEXT DEFAULT 'NM', qty INTEGER DEFAULT 1);
    """)
    cols = [r[1] for r in c.execute("PRAGMA table_info(cards)")]
    if "emb" not in cols: c.execute("ALTER TABLE cards ADD COLUMN emb BLOB")
    return c
