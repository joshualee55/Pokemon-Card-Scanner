"""Re-test the matcher on YOUR saved scan photos (the ones where you confirmed the right card).
    python -m app.eval_scans              # current matcher, with card detection
    python -m app.eval_scans --no-rectify # compare without card detection
Prints accuracy and lists every miss so we can see what goes wrong."""
import sys, json, pathlib
from PIL import Image
from .db import conn
from .matcher import Index
from .main import SCAN_DIR

def main(a):
    rect = "--no-rectify" not in a
    db = conn(); idx = Index().load(db)
    rows = db.execute("SELECT id, chosen FROM scans WHERE chosen IS NOT NULL").fetchall()
    names = {r["id"]: (r["name"], r["set_name"], r["number"]) for r in db.execute("SELECT id,name,set_name,number FROM cards")}
    n = ok1 = ok3 = ok5 = 0; misses = []
    for r in rows:
        f = SCAN_DIR / f"{r['id']}.jpg"
        if not f.exists(): continue
        res = idx.search(Image.open(f), k=5, rect=rect); ids = [x[0]["id"] for x in res]; n += 1
        if r["chosen"] in ids[:1]: ok1 += 1
        if r["chosen"] in ids[:3]: ok3 += 1
        if r["chosen"] in ids: ok5 += 1
        else: misses.append((r["id"], names.get(r["chosen"]), [names.get(i) for i in ids[:2]]))
    if not n: sys.exit("No labelled scans yet. Scan some cards in the app and tap '+ Add' on the right match.")
    print(f"{n} real photos | card detection {'ON' if rect else 'OFF'} | top-1 {ok1} ({100*ok1//n}%) | top-3 {ok3} ({100*ok3//n}%) | top-5 {ok5} ({100*ok5//n}%)")
    for sid, want, got in misses: print(f"  MISS scan #{sid}: wanted {want}; guessed {got}")

if __name__ == "__main__": main(sys.argv[1:])
