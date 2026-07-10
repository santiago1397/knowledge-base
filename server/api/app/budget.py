"""MiniMax spend guardrails: per-user daily question limit + global token
kill-switch. Both are enforced in Postgres so they survive restarts."""

from __future__ import annotations

from datetime import date

from fastapi import HTTPException

from .config import settings
from .db import cursor


def check_and_count_question(user_id: int) -> None:
    """Raise 429 if the user hit their daily question cap or the global token
    budget is exhausted; otherwise increment the user's question count."""
    today = date.today()
    with cursor() as cur:
        cur.execute("SELECT tokens_used FROM usage_daily WHERE day=%s", (today,))
        row = cur.fetchone()
        if row and row[0] >= settings.TOKEN_BUDGET_PER_DAY:
            raise HTTPException(status_code=429,
                                detail="Daily token budget reached. Try again tomorrow.")

        cur.execute("SELECT questions FROM user_usage WHERE user_id=%s AND day=%s",
                    (user_id, today))
        urow = cur.fetchone()
        if urow and urow[0] >= settings.RATE_LIMIT_PER_DAY:
            raise HTTPException(status_code=429,
                                detail="Daily question limit reached.")

        cur.execute(
            "INSERT INTO user_usage (user_id, day, questions) VALUES (%s,%s,1) "
            "ON CONFLICT (user_id, day) DO UPDATE SET questions = user_usage.questions + 1",
            (user_id, today))


def record_tokens(tokens: int) -> None:
    if tokens <= 0:
        return
    with cursor() as cur:
        cur.execute(
            "INSERT INTO usage_daily (day, tokens_used) VALUES (%s,%s) "
            "ON CONFLICT (day) DO UPDATE SET tokens_used = usage_daily.tokens_used + %s",
            (date.today(), tokens, tokens))
