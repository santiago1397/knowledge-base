"""Minimal MiniMax chat client (OpenAI-compatible-shaped, streaming).

NOTE: confirm MINIMAX_BASE_URL / MINIMAX_MODEL against your MiniMax account.
The endpoint here posts an OpenAI-style {model, messages, stream} body to
`{BASE_URL}/text/chatcompletion_v2` and parses SSE `data:` lines.
"""

from __future__ import annotations

import json
from typing import AsyncIterator

import httpx

from .config import settings

SYSTEM_PROMPT = (
    "You answer questions using ONLY the provided course excerpts. "
    "Cite the lessons you used by their title. If the excerpts do not contain "
    "the answer, say so plainly. Be concise."
)


def build_messages(question: str, chunks: list[dict]) -> list[dict]:
    context = "\n\n".join(
        f"[{c['title']}]"
        + (f" @ {int(c['start_time'])}s" if c.get("start_time") is not None else "")
        + f"\n{c['text']}"
        for c in chunks
    )
    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": f"Course excerpts:\n{context}\n\nQuestion: {question}"},
    ]


async def stream_chat(messages: list[dict]) -> AsyncIterator[tuple[str, int]]:
    """Yield (text_delta, tokens_used). tokens_used is non-zero only on the
    final chunk when the API reports usage."""
    url = f"{settings.MINIMAX_BASE_URL}/text/chatcompletion_v2"
    headers = {"Authorization": f"Bearer {settings.MINIMAX_API_KEY}"}
    body = {
        "model": settings.MINIMAX_MODEL,
        "messages": messages,
        "stream": True,
        "max_tokens": settings.MAX_ANSWER_TOKENS,
    }
    async with httpx.AsyncClient(timeout=60) as client:
        async with client.stream("POST", url, headers=headers, json=body) as resp:
            resp.raise_for_status()
            async for line in resp.aiter_lines():
                if not line.startswith("data:"):
                    continue
                payload = line[5:].strip()
                if payload in ("", "[DONE]"):
                    continue
                try:
                    obj = json.loads(payload)
                except json.JSONDecodeError:
                    continue
                choices = obj.get("choices") or []
                if choices:
                    delta = choices[0].get("delta") or {}
                    if delta.get("content"):
                        yield delta["content"], 0
                usage = obj.get("usage")
                if usage and usage.get("total_tokens"):
                    yield "", int(usage["total_tokens"])
