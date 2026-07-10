"""Runtime configuration, read from the environment (.env.prod on the server)."""

from __future__ import annotations

import os


def _int(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, default))
    except ValueError:
        return default


class Settings:
    # Postgres (native host DB, reached via host.docker.internal in prod)
    DATABASE_URL: str = os.environ.get(
        "DATABASE_URL",
        "postgresql://kb:kb@localhost:5432/knowledge_base",
    )

    # Session cookie signing — `openssl rand -hex 32`
    SESSION_SECRET: str = os.environ.get("SESSION_SECRET", "dev-insecure-change-me")
    SESSION_MAX_AGE: int = _int("SESSION_MAX_AGE", 60 * 60 * 24 * 7)   # 7 days
    COOKIE_SECURE: bool = os.environ.get("COOKIE_SECURE", "true") == "true"
    COOKIE_NAME: str = "kb_session"

    # Login lockout
    MAX_FAILED_ATTEMPTS: int = _int("MAX_FAILED_ATTEMPTS", 5)
    LOCKOUT_MINUTES: int = _int("LOCKOUT_MINUTES", 15)

    # MiniMax (the only external API). Endpoint is OpenAI-compatible-shaped;
    # confirm BASE_URL + MODEL against your MiniMax account.
    MINIMAX_API_KEY: str = os.environ.get("MINIMAX_API_KEY", "")
    MINIMAX_BASE_URL: str = os.environ.get(
        "MINIMAX_BASE_URL", "https://api.minimax.io/v1")
    # MiniMax-Text-01 is non-reasoning: direct answers, far cheaper than the
    # M2.x reasoning models for RAG Q&A. (Reasoning models burn tokens thinking.)
    MINIMAX_MODEL: str = os.environ.get("MINIMAX_MODEL", "MiniMax-Text-01")

    # Guardrails on token spend
    RATE_LIMIT_PER_DAY: int = _int("RATE_LIMIT_PER_DAY", 200)        # per user
    TOKEN_BUDGET_PER_DAY: int = _int("TOKEN_BUDGET_PER_DAY", 300_000)  # global
    MAX_ANSWER_TOKENS: int = _int("MAX_ANSWER_TOKENS", 500)
    TOP_K: int = _int("TOP_K", 5)

    # Embeddings — identical model to the pipeline
    EMBED_MODEL: str = os.environ.get("EMBED_MODEL", "BAAI/bge-small-en-v1.5")

    # Static SPA (built into the image) + media mount
    WEB_DIST: str = os.environ.get("WEB_DIST", "/app/web")


settings = Settings()
