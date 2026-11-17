"""Make a small, public-safe catalogue file for hosting:   python -m app.export_catalog
Contains ONLY the card catalogue (names, prices, matching data). No accounts, collections, photos or sessions.
Output: data/catalog.db.gz  - upload it as a GitHub Release file and point CATALOG_URL at it."""
import gzip, shutil, sqlite3, os, pathlib
from .db import conn, DATA
from .seed import COLS

def main():
    src = conn()
    n = src.execute("SELECT COUNT(*) FROM cards WHERE emb IS NOT NULL").fetchone()[0]
    out = DATA / "catalog.db"; out.unlink(missing_ok=True)
    dst = sqlite3.connect(out)
    dst.execute("CREATE TABLE cards(id TEXT PRIMARY KEY, name TEXT, set_name TEXT, number TEXT, rarity TEXT, image_url TEXT, market REAL, prices_json TEXT, emb BLOB, price_day TEXT)")
    dst.executemany(f"INSERT INTO cards({COLS}) VALUES(?,?,?,?,?,?,?,?,?,?)",
                    (tuple(r) for r in src.execute(f"SELECT {COLS} FROM cards WHERE emb IS NOT NULL")))
    dst.commit(); dst.execute("VACUUM"); dst.close(); src.close()
    gz = DATA / "catalog.db.gz"
    with open(out, "rb") as a, gzip.open(gz, "wb", 9) as b: shutil.copyfileobj(a, b)
    out.unlink()
    print(f"Exported {n} cards -> {gz} ({gz.stat().st_size/1e6:.1f} MB)")

if __name__ == "__main__": main()
