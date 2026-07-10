# Multi-stage: build the React SPA, then a light Python image that serves it.
# Build context is ./server (see docker-compose.prod.yml) so both web/ and api/
# are available.

# ---- stage 1: build the SPA ----
FROM node:20-alpine AS web
WORKDIR /web
COPY web/package.json web/package-lock.json* ./
RUN npm install
COPY web/ ./
RUN npm run build           # -> /web/dist

# ---- stage 2: API + static SPA ----
FROM python:3.12-slim
WORKDIR /app

# Light deps only — no faster-whisper / torch / ollama.
RUN pip install --no-cache-dir \
    "fastapi>=0.115" "uvicorn[standard]>=0.32" \
    "psycopg[binary]>=3.2" "psycopg-pool>=3.2" "pgvector>=0.3" \
    "fastembed>=0.4" "argon2-cffi>=23.1" "itsdangerous>=2.2" \
    "httpx>=0.28" "pyarrow>=17"

COPY api/app ./app
COPY api/ingest.py api/create_user.py ./
COPY --from=web /web/dist ./web

ENV WEB_DIST=/app/web
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
