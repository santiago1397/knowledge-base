# Knowledge Base

Private, login-gated web app over a course library. Browse lessons + watch the
video manually, or chat with an agent that answers from the material and cites
the exact lesson + timestamp. Multi-course.

**Laptop (GPU) prepares everything offline; the server just stores + serves.**
See [`DESIGN.md`](DESIGN.md) for the full locked design and rationale.

## Layout

```
pipeline/     LAPTOP (GPU): transcribe → enrich → chunk+embed → artifacts
server/api/   FastAPI + built React SPA (deploys; light deps only)
server/web/   React/Vite SPA (built into the api image)
server/nginx/ media static-server (video, behind Traefik ForwardAuth)
data/<course> committed artifacts: lessons/*.json + chunks.parquet
media/        gitignored: video rsync target
scripts/      deploy.sh   ·   Makefile: pipeline + deploy targets
```

## Laptop pipeline (offline, one-time per course)

Needs an NVIDIA GPU (CUDA 12 + cuDNN 9) and a running [Ollama](https://ollama.com).

```bash
cd pipeline && uv sync
ollama pull qwen2.5:7b-instruct

# from repo root:
make transcribe COURSE=ai-seo-mastery-pro   # video → transcript JSON
make enrich     COURSE=ai-seo-mastery-pro   # transcript → summary/keypoints/tags
make embed      COURSE=ai-seo-mastery-pro   # chunk + bge-small → data/<course>/chunks.parquet
```

Produces `data/<course>/lessons/*.json` + `data/<course>/chunks.parquet` (commit
these) and expects videos under `../video-downloader/downloads/` (rsync'd to the
server separately).

## Server

One FastAPI container (API + SPA, ~200 MB) + one nginx container (video). Plugs
into the existing Traefik + host-Postgres setup. See `DESIGN.md` → deploy-day
checklist, and `scripts/deploy.sh`.

```bash
make ingest COURSE=ai-seo-mastery-pro   # load vectors+text into Postgres (on server)
make create-user                        # bootstrap your login
make deploy                             # local → GitHub → server pull/build/restart
```

## Only one API key

`bge-small` (embeddings) and the LLM enrichment run **locally** — no key. The
**only** external key is `MINIMAX_API_KEY`, used solely to write chat answers.
