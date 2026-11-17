# Container recipe for hosting (Railway, Render, Fly.io, any VPS). Not built/tested in the authoring sandbox.
FROM python:3.12-slim
ENV PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 \
    DATA_DIR=/data TRUST_PROXY=1 CATALOG_TOPUP=1
RUN apt-get update && apt-get install -y --no-install-recommends curl libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt
# the image-matching model (89 MB) is baked into the image
RUN mkdir -p data/models && curl -fL --retry 3 -o data/models/clip_vision_q.onnx \
    https://huggingface.co/Xenova/clip-vit-base-patch32/resolve/main/onnx/vision_model_quantized.onnx
COPY app app
COPY web web
# Mount the host's persistent disk at /data (accounts, collections, price history, scan photos, card catalogue)
EXPOSE 8000
# one worker on purpose (the card index is held in memory)
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
