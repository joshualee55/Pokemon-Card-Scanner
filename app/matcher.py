"""Card identification via a perceptual fingerprint (v0).
Fingerprint = 16x16 dHash-style gradients on luminance + 8x8 colour thumbnail.
Good enough to prove the pipeline; swap `fingerprint()` for CLIP/DINO embeddings
later without touching anything else (see README)."""
import io, numpy as np
from PIL import Image, ImageOps

def fingerprint(img: Image.Image) -> np.ndarray:
    img = ImageOps.exif_transpose(img).convert("RGB")
    img = img.resize((63, 88))                       # normalise to card aspect ratio
    g = np.asarray(img.convert("L").resize((17, 16)), dtype=np.float32)
    grad = (g[:, 1:] > g[:, :-1]).astype(np.float32).ravel() * 2 - 1      # 256 bits as +-1
    col = np.asarray(img.resize((8, 8)), dtype=np.float32).ravel() / 255.0
    col = (col - col.mean()) * 4
    v = np.concatenate([grad, col])
    return (v / np.linalg.norm(v)).astype(np.float32)

def to_blob(v): return v.tobytes()
def from_blob(b): return np.frombuffer(b, dtype=np.float32)

def best_matches(query: np.ndarray, rows, k=5):
    M = np.stack([from_blob(r["hash"]) for r in rows])
    sims = M @ query
    idx = np.argsort(-sims)[:k]
    return [(rows[i], float(sims[i])) for i in idx]


# ---------------- CLIP embeddings (v1) ----------------
import pathlib, threading
MODEL = pathlib.Path(__file__).parent.parent / "data" / "models" / "clip_vision_q.onnx"
_MEAN = np.array([0.48145466, 0.4578275, 0.40821073], dtype=np.float32)[:, None, None]
_STD = np.array([0.26862954, 0.26130258, 0.27577711], dtype=np.float32)[:, None, None]
_sess, _lock = None, threading.Lock()

def _session():
    global _sess
    with _lock:
        if _sess is None:
            import onnxruntime as ort
            _sess = ort.InferenceSession(str(MODEL), providers=["CPUExecutionProvider"])
    return _sess

def _prep(img: Image.Image) -> np.ndarray:
    img = ImageOps.exif_transpose(img).convert("RGB").resize((224, 224), Image.BICUBIC)  # squash whole card
    a = np.asarray(img, dtype=np.float32).transpose(2, 0, 1) / 255.0
    return (a - _MEAN) / _STD

def embed_many(imgs):
    x = np.stack([_prep(i) for i in imgs])
    e = _session().run(None, {"pixel_values": x})[0]
    return (e / np.linalg.norm(e, axis=1, keepdims=True)).astype(np.float32)

def embed(img): return embed_many([img])[0]

class Index:
    """In-memory matrix of all card embeddings; rebuilt when the card count changes."""
    def __init__(self): self.n = -1
    def load(self, db):
        n = db.execute("SELECT COUNT(*) FROM cards WHERE emb IS NOT NULL").fetchone()[0]
        if n != self.n:
            self.rows = db.execute("SELECT * FROM cards WHERE emb IS NOT NULL").fetchall()
            self.E = np.stack([from_blob(r["emb"]) for r in self.rows]) if self.rows else None
            self.F = np.stack([from_blob(r["hash"]) for r in self.rows]) if self.rows else None
            self.n = n
        return self
    def search(self, img, k=5, w_fp=0.0, rect=True):
        if rect:
            from .rectify import rectify
            img = rectify(img)
        clip = self.E @ embed(img)
        s = clip + w_fp * (self.F @ fingerprint(img)) if w_fp else clip
        idx = np.argsort(-s)[:k]
        return [(self.rows[i], float(clip[i])) for i in idx]   # rank by blend, report CLIP similarity
