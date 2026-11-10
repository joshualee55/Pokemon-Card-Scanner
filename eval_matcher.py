"""Compare matchers on synthetic 'phone photo' degradations. Usage: python eval_matcher.py [n]"""
import io, sys, random, requests, numpy as np
from PIL import Image, ImageEnhance, ImageFilter
from app.db import conn
from app.matcher import Index, fingerprint, best_matches, from_blob

def degrade(img, rnd):
    w, h = img.size
    m = rnd.uniform(0.02, 0.10)                                   # sloppy crop margin
    bg = Image.new("RGB", (int(w*(1+2*m)), int(h*(1+2*m))), tuple(rnd.randint(20, 200) for _ in range(3)))
    bg.paste(img, (int(w*m), int(h*m))); img = bg
    W, H = img.size; j = lambda: rnd.uniform(-0.06, 0.06)           # perspective warp
    quad = (W*j(), H*j(), -W*j(), H*(1+j()), W*(1+j()), H*(1+j()), W*(1+j()), H*j())
    img = img.transform((W, H), Image.QUAD, tuple(max(-W*.1, min(W*1.1, v)) for v in quad), Image.BICUBIC)
    img = img.rotate(rnd.uniform(-8, 8), expand=True, fillcolor=(60, 60, 60))
    img = ImageEnhance.Brightness(img).enhance(rnd.uniform(.7, 1.25))
    img = ImageEnhance.Color(img).enhance(rnd.uniform(.7, 1.2))
    a = np.asarray(img, dtype=np.float32); Hh, Ww = a.shape[:2]       # glare
    gx, gy = rnd.uniform(0, Ww), rnd.uniform(0, Hh)
    yy, xx = np.mgrid[0:Hh, 0:Ww]; glare = np.exp(-(((xx-gx)**2+(yy-gy)**2) / (2*(Ww*.25)**2))) * rnd.uniform(0, 110)
    a = np.clip(a + glare[..., None] + np.random.normal(0, 6, a.shape), 0, 255).astype(np.uint8)
    img = Image.fromarray(a).filter(ImageFilter.GaussianBlur(rnd.uniform(0.5, 1.6)))
    buf = io.BytesIO(); img.resize((rnd.randint(260, 420), rnd.randint(380, 560))).save(buf, "JPEG", quality=rnd.randint(40, 85))
    return Image.open(io.BytesIO(buf.getvalue()))

if __name__ == "__main__":
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 100
    db = conn(); idx = Index().load(db); rnd = random.Random(7)
    print(len(idx.rows), "cards indexed")
    names = {"clip (no rectify)": 0, "clip+rectify": 0}; top5 = 0; detected = 0
    for r in rnd.sample(idx.rows, n):
        img = degrade(Image.open(io.BytesIO(requests.get(r["image_url"]).content)).convert("RGB"), rnd)
        names["clip (no rectify)"] += idx.search(img, 1, rect=False)[0][0]["id"] == r["id"]
        res = idx.search(img, 5); names["clip+rectify"] += res[0][0]["id"] == r["id"]; top5 += r["id"] in [x[0]["id"] for x in res]
    for k, v in names.items(): print(f"{k:12s} top-1 {v}/{n}")
    print(f"rectify top-5 {top5}/{n}")
