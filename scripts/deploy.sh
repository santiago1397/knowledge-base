#!/usr/bin/env bash
# Deploy: server pulls latest main, rebuilds, restarts, waits for health.
# Follows the local -> GitHub -> server pattern from SERVER_SETUP.md.
set -euo pipefail

SSH_ALIAS="${SSH_ALIAS:-kb}"
VPS_REPO_PATH="${VPS_REPO_PATH:-/opt/knowledge-base}"
COMPOSE="docker compose -f docker-compose.prod.yml --env-file .env.prod"

echo "==> Checking SSH alias '$SSH_ALIAS'"
ssh -o BatchMode=yes "$SSH_ALIAS" true

echo "==> Verifying .env.prod exists on server"
ssh "$SSH_ALIAS" "test -f $VPS_REPO_PATH/server/.env.prod" \
  || { echo "Missing $VPS_REPO_PATH/server/.env.prod"; exit 1; }

echo "==> Pull + build + up"
ssh "$SSH_ALIAS" "set -e
  cd $VPS_REPO_PATH
  git fetch origin && git merge --ff-only origin/main
  cd server
  $COMPOSE build
  $COMPOSE up -d"

echo "==> Waiting for kb_api health"
ssh "$SSH_ALIAS" '
  for i in $(seq 1 30); do
    s=$(docker inspect -f "{{.State.Health.Status}}" kb_api 2>/dev/null || echo none)
    [ "$s" = "healthy" ] && echo "healthy" && exit 0
    sleep 3
  done
  echo "did not become healthy:"; docker logs --tail 60 kb_api; exit 1'

echo "==> Deployed. Remember: 'make ingest COURSE=<slug>' if data changed."
