#!/usr/bin/env python3
"""Append-only auditions for the user-selected Qwen-Audio 3.0 models.

Only original fictional text below is sent to the configured official Alibaba
endpoint. Credentials are read from the existing provider, never printed/copied.
--probe makes one request. --generate adds missing candidates after a successful
probe. Any API failure stops the entire run and prevents further automatic calls.
No original Demo audio, manifest, database record or active take is modified.
"""
from __future__ import annotations
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sqlite3
import subprocess
import sys
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "SonicVale"))
from app.core.tts_engine import ConfigurableCloudTTSEngine

TEXT = "别开门。门外的人，刚刚用的是你的声音。"
DIRECTION = "低声克制，句间换气，尾音收住。"
ALLOWED = {"qwen-audio-3.0-tts-plus", "qwen-audio-3.0-tts-flash"}
CANDIDATES = [
    {"id": "qwen-audio-plus-lingxin", "voice": "longanlingxin", "model": "qwen-audio-3.0-tts-plus", "label": "龙安灵心", "role": "xu", "description": "官方描述为温暖女声；都市女角候选，待盲听选择。"},
    {"id": "qwen-audio-plus-lufeng", "voice": "longanlufeng", "model": "qwen-audio-3.0-tts-plus", "label": "龙安鲁风", "role": "lin", "description": "官方描述为明亮男声；克制对话候选，待盲听选择。"},
    {"id": "qwen-audio-flash-fengyue", "voice": "longanfengyue", "model": "qwen-audio-3.0-tts-flash", "label": "龙安风悦", "role": "xu", "description": "官方描述为自然亲切女声；都市女角候选，待盲听选择。"},
]

def write_new(path, data):
    with path.open("x", encoding="utf-8") as handle:
        json.dump(data, handle, ensure_ascii=False, indent=2)
        handle.write("\n")

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--probe", action="store_true")
    group.add_argument("--generate", action="store_true")
    parser.add_argument("--provider-id", type=int, default=2)
    parser.add_argument("--config-dir", type=Path, default=ROOT / ".local-data")
    args = parser.parse_args()
    chars = len(CANDIDATES) * (len(TEXT) + len(DIRECTION))
    if chars > 150 or any(item["model"] not in ALLOWED for item in CANDIDATES):
        raise SystemExit("Candidate batch exceeds the approved model/text scope.")
    out = ROOT / "sonicvale-front/public/demo-night/free-auditions"
    final = out.parent / "free-candidates.json"
    state = args.config_dir / "free-voice-probe-state.json"
    if not (args.probe or args.generate):
        print(json.dumps({"dry_run": True, "maximum_requests": 3, "text_and_instruction_characters": chars, "output": str(out)}, ensure_ascii=False))
        return
    if state.exists() and json.loads(state.read_text()).get("failed"):
        raise SystemExit("Previous probe failed. Automatic retries are disabled; no request sent.")
    if final.exists():
        raise SystemExit("Candidate manifest already exists; no file overwritten or request sent.")
    if args.generate and not (out / f"{CANDIDATES[0]['id']}.json").exists():
        raise SystemExit("Run --probe first; generation requires one verified successful request.")
    with sqlite3.connect(f"file:{(args.config_dir / 'app_test.db').resolve()}?mode=ro", uri=True) as db:
        row = db.execute("SELECT api_base_url,api_key FROM tts_provider WHERE id=?", (args.provider_id,)).fetchone()
    if not row or not row[1]:
        raise SystemExit("Selected provider has no credential.")
    base, key = row
    host = urlparse(base).hostname or ""
    if host != "dashscope.aliyuncs.com" and not host.endswith(".cn-beijing.maas.aliyuncs.com"):
        raise SystemExit("Only the configured official Alibaba Beijing endpoint is allowed.")
    out.mkdir(parents=True, exist_ok=True)
    for item in CANDIDATES[:1] if args.probe else CANDIDATES:
        target = out / f"{item['id']}.mp3"
        metadata = target.with_suffix(".json")
        if metadata.exists():
            saved = json.loads(metadata.read_text())
            if not target.exists() or hashlib.sha256(target.read_bytes()).hexdigest() != saved["audio_sha256"]:
                raise SystemExit("Existing audition hash differs; no overwrite or request sent.")
            continue
        if target.exists():
            raise SystemExit("Existing audition has no provenance; no overwrite or request sent.")
        engine = ConfigurableCloudTTSEngine(base, key, item["model"], {"driver": "http", "format": "mp3", "sample_rate": 24000, "language_hints": ["zh"]})
        try:
            engine.synthesize(TEXT, str(target), voice_name=item["voice"], instruction=DIRECTION)
            subprocess.run(["ffmpeg", "-v", "error", "-i", str(target), "-f", "null", "-"], check=True, capture_output=True)
            duration = float(subprocess.check_output(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", str(target)], text=True))
        except Exception as exc:
            message = str(exc)
            code = next((name for name in ("Arrearage", "AllocationQuota.FreeTierOnly", "InvalidApiKey", "InvalidParameter") if name in message), type(exc).__name__)
            write_new(state, {"failed": True, "model": item["model"], "code": code, "at": datetime.now(timezone.utc).isoformat(), "requests_stopped": True})
            print(json.dumps({"ok": False, "code": code, "further_requests": 0}), flush=True)
            raise SystemExit(1) from None
        result = {**item, "mode": "native", "file": f"free-auditions/{target.name}", "duration": round(duration, 3), "instruction": DIRECTION, "text_sha256": hashlib.sha256(TEXT.encode()).hexdigest(), "audio_sha256": hashlib.sha256(target.read_bytes()).hexdigest(), "generated_at": datetime.now(timezone.utc).isoformat()}
        write_new(metadata, result)
        print(json.dumps({"ok": True, "id": item["id"], "model": item["model"], "duration": result["duration"]}), flush=True)
    if args.generate:
        write_new(final, {"schema_version": 1, "audition_text": TEXT, "audition_direction": DIRECTION, "evaluation": "独立新增候选；未替换原 Demo 配音，未经人工盲听评分。", "auditions": [json.loads((out / f"{item['id']}.json").read_text()) for item in CANDIDATES]})

if __name__ == "__main__":
    main()
