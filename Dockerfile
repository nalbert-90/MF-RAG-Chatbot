FROM python:3.11-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    HF_HOME=/app/.cache/huggingface \
    HF_HUB_DISABLE_TELEMETRY=1 \
    CHROMA_PATH=data/processed/chroma \
    EMBEDDING_MODEL=all-MiniLM-L6-v2

RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential \
    && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir torch --index-url https://download.pytorch.org/whl/cpu

COPY requirements-prod.txt requirements-prod.txt
RUN pip install --no-cache-dir -r requirements-prod.txt

COPY src/ src/
COPY data/registry/ data/registry/
COPY data/processed/chunks.jsonl data/processed/chunks.jsonl

RUN python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('all-MiniLM-L6-v2')"

RUN python -m src.ingest.embed_index --rebuild

ENV TRANSFORMERS_OFFLINE=1

EXPOSE 8000

CMD ["sh", "-c", "uvicorn src.api.main:app --host 0.0.0.0 --port ${PORT:-8000} --workers 1"]
