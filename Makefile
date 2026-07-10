# Knowledge Base — laptop pipeline + server ops.
# Override per invocation: make transcribe COURSE=ai-seo-mastery-pro

COURSE        ?= ai-seo-mastery-pro
SSH_ALIAS     ?= kb
VPS_REPO_PATH ?= /opt/knowledge-base
COMPOSE       = docker compose -f docker-compose.prod.yml --env-file .env.prod

.PHONY: help transcribe enrich embed pipeline deploy db-schema ingest create-user

help:
	@echo "Laptop pipeline:"
	@echo "  make transcribe COURSE=<slug>   video -> transcripts"
	@echo "  make enrich     COURSE=<slug>   transcripts -> lessons (Ollama)"
	@echo "  make embed      COURSE=<slug>   chunk + bge-small -> chunks.parquet"
	@echo "  make pipeline   COURSE=<slug>   all three"
	@echo "Server:"
	@echo "  make db-schema                  apply schema.sql (once)"
	@echo "  make deploy                     git pull + build + restart"
	@echo "  make ingest     COURSE=<slug>   load artifacts into Postgres"
	@echo "  make create-user                bootstrap a login"

# ---- laptop (GPU) ----
transcribe:
	cd pipeline && uv run transcribe.py --course $(COURSE)
enrich:
	cd pipeline && uv run enrich.py --course $(COURSE)
embed:
	cd pipeline && uv run chunk_embed.py --course $(COURSE)
pipeline: transcribe enrich embed

# ---- server ----
deploy:
	@SSH_ALIAS="$(SSH_ALIAS)" VPS_REPO_PATH="$(VPS_REPO_PATH)" bash scripts/deploy.sh

db-schema:
	ssh $(SSH_ALIAS) 'psql "$$KB_DATABASE_URL" -f $(VPS_REPO_PATH)/server/api/schema.sql'

ingest:
	ssh $(SSH_ALIAS) 'cd $(VPS_REPO_PATH)/server && $(COMPOSE) exec -T api \
	  python ingest.py --course $(COURSE) --data /app/data'

create-user:
	ssh -t $(SSH_ALIAS) 'cd $(VPS_REPO_PATH)/server && $(COMPOSE) exec api \
	  python create_user.py'
