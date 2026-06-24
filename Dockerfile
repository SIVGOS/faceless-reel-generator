# syntax=docker/dockerfile:1

# ---- Stage 1: build wheels for Python deps ----
FROM python:3.11-slim AS builder

ENV PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /build
RUN apt-get update && apt-get install -y --no-install-recommends build-essential \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
# Pre-build wheels so the runtime stage installs without a compiler.
RUN pip wheel --wheel-dir /wheels -r requirements.txt


# ---- Stage 2: lean runtime ----
FROM python:3.11-slim AS runtime

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

# ffmpeg + shared libs for audio bindings (libsndfile) and ctranslate2/whisper.
RUN apt-get update && apt-get install -y --no-install-recommends \
        ffmpeg \
        libsndfile1 \
        libgomp1 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY --from=builder /wheels /wheels
COPY requirements.txt .
RUN pip install --no-index --find-links=/wheels -r requirements.txt \
    && rm -rf /wheels

# App code (backgrounds + data are mounted volumes, not baked in).
COPY app ./app

# Runtime dirs (also mounted in compose, created for bare `docker run`).
RUN mkdir -p data backgrounds

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
