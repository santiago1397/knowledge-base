"""Enrich each transcript with a summary, key points, and tags -- local + free.

Runs a local Ollama model over the transcript (+ existing content.md) and merges
everything into one per-lesson document that the server ingests and the lesson
page renders:

    data/<course>/lessons/<code>.json

Idempotent: a lesson already enriched is skipped unless --force. Requires a
running Ollama daemon (`ollama serve`) and the model pulled
(`ollama pull qwen2.5:7b-instruct`).

Usage:
    uv run enrich.py --course ai-seo-mastery-pro
    uv run enrich.py --only b2ebc7f8
    uv run enrich.py --model llama3.1:8b-instruct-q4_K_M
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import common

PROMPT = """You are summarizing a lesson from an online course so it can be \
searched and displayed in a knowledge base.

Lesson title: {title}

Transcript and notes:
\"\"\"
{body}
\"\"\"

Return ONLY a JSON object, no prose, with exactly these keys:
- "summary": 2-4 sentence plain-language overview of the lesson.
- "key_points": array of 3-7 short strings, the concrete takeaways.
- "tags": array of 3-8 lowercase topic tags (single words or short phrases).
"""


def build_body(transcript: dict, content_md: str) -> str:
    parts = []
    if transcript.get("text"):
        parts.append(transcript["text"])
    if content_md.strip():
        parts.append("\n\n--- Existing notes ---\n" + content_md)
    return "\n".join(parts).strip()


def enrich_one(client, model: str, title: str, body: str) -> dict:
    resp = client.chat(
        model=model,
        messages=[{"role": "user",
                   "content": PROMPT.format(title=title, body=body[:12000])}],
        format="json",
        options={"temperature": 0.2},
    )
    raw = resp["message"]["content"]
    data = json.loads(raw)                       # format=json -> valid JSON
    return {
        "summary": str(data.get("summary", "")).strip(),
        "key_points": [str(x).strip() for x in data.get("key_points", []) if x],
        "tags": [str(x).strip().lower() for x in data.get("tags", []) if x],
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--course", default="ai-seo-mastery-pro")
    ap.add_argument("--source", default=str(common.DEFAULT_SOURCE))
    ap.add_argument("--model", default="qwen2.5:7b-instruct")
    ap.add_argument("--only")
    ap.add_argument("--force", action="store_true")
    args = ap.parse_args()

    import ollama

    source = Path(args.source).resolve()
    manifest = common.load_manifest(source)
    trans_dir = common.data_dir(args.course) / "transcripts"
    out_dir = common.data_dir(args.course) / "lessons"
    out_dir.mkdir(parents=True, exist_ok=True)

    codes = [args.only] if args.only else list(manifest)
    client = ollama.Client()
    total = done = 0

    for code in codes:
        row = manifest.get(code)
        if not row:
            continue
        out = out_dir / f"{code}.json"
        if out.exists() and not args.force:
            continue
        total += 1

        stem = common.lesson_stem(row)
        tpath = trans_dir / f"{stem}.json"
        transcript = (json.loads(tpath.read_text(encoding="utf-8"))
                      if tpath.exists() else {})
        content_md = common.read_content_md(source, row)
        body = build_body(transcript, content_md)

        lesson = {
            "course": args.course,
            "code": code,
            "title": row.get("title", ""),
            "duration": row.get("duration", ""),
            "source_url": row.get("source_url", ""),
            "video_url": row.get("video_url", ""),
            "video_file": row.get("video_file", ""),
            "content_md": content_md,
            "transcript": transcript.get("segments", []),
            "transcript_text": transcript.get("text", ""),
            "summary": "", "key_points": [], "tags": [],
        }

        if body:
            print(f"[{code}] enriching '{row.get('title','')}'...", flush=True)
            try:
                lesson.update(enrich_one(client, args.model,
                                         row.get("title", ""), body))
                done += 1
            except Exception as e:                          # noqa: BLE001
                print(f"    enrich failed ({e}); keeping transcript only",
                      file=sys.stderr)
        else:
            print(f"[{code}] no transcript/content; metadata only", flush=True)

        out.write_text(json.dumps(lesson, indent=2, ensure_ascii=False),
                       encoding="utf-8")

    print(f"\nWrote {total} lesson file(s), {done} enriched -> {out_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
