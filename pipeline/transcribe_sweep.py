"""Reap-proof transcription sweep: ONE long-lived process that loads the whisper
model once, then loops until every downloaded video has a transcript. Survives
the harness reaping background *shells* (a running Python child keeps going);
picks up videos as the downloader finishes them.

    uv run transcribe_sweep.py <workspace_source> <course_slug> [target_count]
"""
from __future__ import annotations

import json
import subprocess
import sys
import time
from pathlib import Path

import common
import transcribe as T


def gpu_used_mib() -> int:
    """Total GPU memory in use (MiB); 0 if nvidia-smi is unavailable."""
    try:
        out = subprocess.run(
            ["nvidia-smi", "--query-gpu=memory.used",
             "--format=csv,noheader,nounits"],
            capture_output=True, text=True, timeout=15).stdout
        return int(out.strip().splitlines()[0].strip())
    except Exception:
        return 0


def wait_for_free_gpu(threshold: int = 3000, tries: int = 240) -> None:
    """Block until no other whisper model is resident (e.g. an orphaned run)."""
    for _ in range(tries):
        used = gpu_used_mib()
        if used < threshold:
            return
        print(f"   ...GPU busy ({used} MiB); waiting for a free slot", flush=True)
        time.sleep(30)


def main() -> int:
    src = Path(sys.argv[1]).resolve()
    course = sys.argv[2]
    target = int(sys.argv[3]) if len(sys.argv) > 3 else 22

    downloads = src / "downloads"
    out_dir = common.data_dir(course) / "transcripts"
    out_dir.mkdir(parents=True, exist_ok=True)

    # Don't collide with an orphaned transcribe still holding the 8 GB card.
    wait_for_free_gpu()
    model = T.load_model("large-v3", "cuda", "auto")   # loaded ONCE, reused

    for sweep in range(1, 120):
        done = len(list(out_dir.glob("*.json")))
        manifest = common.load_manifest(src)
        rows = T.pending_rows(manifest, out_dir, downloads, None, False)
        print(f"=== sweep {sweep}: {done}/{target} done, {len(rows)} ready "
              f"({time.strftime('%H:%M:%S')}) ===", flush=True)
        if done >= target:
            print("ALL TRANSCRIBED", flush=True)
            break
        if not rows:
            time.sleep(60)          # nothing downloaded yet; wait for downloader
            continue
        for row in rows:
            out = out_dir / f"{common.lesson_stem(row)}.json"
            if out.exists():
                continue
            t0 = time.time()
            print(f"  -> {row['code']} {row.get('title','')}", flush=True)
            try:
                data = T.transcribe_one(model, row, downloads, course, "large-v3")
            except Exception as e:                       # noqa: BLE001
                print(f"     ERROR: {e}", flush=True)
                continue
            out.write_text(json.dumps(data, indent=2, ensure_ascii=False),
                           encoding="utf-8")
            print(f"     {len(data['text'].split())} words "
                  f"({time.time() - t0:.0f}s) -> {out.name}", flush=True)
        time.sleep(15)

    print(f"DONE: {len(list(out_dir.glob('*.json')))}/{target}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
