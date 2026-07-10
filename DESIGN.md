# Knowledge Base — Design (locked)

Private, login-gated web app over a course library. Browse lessons + watch the
video manually, **or** chat with an agent that answers from the material and
cites the exact lesson + timestamp. Multi-course from day one.

The guiding split: **the laptop (GPU) does all AI/heavy prep offline and ships
small artifacts; the server just stores, searches, and calls an LLM.** The
deployed server never runs a GPU model larger than a tiny embedder.

---

## Data flow

```
LAPTOP (GPU, offline)                          SERVER (Contabo, shared, tiny)
─────────────────────                          ─────────────────────────────
video ─faster-whisper─▶ transcript.json
transcript ─Ollama─────▶ summary/keypoints/tags
+ content.md ─chunk────▶ ~300-tok chunks
chunks ─bge-small──────▶ vectors
        │                                       Postgres 16 + pgvector
        ├─ data/<course>/lessons/*.json ──git──▶  lessons table
        ├─ data/<course>/chunks.parquet ─git──▶  chunks table   (via `make ingest`)
        └─ media/<course>/*.mp4 ─────rsync─────▶  /opt/.../media  (served by nginx)

live question ─bge-small(server)─▶ vector ─pgvector─▶ top-5 chunks ─MiniMax─▶ answer
```

## Component decisions

| Concern | Decision | Why |
| --- | --- | --- |
| Transcription | faster-whisper `large-v3`, local GPU | free, fast, one-time per course |
| Enrichment (summary/keypoints/tags) | **Ollama** local LLM (Qwen2.5-7B / Llama-3.1-8B) | free, no tokens; runs after transcription so VRAM isn't shared |
| Embeddings | **`bge-small-en-v1.5`** via `fastembed` (ONNX, no torch) | same model laptop (bulk) + server (queries); ~250 MB; free |
| Vector store | native host **Postgres 16 + pgvector** | reuse existing DB; no new container; multi-course = `course_id` column |
| Chat LLM | **MiniMax** `MiniMax-Text-01` (`api.minimax.io/v1`) | only token spend; **non-reasoning** model — the M2.x models burn tokens "thinking" and cost far more per answer |
| API + UI | one **FastAPI** container serving a built **React/Vite SPA** | ~200 MB; no Node at runtime; SSE streaming chat |
| Video serving | tiny **nginx** container + Traefik **ForwardAuth** | native HTTP-range seeking; kept behind login; Python stays out of the byte path |
| Proxy / TLS | existing **Traefik**, one subdomain, path-routed | `/`,`/api`→api; `/media`→nginx; one cert, same-origin cookie |

## Retrieval & cost

- **Chat** = pgvector search → top-5 chunks → MiniMax. ~2.5–3.5k tokens/question.
- **Search bar** = pgvector only, **no LLM → free**.
- **Embeddings cost 0 tokens** (local). MiniMax is the only recurring spend.

## Chunking

- Transcript: **~300 tokens**, aligned to segment boundaries, ~50-token overlap;
  each chunk keeps `start_time` (first segment) → citation deep-links to video.
- `content.md`: split by markdown headings; `source=content`; no timestamp.
- Lesson **summary is its own chunk** (`source=summary`) — high-signal for
  "what is X" questions.
- Chunk metadata: `course, lesson_code, chunk_index, start_time?, source`.

## Auth (strong — protects the MiniMax budget)

- **Argon2id** password hash in `users` table (never plaintext / env).
- Signed **session cookie**: `httpOnly`, `Secure`, `SameSite=Strict`.
- **Login lockout**: 5 fails → 15-min lock.
- **No 2FA.**
- **Per-user rate limit**: 200 questions/day.
- **Global daily kill-switch**: 300k MiniMax tokens/day → chat returns
  "daily limit reached" instead of calling the API.
- First user created via `make create-user` (server-side CLI).

## Repo layout (monorepo)

```
pipeline/     LAPTOP side (GPU). Heavy deps. Never deployed.
server/api/   FastAPI + built SPA. LIGHT deps only.
server/web/   React/Vite SPA (built into the api image).
server/nginx/ media static-server config.
data/<course> COMMITTED artifacts: lessons/*.json + chunks.parquet.
media/        gitignored — rsync target for videos.
scripts/      deploy.sh (local→GitHub→server pull, per SERVER_SETUP.md).
Makefile      transcribe · enrich · embed · ingest · deploy · create-user.
```

Two **separate dependency sets** (`pipeline/pyproject.toml` vs
`server/api/pyproject.toml`) so the server image never installs faster-whisper /
torch / Ollama. `fastembed` is in both to guarantee an identical embedding model.

## Deploy-day checklist

```
1. DNS A record: library.<domain> → server IP        (before ACME)
2. Host Postgres: apt install postgresql-16-pgvector
                  CREATE DATABASE knowledge_base; CREATE EXTENSION vector; + user
3. server/.env.prod: DB creds · SESSION_SECRET (openssl rand -hex 32)
                     MINIMAX_API_KEY · rate/budget caps · APP_HOST
4. rsync videos → /opt/knowledge-base/media/<course>/
5. make deploy   → server pulls, builds (SPA baked in), starts api + nginx
6. make ingest   → load vectors + text into Postgres
7. make create-user → your login
8. Browser: HTTPS, log in, ask a question
```

No backups: the DB is reproducible (Git + `make ingest` + re-`rsync`); the only
server-only state is the single login, recreated via `make create-user`.

## Validated end-to-end (2026-07-10)

Proven to run on this machine before deployment:
- **Pipeline (GPU):** transcribe (faster-whisper `small`, CUDA) → enrich → chunk
  + embed (`bge-small`, 384-dim) → `chunks.parquet`. GPU works from a plain
  `uv sync`: `transcribe.py` auto-copies the cuBLAS/nvrtc DLLs next to
  CTranslate2 (Windows dependency fix).
- **Server:** Postgres+pgvector schema → `ingest.py` (97 lessons, 250 chunks) →
  FastAPI. Verified: login (Argon2id + cookie), wrong-password 401, ForwardAuth
  `/auth/verify` 200-with-cookie / 401-without, free semantic search, and
  **streaming MiniMax chat with citations** — tested in the real production
  Docker image (SPA baked in) against the DB.
- **MiniMax key:** confirmed working. `MiniMax-Text-01` returns direct answers
  (~1.2k tokens/question); the M2.x reasoning models were rejected as too
  costly for RAG.

Remaining before go-live: only **9 of 94 videos transcribed** during validation
— run `make pipeline COURSE=ai-seo-mastery-pro` (idempotent, skips done) for the
full corpus, then commit `data/` and `make ingest`.
