"""Transcribe course videos into timestamped JSON -- the offline GPU stage.

Reads a course's videos + manifest from the sibling video-downloader project
(read-only) and writes one transcript per lesson:

    data/<course>/transcripts/<code>_<slug>.json

Idempotent: a lesson whose transcript already exists is skipped unless --force.

Usage:
    uv run transcribe.py --course ai-seo-mastery-pro
    uv run transcribe.py --only b2ebc7f8            # a single lesson
    uv run transcribe.py --limit 1 --model tiny     # smoke test
    uv run transcribe.py --device cpu               # no GPU / cuDNN fallback
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

import common


def pending_rows(manifest: dict, out_dir: Path, downloads: Path,
                 only: str | None, force: bool) -> list[dict]:
    rows = []
    for code, row in manifest.items():
        if only and code != only:
            continue
        video_file = row.get("video_file", "")
        if not video_file or video_file == "(text-only)":
            continue
        if not (downloads / video_file).exists():
            continue
        if not force and (out_dir / f"{common.lesson_stem(row)}.json").exists():
            continue
        rows.append(row)
    return rows


def _ensure_cuda_dlls() -> None:
    """On Windows, CTranslate2 resolves its cuBLAS/nvrtc dependencies from its
    own package directory. The pip-packaged nvidia libs land elsewhere, so copy
    the needed DLLs next to ctranslate2.dll once (idempotent). Lets `--device
    cuda` work from a plain `uv sync` with no manual steps."""
    if os.name != "nt":
        return
    try:
        import importlib.util
        import shutil
        # Locate dirs WITHOUT importing (importing ctranslate2 would load its
        # DLL and cache the cuBLAS miss before we can copy it).
        ct = importlib.util.find_spec("ctranslate2")
        nv = importlib.util.find_spec("nvidia")   # PEP-420 namespace package
        if not ct or not ct.origin or not nv or not nv.submodule_search_locations:
            return
        dst = Path(ct.origin).parent
        nvbase = Path(list(nv.submodule_search_locations)[0])
        for sub in ("cublas/bin", "cuda_nvrtc/bin", "cudnn/bin"):
            src = nvbase / sub
            if not src.is_dir():
                continue
            for dll in src.glob("*.dll"):
                target = dst / dll.name
                if not target.exists():
                    shutil.copy2(dll, target)
    except Exception:                                       # noqa: BLE001
        pass


def load_model(model_name: str, device: str, compute_type: str):
    if device == "cuda":
        _ensure_cuda_dlls()
    from faster_whisper import WhisperModel

    if compute_type == "auto":
        compute_type = "float16" if device == "cuda" else "int8"
    print(f"Loading {model_name} on {device} ({compute_type})...", flush=True)
    return WhisperModel(model_name, device=device, compute_type=compute_type)


def transcribe_one(model, row: dict, downloads: Path, course: str,
                   model_name: str) -> dict:
    segments, info = model.transcribe(
        str(downloads / row["video_file"]),
        vad_filter=True,               # drop long silences -> cleaner chunks
        beam_size=5,
    )
    seg_list, parts = [], []
    for seg in segments:                # generator -> transcription runs here
        text = seg.text.strip()
        seg_list.append({"start": round(seg.start, 2),
                         "end": round(seg.end, 2),
                         "text": text})
        parts.append(text)

    return {
        "course": course,
        "code": row["code"],
        "title": row.get("title", ""),
        "source_url": row.get("source_url", ""),
        "video_url": row.get("video_url", ""),
        "duration": row.get("duration", ""),
        "model": model_name,
        "language": info.language,
        "language_probability": round(info.language_probability, 3),
        "segments": seg_list,
        "text": " ".join(parts).strip(),
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--source", default=str(common.DEFAULT_SOURCE),
                    help="path to the download project (read-only)")
    ap.add_argument("--course", default="ai-seo-mastery-pro")
    ap.add_argument("--model", default="large-v3")
    ap.add_argument("--device", default="cuda", choices=["cuda", "cpu"])
    ap.add_argument("--compute-type", default="auto")
    ap.add_argument("--only", help="transcribe just this lesson code")
    ap.add_argument("--limit", type=int, help="cap number of lessons this run")
    ap.add_argument("--force", action="store_true")
    args = ap.parse_args()

    source = Path(args.source).resolve()
    downloads = source / "downloads"
    out_dir = common.data_dir(args.course) / "transcripts"

    manifest = common.load_manifest(source)
    if not manifest:
        print(f"No manifest.json under {source}", file=sys.stderr)
        return 1

    rows = pending_rows(manifest, out_dir, downloads, args.only, args.force)
    if args.limit:
        rows = rows[: args.limit]
    if not rows:
        print("Nothing to transcribe. (All done, or nothing matched.)")
        return 0

    out_dir.mkdir(parents=True, exist_ok=True)
    try:
        model = load_model(args.model, args.device, args.compute_type)
    except Exception as e:                                  # noqa: BLE001
        print(f"Failed to load model on {args.device}: {e}", file=sys.stderr)
        if args.device == "cuda":
            print("Tip: retry with --device cpu, or check CUDA/cuDNN.",
                  file=sys.stderr)
        return 2

    total = len(rows)
    print(f"Transcribing {total} lesson(s) for '{args.course}'.\n")
    for i, row in enumerate(rows, 1):
        out = out_dir / f"{common.lesson_stem(row)}.json"
        print(f"[{i}/{total}] {row['code']} {row.get('title', '')}", flush=True)
        t0 = time.time()
        try:
            data = transcribe_one(model, row, downloads, args.course, args.model)
        except Exception as e:                              # noqa: BLE001
            print(f"    ERROR: {e}", file=sys.stderr)
            continue
        out.write_text(json.dumps(data, indent=2, ensure_ascii=False),
                       encoding="utf-8")
        print(f"    {len(data['text'].split())} words, lang={data['language']} "
              f"({time.time() - t0:.0f}s) -> {out.name}", flush=True)

    print("\nDone.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
