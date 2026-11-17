# Pokemon-Card-Scanner
Free workaround for Collectr Pro scans

## What it is
Python/FastAPI backend + installable PWA front end (`web/`).

    pip install -r requirements.txt          # includes onnxruntime + opencv-python-headless
    # download the CLIP image encoder once (89 MB):
    mkdir -p data/models && curl -L -o data/models/clip_vision_q.onnx \
      https://huggingface.co/Xenova/clip-vit-base-patch32/resolve/main/onnx/vision_model_quantized.onnx
    ./run_ingest.sh                          # full catalogue + prices + embeddings (resumable; flaky API -> retries)
    uvicorn app.main:app --host 0.0.0.0 --port 8000

Open http://localhost:8000. The phone camera needs HTTPS (e.g. `cloudflared tunnel --url http://localhost:8000`
or deploy to Fly/Render), then "Add to Home Screen".

Pipeline: photo -> `rectify` (find card outline, flatten) -> CLIP embedding -> cosine search over all cards.
Condition is chosen by the user with a slider; the app only suggests one.
Accounts: username + password, each user has a private collection (max 10 by default, `MAX_USERS`).
Set `SIGNUP_CODE` to require an invite code to sign up. Owner tools: `python -m app.admin list|reset|delete`.
`python eval_matcher.py 100` benchmarks matching on synthetic degraded photos.

Variants: each collection entry records which printing you own (normal/holofoil/reverseHolofoil/...); prices and history are per variant.
Price history: `app/tcgcsv.py` pulls daily TCGplayer prices from TCGCSV (free daily archives; ~2 weeks daily + weekly back
`BACKFILL_WEEKS`, default 26), only for cards in collections or that were opened. Each point is dated by its archive day.
Cards are matched to TCGplayer products via the pokemontcg.io link redirect. The old pokemontcg.io feed is only a fallback.

Windows users: see `GUIDE.txt` for a step-by-step walkthrough.

Hosting: see `HOSTING.md` (Dockerfile, `DATA_DIR`, `CATALOG_URL`, `SIGNUP_CODE`, `TRUST_PROXY`, `CATALOG_TOPUP`).
