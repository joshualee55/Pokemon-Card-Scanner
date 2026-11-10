"""Find the card in a photo and warp it to a flat, upright 315x440 image.
Falls back to the original image when no card-shaped quadrilateral is found."""
import numpy as np
from PIL import Image

OUT_W, OUT_H = 315, 440
CARD_AR = 63 / 88

def _order(pts):
    s, d = pts.sum(1), np.diff(pts, axis=1).ravel()
    return np.array([pts[s.argmin()], pts[d.argmin()], pts[s.argmax()], pts[d.argmax()]], dtype=np.float32)  # tl,tr,br,bl

def rectify(img: Image.Image) -> Image.Image:
    try:
        import cv2
    except ImportError:
        return img
    rgb = np.asarray(img.convert("RGB"))
    h, w = rgb.shape[:2]
    scale = 640 / max(h, w)
    small = cv2.resize(rgb, None, fx=scale, fy=scale) if scale < 1 else rgb
    sc = small.shape[1] / w
    g = cv2.GaussianBlur(cv2.cvtColor(small, cv2.COLOR_RGB2GRAY), (5, 5), 0)
    best, best_area = None, 0
    for edges in (cv2.Canny(g, 40, 120), cv2.threshold(g, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)[1]):
        edges = cv2.morphologyEx(edges, cv2.MORPH_CLOSE, np.ones((5, 5), np.uint8))
        cnts, _ = cv2.findContours(edges, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)
        for c in sorted(cnts, key=cv2.contourArea, reverse=True)[:5]:
            area = cv2.contourArea(c)
            if area < 0.2 * small.shape[0] * small.shape[1] or area >= 0.98 * small.shape[0] * small.shape[1]: continue
            approx = cv2.approxPolyDP(c, 0.02 * cv2.arcLength(c, True), True)
            if len(approx) != 4 or not cv2.isContourConvex(approx): continue
            q = _order(approx.reshape(4, 2).astype(np.float32))
            wd = (np.linalg.norm(q[1] - q[0]) + np.linalg.norm(q[2] - q[3])) / 2
            ht = (np.linalg.norm(q[3] - q[0]) + np.linalg.norm(q[2] - q[1])) / 2
            ar = min(wd, ht) / max(wd, ht)
            if abs(ar - CARD_AR) < 0.12 and area > best_area:
                best, best_area = (q, wd > ht), area
        if best: break
    if best is None: return img
    q, landscape = best
    q = q / sc
    if landscape: q = np.roll(q, -1, axis=0)       # rotate so the long edge is vertical
    M = cv2.getPerspectiveTransform(q, np.array([[0, 0], [OUT_W, 0], [OUT_W, OUT_H], [0, OUT_H]], dtype=np.float32))
    return Image.fromarray(cv2.warpPerspective(rgb, M, (OUT_W, OUT_H), flags=cv2.INTER_CUBIC))
