#!/usr/bin/env python3
"""Generate auditions for the original Rain Night demo; never edits role bindings.

Default is a local dry run. --generate calls the configured Alibaba provider,
using only the newly authored demo fixture and fixed original audition text.
No credential, signed response URL or user novel is written to the manifest.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "SonicVale"))
from app.core.tts_engine import ConfigurableCloudTTSEngine

MODEL = "qwen-audio-3.0-tts-plus"
ALLOWED_MODELS = {"qwen-audio-3.0-tts-plus", "qwen-audio-3.0-tts-flash"}
ROLES = {
    "lin": {"voice": "longanlufeng", "label": "龙安鲁风 · 都市男角候选", "model": MODEL},
    "xu": {"voice": "longanlingxin", "label": "龙安灵心 · 都市女角候选", "model": MODEL},
    "narrator": {"voice": "longanlufeng", "label": "龙安鲁风 · 旁白候选", "model": MODEL},
}
AUDITION_TEXT = "别开门。先听我说，门外的人，刚刚用的是你的声音。"
AUDITION_DIRECTION = "低声面对面说话，克制紧张，句间自然换气。你的声音前稍停，尾音收住，避免播音腔。"
AUDITIONS = [{"id": role, **voice, "role": role, "description": "新建实验专用候选；自然度需人工试听确认。", "mode": "native"} for role, voice in ROLES.items()]


def dump(path, value):
    with path.open("x", encoding="utf-8") as handle:
        handle.write(json.dumps(value, ensure_ascii=False, indent=2) + "\n")


def synthesize(base, key, out, item):
    target = out / item["file"]
    if item["model"] not in ALLOWED_MODELS:
        raise ValueError("Only the user-selected Qwen-Audio 3.0 models are allowed for new generation.")
    if target.exists() or target.with_suffix(".source").exists():
        raise FileExistsError("Existing audio is protected; use a new --output-dir.")
    target.parent.mkdir(parents=True, exist_ok=True)
    params = {"driver": "http", "language_hints": ["zh"], "format": "mp3", "sample_rate": 24000}
    engine = ConfigurableCloudTTSEngine(base, key, item["model"], params)
    start = time.monotonic()
    raw_path = target.with_suffix(".source")
    engine.synthesize(item["text"], str(raw_path), voice_name=item["voice"], instruction=item["instruction"])
    subprocess.run(["ffmpeg", "-n", "-hide_banner", "-loglevel", "error", "-i", str(raw_path), "-codec:a", "libmp3lame", "-q:a", "3", str(target)], check=True)
    raw_path.unlink()
    duration = float(subprocess.check_output(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", str(target)], text=True))
    return {"file": item["file"], "duration": round(duration, 3), "model": item["model"], "voice": item["voice"], "instruction": item["instruction"], "text_sha256": hashlib.sha256(item["text"].encode()).hexdigest(), "audio_sha256": hashlib.sha256(target.read_bytes()).hexdigest(), "generation_seconds": round(time.monotonic() - start, 2)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--generate", action="store_true", help="Generate a separately authorized experiment in a NEW output directory; existing recordings are protected.")
    parser.add_argument("--provider-id", type=int, default=2)
    parser.add_argument("--config-dir", type=Path, default=Path(os.environ.get("AURALIS_CONFIG_DIR", ROOT / ".local-data")))
    parser.add_argument("--output-dir", type=Path, default=ROOT / "sonicvale-front/public/demo-night")
    args = parser.parse_args()
    if args.generate and args.output_dir.exists() and any(args.output_dir.iterdir()):
        parser.error("Existing files are protected. Choose a NEW --output-dir; no overwrite option is provided.")
    fixture_path = ROOT / "sonicvale-front/src/demo/suspense.json"
    fixture = json.loads(fixture_path.read_text(encoding="utf-8"))
    if fixture["id"] != "night-delivery-v1":
        raise ValueError("This script is scoped to the original night-delivery-v1 demo.")
    jobs = []
    for take in ("directed", "neutral"):
        for line in fixture["lines"]:
            role = ROLES[line["role"]]
            jobs.append({"id": line["id"], "take": take, "file": f"audio/{line['id']}-{take}.mp3", "text": line["text"], "voice": role["voice"], "model": MODEL, "instruction": line["direction"] if take == "directed" else ""})
    audition_jobs = [{**v, "file": f"auditions/{v['id']}.mp3", "text": AUDITION_TEXT, "instruction": AUDITION_DIRECTION} for v in AUDITIONS]
    input_characters = sum(len(v["text"]) + len(v["instruction"]) for v in jobs + audition_jobs)
    if input_characters > 2000:
        raise ValueError("New experiment exceeds the 2000 input-character ceiling.")
    if not args.generate:
        print(json.dumps({"mode": "dry_run", "model": MODEL, "line_takes": len(jobs), "auditions": len(audition_jobs), "characters": sum(len(v["text"]) for v in jobs + audition_jobs), "output_dir": str(args.output_dir)}, ensure_ascii=False))
        return
    db = args.config_dir / "app_test.db"
    with sqlite3.connect(f"file:{db.resolve()}?mode=ro", uri=True) as connection:
        row = connection.execute("SELECT api_base_url,api_key FROM tts_provider WHERE id=?", (args.provider_id,)).fetchone()
    if not row or not row[1]:
        raise ValueError("Selected Alibaba provider has no credential.")
    base, key = row
    from urllib.parse import urlparse
    host = urlparse(base).hostname or ""
    if not (host in {"dashscope.aliyuncs.com", "dashscope-intl.aliyuncs.com"} or host.endswith(".maas.aliyuncs.com")):
        raise ValueError("This script only sends its original demo dialogue to configured official Alibaba hosts.")
    out = args.output_dir
    out.mkdir(parents=True, exist_ok=True)
    manifest = {"schema_version": 1, "model": MODEL, "generated_at": datetime.now(timezone.utc).isoformat(), "fixture_sha256": hashlib.sha256(fixture_path.read_bytes()).hexdigest(), "roles": ROLES, "lines": {}, "auditions": [], "audition_text": AUDITION_TEXT, "audition_direction": AUDITION_DIRECTION, "evaluation": "已实测合成及音频解码；候选未经人工盲听评分，不声称自然度最佳。", "errors": []}
    manifest_path = out / "manifest.json"
    # Sequential requests stop at the first error, including billing failures.
    # Reserve the fresh directory before any request; never reuse a partial run.
    dump(out / "generation-started.json", {"model": MODEL, "input_characters": input_characters})
    for item in jobs + audition_jobs:
        try:
            result = synthesize(base, key, out, item)
        except Exception as exc:
            manifest["errors"].append({"id": item["id"], "error_type": type(exc).__name__})
            dump(out / "partial-manifest.json", manifest)
            print(json.dumps({"ok": False, "error_type": type(exc).__name__, "further_requests": 0}), flush=True)
            raise SystemExit(1) from None
        if "take" in item:
            manifest["lines"].setdefault(item["id"], {})[item["take"]] = result
        else:
            manifest["auditions"].append({k: item[k] for k in ("id", "voice", "label", "model", "role", "description", "mode")} | result)
        print(json.dumps({"id": item["id"], "take": item.get("take"), "ok": True}), flush=True)
    dump(manifest_path, manifest)
    print(json.dumps({"manifest": str(manifest_path), "line_takes": sum(map(len, manifest["lines"].values())), "auditions": len(manifest["auditions"]), "errors": len(manifest["errors"])}), flush=True)
    if manifest["errors"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
