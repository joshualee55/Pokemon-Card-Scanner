"""Condition *suggestion* (heuristic). The user always has the final say via the slider.
Compares edge energy along the card border in the user's photo to the matched reference
image: whitening/nicks/scuffs raise it relative to a clean card. Never suggests worse than MP."""
import numpy as np
from PIL import Image, ImageFilter

MULT = {"NM": 1.0, "LP": 0.85, "MP": 0.65, "HP": 0.45, "DMG": 0.25}

def _wear(img: Image.Image) -> float:
    g = img.convert("L").resize((315, 440))
    e = np.asarray(g.filter(ImageFilter.FIND_EDGES), dtype=np.float32)
    ring = np.concatenate([e[4:14].ravel(), e[-14:-4].ravel(), e[:, 4:14].ravel(), e[:, -14:-4].ravel()])
    return float(ring.mean()) + 1e-3

def estimate(img: Image.Image, ref: Image.Image | None = None) -> dict:
    if ref is None:
        return {"condition": "NM", "score": None, "note": "no reference - you decide"}
    ratio = _wear(img) / _wear(ref)
    cond = "NM" if ratio < 1.3 else "LP" if ratio < 1.8 else "MP"
    return {"condition": cond, "score": round(float(ratio), 2), "note": "rough suggestion - you decide"}
