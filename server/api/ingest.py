"""Load a course's committed artifacts into Postgres. Idempotent.

Reads:
    data/<course>/lessons/*.json
    data/<course>/chunks.parquet

Upserts the course + lessons, then replaces that course's chunks. Safe to
re-run; adding a course just inserts new rows. Run on the server (has DB):

    uv run ingest.py --course ai-seo-mastery-pro
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import pyarrow.parquet as pq

from app.db import cursor

REPO_ROOT = Path(__file__).resolve().parents[2]


def vec_literal(values) -> str:
    return "[" + ",".join(f"{float(x):.7f}" for x in values) + "]"


def upsert_course(cur, slug: str) -> int:
    cur.execute(
        "INSERT INTO courses (slug, title) VALUES (%s, %s) "
        "ON CONFLICT (slug) DO UPDATE SET slug = EXCLUDED.slug RETURNING id",
        (slug, slug))
    return cur.fetchone()[0]


def upsert_lesson(cur, course_id: int, l: dict) -> int:
    cur.execute(
        """INSERT INTO lessons
             (course_id, code, title, duration, source_url, video_url,
              video_file, summary, key_points, tags, content_md,
              transcript, transcript_text)
           VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
           ON CONFLICT (course_id, code) DO UPDATE SET
             title=EXCLUDED.title, duration=EXCLUDED.duration,
             source_url=EXCLUDED.source_url, video_url=EXCLUDED.video_url,
             video_file=EXCLUDED.video_file, summary=EXCLUDED.summary,
             key_points=EXCLUDED.key_points, tags=EXCLUDED.tags,
             content_md=EXCLUDED.content_md, transcript=EXCLUDED.transcript,
             transcript_text=EXCLUDED.transcript_text
           RETURNING id""",
        (course_id, l["code"], l.get("title", ""), l.get("duration", ""),
         l.get("source_url", ""), l.get("video_url", ""), l.get("video_file", ""),
         l.get("summary", ""), json.dumps(l.get("key_points", [])),
         json.dumps(l.get("tags", [])), l.get("content_md", ""),
         json.dumps(l.get("transcript", [])), l.get("transcript_text", "")))
    return cur.fetchone()[0]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--course", required=True)
    ap.add_argument("--data", default=str(REPO_ROOT / "data"))
    args = ap.parse_args()

    base = Path(args.data) / args.course
    lessons_dir = base / "lessons"
    parquet = base / "chunks.parquet"
    if not lessons_dir.is_dir() or not parquet.exists():
        print(f"Missing artifacts under {base}")
        return 1

    with cursor() as cur:
        course_id = upsert_course(cur, args.course)

        code_to_lesson_id: dict[str, int] = {}
        for f in sorted(lessons_dir.glob("*.json")):
            l = json.loads(f.read_text(encoding="utf-8"))
            code_to_lesson_id[l["code"]] = upsert_lesson(cur, course_id, l)
        print(f"Upserted {len(code_to_lesson_id)} lessons.")

        cur.execute("DELETE FROM chunks WHERE course_id = %s", (course_id,))
        table = pq.read_table(parquet).to_pylist()
        n = 0
        for ch in table:
            lid = code_to_lesson_id.get(ch["lesson_code"])
            if lid is None:
                continue
            cur.execute(
                "INSERT INTO chunks (course_id, lesson_id, lesson_code, "
                "chunk_index, source, start_time, text, embedding) "
                "VALUES (%s,%s,%s,%s,%s,%s,%s,%s::vector)",
                (course_id, lid, ch["lesson_code"], ch["chunk_index"],
                 ch["source"], ch.get("start_time"), ch["text"],
                 vec_literal(ch["embedding"])))
            n += 1
        print(f"Loaded {n} chunks for course '{args.course}'.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
