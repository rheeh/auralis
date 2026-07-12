#!/usr/bin/env python3
from __future__ import annotations

import argparse
import asyncio
import json
import os
import shutil
import sys
import wave
from pathlib import Path


DEMO_SCRIPT = {
    "title": "Auralis Demo",
    "logline": "深夜电台收到一段来自旧楼的求救录音，两名角色循声进入走廊。",
    "characters": [
        {"name": "林澈", "role": "主角", "voiceProfile": "年轻男性，冷静但语速略快"},
        {"name": "许遥", "role": "关键搭档", "voiceProfile": "年轻女性，敏锐，情绪变化明显"},
        {"name": "旁白", "role": "叙事", "voiceProfile": "清晰、克制、低声压"},
    ],
    "scenes": [
        {
            "title": "旧楼电台",
            "location": "深夜的社区广播室",
            "mood": "悬疑",
            "lines": [
                {
                    "type": "bgm",
                    "track": "bgm",
                    "shouldSpeak": False,
                    "speaker": "BGM",
                    "text": "低频合成器铺底，节奏缓慢，带轻微磁带噪声",
                    "soundPrompt": "low synth drone, tape hiss, slow suspense",
                    "productionNote": "音量压低，铺在整场下方",
                },
                {
                    "type": "narration",
                    "track": "narration",
                    "shouldSpeak": True,
                    "speaker": "旁白",
                    "text": "零点刚过，广播室的备用线路忽然自己亮了起来。",
                    "emotion": "平静",
                    "strength": "中等",
                    "voiceProfile": "克制旁白，句尾留一点悬念",
                },
                {
                    "type": "sfx",
                    "track": "sfx",
                    "shouldSpeak": False,
                    "speaker": "音效",
                    "text": "老式开关啪嗒一声，随后有电流底噪",
                    "soundPrompt": "old switch click, electric hum",
                    "productionNote": "开关声贴近，电流声持续 2 秒",
                },
                {
                    "type": "dialogue",
                    "track": "voice",
                    "shouldSpeak": True,
                    "speaker": "林澈",
                    "text": "你听见了吗？这不是我们排好的节目。",
                    "emotion": "害怕",
                    "strength": "稍弱",
                    "voiceProfile": "压低声音，克制紧张",
                },
                {
                    "type": "dialogue",
                    "track": "voice",
                    "shouldSpeak": True,
                    "speaker": "许遥",
                    "text": "别关。那段呼吸声后面，还有人在敲门。",
                    "emotion": "惊喜",
                    "strength": "中等",
                    "voiceProfile": "轻声但明确，后半句更急",
                },
            ],
        },
        {
            "title": "走廊回声",
            "location": "旧楼二层走廊",
            "mood": "逼近",
            "lines": [
                {
                    "type": "sfx",
                    "track": "sfx",
                    "shouldSpeak": False,
                    "speaker": "音效",
                    "text": "远处三次敲门声，间隔越来越短",
                    "soundPrompt": "three distant knocks, narrowing interval",
                    "productionNote": "第三声加混响，接下一句台词",
                },
                {
                    "type": "narration",
                    "track": "narration",
                    "shouldSpeak": True,
                    "speaker": "旁白",
                    "text": "他们推开门，走廊尽头的红灯正一下一下闪烁。",
                    "emotion": "平静",
                    "strength": "中等",
                    "voiceProfile": "放慢，空间感更强",
                },
                {
                    "type": "dialogue",
                    "track": "voice",
                    "shouldSpeak": True,
                    "speaker": "林澈",
                    "text": "如果录音来自这里，那门后面应该没有人。",
                    "emotion": "低落",
                    "strength": "稍弱",
                    "voiceProfile": "低声推理，句尾犹豫",
                },
                {
                    "type": "dialogue",
                    "track": "voice",
                    "shouldSpeak": True,
                    "speaker": "许遥",
                    "text": "可你看，门缝下面有光。",
                    "emotion": "害怕",
                    "strength": "中等",
                    "voiceProfile": "短促，压住呼吸",
                },
            ],
        },
    ],
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Create a local Auralis demo project and export a multitrack sample.")
    parser.add_argument("--config-dir", help="Auralis config/data directory. Defaults to AURALIS_CONFIG_DIR or .local-data.")
    parser.add_argument("--project-name", default="Auralis Demo Project")
    parser.add_argument("--chapter-title", default="Demo Episode")
    parser.add_argument("--reset", action="store_true", help="Delete the existing demo project first when present.")
    parser.add_argument("--json", action="store_true", help="Print machine-readable summary JSON.")
    return parser.parse_args()


def write_silence_wav(path: str, seconds: float = 0.25, sample_rate: int = 44100) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    frame_count = max(1, int(sample_rate * seconds))
    with wave.open(path, "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(sample_rate)
        wav.writeframes(b"\x00\x00" * frame_count)


def main() -> None:
    args = parse_args()
    root_dir = Path(__file__).resolve().parents[1]
    config_dir = Path(args.config_dir or os.environ.get("AURALIS_CONFIG_DIR") or root_dir / ".local-data").resolve()
    os.environ["AURALIS_CONFIG_DIR"] = str(config_dir)
    os.environ.setdefault("PYTHONPYCACHEPREFIX", str(root_dir / ".pycache"))
    sys.path.insert(0, str(root_dir / "SonicVale"))

    from fastapi.testclient import TestClient

    from app.main import app
    from app.db.database import SessionLocal
    from app.models.po import AdaptationRunPO, ProjectPO
    from app.repositories.line_repository import LineRepository
    from app.repositories.llm_provider_repository import LLMProviderRepository
    from app.repositories.project_repository import ProjectRepository
    from app.repositories.role_repository import RoleRepository
    from app.repositories.tts_provider_repository import TTSProviderRepository
    from app.core.subtitle import subtitle_engine
    from app.services.drama_adaptation_service import DramaAdaptationService
    from app.services.line_service import LineService

    subtitle_engine.generate_subtitle = lambda audio_path, subtitle_path: Path(subtitle_path).write_text(
        "", encoding="utf-8"
    )

    with TestClient(app):
        db = SessionLocal()
        try:
            projects = ProjectRepository(db)
            existing = projects.get_by_name(args.project_name)
            if existing and args.reset:
                projects.delete(existing.id)
                existing = None

            project_root = config_dir / "projects" / args.project_name.replace(" ", "_")
            project_root.mkdir(parents=True, exist_ok=True)

            if existing:
                project = projects.update(
                    existing.id,
                    {
                        "description": "Local end-to-end demo generated by scripts/seed_demo.py",
                        "tts_provider_id": existing.tts_provider_id or 1,
                        "project_root_path": str(project_root),
                    },
                )
            else:
                project = projects.create(
                    ProjectPO(
                        name=args.project_name,
                        description="Local end-to-end demo generated by scripts/seed_demo.py",
                        tts_provider_id=1,
                        project_root_path=str(project_root),
                    )
                )

            run = AdaptationRunPO(
                project_id=project.id,
                title=DEMO_SCRIPT["title"],
                source_kind="demo",
                source_text="内置样例文本",
                instruction="生成可验证的多轨广播剧工程",
                scene_count=len(DEMO_SCRIPT["scenes"]),
                adaptation_density="balanced",
                status="script_ready",
                current_stage="script_ready",
                parsed_json={"source": "scripts/seed_demo.py"},
                draft_json=DEMO_SCRIPT,
                final_json=DEMO_SCRIPT,
            )
            db.add(run)
            db.commit()
            db.refresh(run)

            drama = DramaAdaptationService(db)
            chapter = drama.commit_run(run.id, args.chapter_title, replace_chapter_lines=True)

            line_repo = LineRepository(db)
            lines = line_repo.get_all(chapter.id)
            durations = {"voice": 0.32, "narration": 0.36, "sfx": 0.24, "bgm": 0.48}
            for line in lines:
                write_silence_wav(line.audio_path, seconds=durations.get(line.track or "voice", 0.3))
                line_repo.update(line.id, {"status": "done", "is_done": 1})

            line_service = LineService(
                line_repo,
                RoleRepository(db),
                TTSProviderRepository(db),
                LLMProviderRepository(db),
            )
            export = line_service.export_audio(chapter.id, single=False)
            if not export.get("success"):
                raise RuntimeError(f"demo export failed: {export}")

            lines = line_repo.get_all(chapter.id)
            tracks = {}
            for line in lines:
                tracks[line.track] = tracks.get(line.track, 0) + 1

            summary = {
                "project_id": project.id,
                "chapter_id": chapter.id,
                "run_id": run.id,
                "line_count": len(lines),
                "tracks": tracks,
                "audio_path": export.get("audio_path"),
                "manifest_path": export.get("manifest_path"),
                "excel_path": export.get("excel_path"),
                "config_dir": str(config_dir),
            }
            if args.json:
                print(json.dumps(summary, ensure_ascii=False, indent=2))
            else:
                print("Auralis demo project created.")
                for key, value in summary.items():
                    print(f"{key}: {value}")
        finally:
            db.close()


if __name__ == "__main__":
    main()
