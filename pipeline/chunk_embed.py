"""Chunk each enriched lesson and embed the chunks -> data/<course>/chunks.parquet.

Chunking (per DESIGN.md):
  - summary          -> one chunk (source=summary, no timestamp)
  - transcript       -> ~300-token windows aligned to segments, ~50 overlap,
                        each keeps start_time of its first segment
  - content.md       -> split by markdown headings (source=content, no timestamp)

Embeddings use bge-small via fastembed with `embed()` (the *document* side).
The server embeds questions with `query_embed()` so the query instruction is
applied only to queries -- both sides share the identical model.

Usage:
    uv run chunk_embed.py --course ai-seo-mastery-pro
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

import common

WORDS_PER_CHUNK = 230        # ~300 tokens
WORDS_OVERLAP = 40           # ~50 tokens


def _window(words: list[str], size: int, overlap: int):
    step = max(1, size - overlap)
    for i in range(0, len(words), step):
        piece = words[i : i + size]
        if piece:
            yield i, " ".join(piece)
        if i + size >= len(words):
            break


def transcript_chunks(segments: list[dict]) -> list[tuple[str, float | None]]:
    """~300-token windows; each chunk tagged with the start_time it begins at."""
    out: list[tuple[str, float | None]] = []
    words: list[str] = []
    starts: list[float] = []                 # start_time per word
    for seg in segments:
        for w in seg.get("text", "").split():
            words.append(w)
            starts.append(seg.get("start"))
    for i, text in _window(words, WORDS_PER_CHUNK, WORDS_OVERLAP):
        out.append((text, starts[i] if i < len(starts) else None))
    return out


def content_chunks(content_md: str) -> list[str]:
    """Split by markdown headings; long sections fall back to word windows."""
    if not content_md.strip():
        return []
    sections = re.split(r"(?m)^(?=#{1,6}\s)", content_md)
    chunks: list[str] = []
    for sec in sections:
        sec = sec.strip()
        if not sec:
            continue
        words = sec.split()
        if len(words) <= WORDS_PER_CHUNK * 1.5:
            chunks.append(sec)
        else:
            chunks.extend(t for _, t in _window(words, WORDS_PER_CHUNK, WORDS_OVERLAP))
    return chunks


def build_rows(lesson: dict) -> list[dict]:
    rows: list[dict] = []
    idx = 0

    def add(text: str, source: str, start: float | None):
        nonlocal idx
        text = text.strip()
        if not text:
            return
        rows.append({
            "course": lesson["course"],
            "lesson_code": lesson["code"],
            "chunk_index": idx,
            "source": source,
            "start_time": start,
            "text": text,
        })
        idx += 1

    if lesson.get("summary"):
        kp = "\n".join(f"- {p}" for p in lesson.get("key_points", []))
        add(f"{lesson['title']}\n{lesson['summary']}\n{kp}".strip(), "summary", None)
    for text, start in transcript_chunks(lesson.get("transcript", [])):
        add(text, "transcript", start)
    for text in content_chunks(lesson.get("content_md", "")):
        add(text, "content", None)
    return rows


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--course", default="ai-seo-mastery-pro")
    args = ap.parse_args()

    import pyarrow as pa
    import pyarrow.parquet as pq
    from fastembed import TextEmbedding

    lessons_dir = common.data_dir(args.course) / "lessons"
    files = sorted(lessons_dir.glob("*.json"))
    if not files:
        print(f"No lessons under {lessons_dir}; run enrich.py first.")
        return 1

    rows: list[dict] = []
    for f in files:
        rows.extend(build_rows(json.loads(f.read_text(encoding="utf-8"))))
    print(f"{len(rows)} chunks from {len(files)} lessons. Embedding...", flush=True)

    model = TextEmbedding(model_name=common.EMBED_MODEL)
    vectors = list(model.embed([r["text"] for r in rows]))
    for r, v in zip(rows, vectors):
        r["embedding"] = v.tolist()

    out = common.data_dir(args.course) / "chunks.parquet"
    pq.write_table(pa.Table.from_pylist(rows), out)
    print(f"Wrote {len(rows)} chunks ({len(vectors[0])}-dim) -> {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
