"""Shared paths + helpers for the offline pipeline.

The pipeline reads a course's downloaded videos + manifest (produced by the
sibling `video-downloader` project) READ-ONLY, and writes artifacts under
`data/<course>/` at the repo root:

    data/<course>/transcripts/<code>_<slug>.json   (transcribe.py)
    data/<course>/lessons/<code>.json              (enrich.py)
    data/<course>/chunks.parquet                   (chunk_embed.py)
"""

from __future__ import annotations

import json
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_SOURCE = REPO_ROOT.parent / "video-downloader"

EMBED_MODEL = "BAAI/bge-small-en-v1.5"   # identical on laptop + server


def data_dir(course: str) -> Path:
    return REPO_ROOT / "data" / course


def load_manifest(source: Path) -> dict:
    path = source / "manifest.json"
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}


def lesson_stem(row: dict) -> str:
    """Filename stem shared with the video/content files (from the manifest)."""
    base = row.get("content_file") or row.get("video_file") or row["code"]
    return Path(base).stem


def read_content_md(source: Path, row: dict) -> str:
    """The lesson's existing content.md body (may be sparse / '(no description)')."""
    cf = row.get("content_file")
    if not cf:
        return ""
    p = source / cf
    return p.read_text(encoding="utf-8") if p.exists() else ""
