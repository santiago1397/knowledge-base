"""Query-time embedding. Same bge-small model as the pipeline, but uses the
`query_embed()` side so bge's retrieval instruction is applied to questions."""

from __future__ import annotations

from functools import lru_cache

from .config import settings


@lru_cache(maxsize=1)
def _model():
    from fastembed import TextEmbedding
    return TextEmbedding(model_name=settings.EMBED_MODEL)


def embed_query(text: str) -> list[float]:
    vec = next(iter(_model().query_embed([text])))
    return vec.tolist()


def warmup() -> None:
    """Load the model at startup so the first question isn't slow."""
    embed_query("warmup")
