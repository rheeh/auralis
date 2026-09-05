#!/usr/bin/env python3
"""Import the authored Rain Night demo and render its real timeline, fully offline.

Creates one new project only. An existing project with the same name is returned
without modification, including when its user has edited the imported material.
No startup hooks, migrations, model requests or credential copies are performed.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import sys
import wave
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
MODEL = "qwen3-tts-instruct-flash-2026-01-26"
FILES = {"rain": "rain.mp3", "doorbell": "doorbell.mp3", "paper": "paper.mp3", "knock": "knock.wav", "vibration": "vibration.wav", "steps": "steps.mp3", "clock": "clock.mp3"}


def refuse_network(*args, **kwargs):
    raise RuntimeError("The director demo importer must not access the network")


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def models(raw):
    for _ in range(2):
        if not isinstance(raw, str):
            break
        try:
            raw = json.loads(raw)
        except ValueError:
            return [item.strip() for item in raw.replace("，", ",").split(",")]
    return raw if isinstance(raw, list) else []


def schedule(fixture, manifest):
    cursor = 700
    result = {}
    for line in fixture["lines"]:
        for cue in (c for c in fixture["cues"] if c["anchor"] == line["id"] and c["placement"] == "before"):
            duration = round(cue["duration"] * 1000)
            result[cue["id"]] = (cursor, duration)
            if not cue.get("follow_scene"):
                cursor += duration + 180
        duration = round(manifest["lines"][line["id"]]["directed"]["duration"] * 1000)
        result[line["id"]] = (cursor, duration)
        for cue in (c for c in fixture["cues"] if c["anchor"] == line["id"] and c["placement"] == "with"):
            result[cue["id"]] = (cursor, round(cue["duration"] * 1000))
        cursor += duration + 380
        for cue in (c for c in fixture["cues"] if c["anchor"] == line["id"] and c["placement"] == "after"):
            duration = round(cue["duration"] * 1000)
            result[cue["id"]] = (cursor, duration)
            if not cue.get("follow_scene"):
                cursor += duration + 200
    scene_followers = {cue["id"] for cue in fixture["cues"] if cue.get("follow_scene")}
    scene_duration = max(cursor, *(start + duration for key, (start, duration) in result.items() if key not in scene_followers)) + 1300
    for cue_id in scene_followers:
        result[cue_id] = (result[cue_id][0], scene_duration - result[cue_id][0])
    return result


def exact_wav_duration(path, duration_ms):
    # Repeated MP3 sources may have encoder-delay timestamp gaps. Ensure the
    # actual PCM length, not only FFmpeg's timestamp cutoff, matches the cue.
    with wave.open(str(path), "rb") as reader:
        params = reader.getparams()
        frames = reader.readframes(reader.getnframes())
    wanted = round(duration_ms * params.framerate / 1000) * params.nchannels * params.sampwidth
    frames = (frames + b"\x00" * max(0, wanted - len(frames)))[:wanted]
    with wave.open(str(path), "wb") as writer:
        writer.setparams(params)
        writer.writeframes(frames)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config-dir", type=Path, default=Path(os.environ.get("AURALIS_CONFIG_DIR", ROOT / ".local-data")))
    parser.add_argument("--project-name", default="雨夜来件 · 导演Demo")
    args = parser.parse_args()
    config = args.config_dir.resolve()
    if not (config / "app_test.db").is_file():
        raise SystemExit("请先初始化本地 Auralis 数据库；本脚本不运行迁移或应用启动钩子。")
    os.environ["AURALIS_CONFIG_DIR"] = str(config)
    sys.path.insert(0, str(ROOT / "SonicVale"))
    socket.create_connection = refuse_network
    socket.socket.connect = refuse_network

    from app.db.database import SessionLocal
    from app.dto.timeline_dto import TimelineClipUpdateDTO
    from app.models.po import (ProjectPO, ChapterPO, RolePO, VoicePO, TTSProviderPO, LLMProviderPO, LinePO,
        AdaptationRunPO, ChatSessionPO, SourceDocumentPO, ChatMessagePO, AdaptationDraftRevisionPO)
    from app.repositories.line_repository import LineRepository
    from app.repositories.role_repository import RoleRepository
    from app.repositories.tts_provider_repository import TTSProviderRepository
    from app.repositories.llm_provider_repository import LLMProviderRepository
    from app.services.line_service import LineService
    from app.services.timeline_service import TimelineService
    from app.services.timeline_render_service import TimelineRenderService

    db = SessionLocal()
    try:
        existing = db.query(ProjectPO).filter_by(name=args.project_name).first()
        if existing:
            chapter = db.query(ChapterPO).filter_by(project_id=existing.id).order_by(ChapterPO.id).first()
            print(json.dumps({"status": "already_exists_untouched", "project_id": existing.id, "chapter_id": chapter.id if chapter else None, "project_path": existing.project_root_path}, ensure_ascii=False))
            return

        asset_root = ROOT / "sonicvale-front/public/demo-night"
        fixture_path = ROOT / "sonicvale-front/src/demo/suspense.json"
        fixture = json.loads(fixture_path.read_text())
        manifest = json.loads((asset_root / "manifest.json").read_text())
        for line in fixture["lines"]:
            digest = hashlib.sha256(line["text"].encode()).hexdigest()
            for take in ("neutral", "directed"):
                record = manifest["lines"][line["id"]][take]
                if record["text_sha256"] != digest or sha(asset_root / record["file"]) != record["audio_sha256"]:
                    raise ValueError(f"台词或音频哈希不匹配：{line['id']} {take}")
                if take == "directed" and record["instruction"] != line["direction"]:
                    raise ValueError(f"导演指导已改变：{line['id']}")
        for sample in manifest["auditions"]:
            if sha(asset_root / sample["file"]) != sample["audio_sha256"]:
                raise ValueError(f"试听哈希不匹配：{sample['id']}")
        for cue in fixture["cues"]:
            if not (asset_root / "sfx" / FILES[cue["asset"]]).is_file():
                raise FileNotFoundError(cue["asset"])

        # Historical takes must never inherit an enabled cloud provider: runtime
        # prefers the voice's provider over the project's provider. Give each new
        # offline import its own inert snapshot, even if a same-model or formerly
        # offline provider already exists and the user has since enabled it.
        qwen = TTSProviderPO(name=f"Qwen 导演Demo（离线历史 · {uuid4().hex[:8]}）",
            api_base_url="", api_key="", provider_type="cloud", model=MODEL,
            custom_params=json.dumps({"driver": "http", "voice": "Moon", "language_type": "Chinese"}), status=0)
        db.add(qwen)
        db.flush()
        llm = next((provider for provider in db.query(LLMProviderPO).all() if provider.status == 1 and "qwen3.8-27b" in models(provider.model_list)), None)
        project = ProjectPO(name=args.project_name, description="原创悬疑导演审定稿；真实预录配音与双版本，离线导入，非本轮LLM生成。", llm_provider_id=llm.id if llm else None,
            llm_model="qwen3.8-27b", tts_provider_id=qwen.id, project_root_path=str(config / "projects/director-demo"))
        db.add(project)
        db.flush()
        project_dir = Path(project.project_root_path) / str(project.id)
        project_dir.mkdir(parents=True, exist_ok=False)
        local_assets = project_dir / "source-assets"
        local_assets.mkdir()
        for directory in ("audio", "auditions"):
            shutil.copytree(asset_root / directory, local_assets / directory)
        shutil.copy2(asset_root / "manifest.json", local_assets / "manifest.json")
        shutil.copy2(fixture_path, local_assets / "suspense.json")
        shutil.copy2(asset_root / "sfx/credits.json", local_assets / "sound-credits.json")

        role_by_key = {}
        for actor in fixture["roles"]:
            voice_spec = manifest["roles"][actor["id"]]
            voice = VoicePO(tts_provider_id=qwen.id, name=f"导演Demo {project.id} · {voice_spec['label']}", reference_path=str(local_assets / "auditions" / f"{voice_spec['voice'].lower()}.mp3"),
                description=f"导演Demo,原生表演指令,qwen_voice:{voice_spec['voice']}", is_multi_emotion=0)
            db.add(voice)
            db.flush()
            actor_po = RolePO(project_id=project.id, name=actor["name"], default_voice_id=voice.id, role_importance="lead" if actor["id"] != "narrator" else "supporting", tts_route="cloud")
            db.add(actor_po)
            db.flush()
            role_by_key[actor["id"]] = actor_po
        chapter = ChapterPO(project_id=project.id, title="雨夜来件 · 导演审定样片", order_index=1, text_content=fixture["source"])
        db.add(chapter)
        db.flush()
        rows, script_lines = {}, []
        for order, line in enumerate(fixture["lines"], 1):
            actor = role_by_key[line["role"]]
            line_type = "narration" if line["role"] == "narrator" else "dialogue"
            track = "narration" if line_type == "narration" else "voice"
            row = LinePO(chapter_id=chapter.id, role_id=actor.id, voice_id=actor.default_voice_id, line_order=order * 100,
                text_content=line["text"], line_type=line_type, track=track, should_speak=1, scene_title=fixture["title"],
                production_note=line["direction"], audio_path=str(local_assets / manifest["lines"][line["id"]]["directed"]["file"]), status="done", is_done=1)
            db.add(row)
            db.flush()
            rows[line["id"]] = row
            script_lines.append({"type": line_type, "track": track, "shouldSpeak": True, "speaker": actor.name, "text": line["text"], "productionNote": line["direction"]})
        db.commit()
        service = LineService(LineRepository(db), RoleRepository(db), TTSProviderRepository(db), LLMProviderRepository(db))
        for line in fixture["lines"]:
            for take, label in (("neutral", "无指导对照"), ("directed", "导演指导版")):
                record = manifest["lines"][line["id"]][take]
                service.register_generated_audio_version(rows[line["id"]].id, str(local_assets / record["file"]),
                    {"label": label, "origin": "director_demo_import", "model": record["model"], "voice": record["voice"], "text": line["text"], "prompt": record["instruction"], "text_sha256": record["text_sha256"]})

        timeline_positions = schedule(fixture, manifest)
        sfx_dir = local_assets / "sfx"
        sfx_dir.mkdir()
        cue_by_id = {cue["id"]: cue for cue in fixture["cues"]}
        for cue in fixture["cues"]:
            source = asset_root / "sfx" / FILES[cue["asset"]]
            output = sfx_dir / f"{cue['id']}.wav"
            cue_duration_ms = timeline_positions[cue["id"]][1]
            command = ["ffmpeg", "-nostdin", "-hide_banner", "-loglevel", "error", "-y"]
            if cue["asset"] in {"rain", "clock"}:
                command += ["-stream_loop", "-1"]
            command += ["-i", str(source)]
            filters = ["apad"]
            if cue["id"] == "knock-phone":
                filters = ["highpass=f=600", "lowpass=f=2800", "apad"]
            command += ["-af", ",".join(filters), "-t", str(cue_duration_ms / 1000), "-ar", "44100", "-ac", "2", "-c:a", "pcm_s16le", str(output)]
            subprocess.run(command, check=True)
            exact_wav_duration(output, cue_duration_ms)
            anchor = rows[cue["anchor"]]
            row = LinePO(chapter_id=chapter.id, line_order=anchor.line_order + (-1 if cue["placement"] == "before" else 1),
                text_content=cue["label"], line_type="sfx", track="sfx", should_speak=0, scene_title=fixture["title"],
                production_note=f"导演审定音效；{cue['placement']}第{cue['anchor']}句；{cue['gain']}dB", audio_path=str(output), status="done", is_done=1,
                audio_events=[{"type": "sound_library_placement", "anchor_line_id": anchor.id, "placement": cue["placement"], "duration_ms": cue_duration_ms, "volume_db": cue["gain"]}])
            db.add(row)
            db.flush()
            rows[cue["id"]] = row
        db.commit()
        timeline_service = TimelineService(db)
        timeline = timeline_service.build_chapter_timeline(project.id, chapter.id)
        clip_by_line = {clip["line_id"]: clip for track in timeline["tracks"] for clip in track["clips"]}
        for source_id, row in rows.items():
            clip = clip_by_line[row.id]
            start_ms, desired_ms = timeline_positions[source_id]
            duration_ms = min(desired_ms, clip["duration_ms"])
            cue = cue_by_id.get(source_id)
            fade = min(700 if cue and cue["asset"] in {"rain", "clock"} else 20, duration_ms // 3)
            timeline_service.update_clip(project.id, chapter.id, clip["id"], TimelineClipUpdateDTO(start_ms=start_ms, duration_ms=duration_ms,
                volume_db=cue["gain"] if cue else 0, fade_in_ms=fade, fade_out_ms=fade))
        rendered = TimelineRenderService(db).render_chapter(project.id, chapter.id)

        now = datetime.now(timezone.utc)
        session_id = uuid4().hex
        script = {"title": fixture["title"], "logline": fixture["subtitle"], "characters": [{"name": actor["name"], "role": actor["identity"], "voiceProfile": actor["direction"]} for actor in fixture["roles"]],
            "scenes": [{"title": fixture["title"], "location": "林澈公寓，23:17", "mood": "悬疑", "lines": script_lines}], "provenance": "本次原创导演审定稿；不是自动LLM改编结果。", "soundCues": fixture["cues"]}
        source_doc = SourceDocumentPO(project_id=project.id, name="雨夜来件 · 原创小说", content=fixture["source"])
        db.add(source_doc)
        db.flush()
        run = AdaptationRunPO(project_id=project.id, chapter_id=chapter.id, title=fixture["title"], source_kind="director_demo", source_text=fixture["source"],
            instruction="导演审定稿离线导入，预录音频来自真实阿里云TTS；未执行LLM改编。", scene_count=1, status="committed", current_stage="completed", draft_json=script, final_json=script,
            parsed_json={"provenance": "director_authored_fixture", "fixture_sha256": sha(fixture_path)}, session_id=session_id, is_conversational=True, committed_at=now)
        db.add(run)
        db.flush()
        session = ChatSessionPO(id=session_id, project_id=project.id, chapter_id=chapter.id, adaptation_run_id=run.id, title=chapter.title,
            source_text=fixture["source"], source_document_id=source_doc.id, instruction=run.instruction, status="completed", current_stage="completed", completed_at=now)
        db.add(session)
        db.flush()
        db.add(AdaptationDraftRevisionPO(session_id=session_id, run_id=run.id, draft_type="script", revision=1, payload_json=script, feedback="导演审定，离线导入"))
        db.add(ChatMessagePO(id=uuid4().hex, session_id=session_id, role="assistant", message_type="text", content="导演Demo已离线导入：11句真实配音，每句有导演指导版/无指导对照；音效已进入真实时间线并渲染WAV。此台本为原创导演审定稿，未冒充自动LLM输出。"))
        db.commit()
        summary = {"status": "created", "project_id": project.id, "chapter_id": chapter.id, "session_id": session_id, "project_path": str(project_dir),
            "spoken_lines": len(fixture["lines"]), "audio_takes": len(fixture["lines"]) * 2, "auditions": len(manifest["auditions"]), "sound_cues": len(fixture["cues"]),
            "llm_model": project.llm_model, "tts_model": qwen.model, "tts_enabled": qwen.status == 1, "network_requests": 0,
            "timing": {"source": "DemoMixer.makeSchedule", "intro_ms": 700, "line_gap_ms": 380, "before_gap_ms": 180, "after_gap_ms": 200, "tail_ms": 1300, "scene_following_ambience": True, "positions_ms": timeline_positions}, **rendered}
        (project_dir / "director-demo-import.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n")
        print(json.dumps(summary, ensure_ascii=False, indent=2))
    finally:
        db.close()


if __name__ == "__main__":
    main()
