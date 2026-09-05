#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
export PYTHONPYCACHEPREFIX="$ROOT_DIR/.pycache"
TEST_CONFIG_DIR="$(mktemp -d)"
DEMO_CONFIG_DIR="$(mktemp -d)"
export AURALIS_CONFIG_DIR="$TEST_CONFIG_DIR"
cleanup() {
  rm -rf "$TEST_CONFIG_DIR"
  rm -rf "$DEMO_CONFIG_DIR"
}
trap cleanup EXIT

cd "$ROOT_DIR/SonicVale"
.venv/bin/python -m py_compile \
  app/main.py \
  app/models/po.py \
  app/core/config.py \
  app/core/audio_engin.py \
  app/core/tts_runtime.py \
  app/services/drama_adaptation_service.py \
  app/services/sound_library_service.py \
  app/services/timeline_render_service.py \
  app/routers/drama_adaptation_router.py \
  app/routers/line_router.py \
  app/routers/queue_router.py \
  app/routers/timeline_router.py

.venv/bin/python -m unittest discover -s tests -p 'test_*.py'

.venv/bin/python - <<'PY'
from fastapi.testclient import TestClient
import os
import json
import subprocess
import tempfile
import uuid
from types import SimpleNamespace

from app.main import app
from app.core.config import WORKFLOW_TTS_REVIEW_ENABLED
from app.services.line_service import LineService
from app.dto.line_dto import LineAudioProcessDTO
from app.core.subtitle import subtitle_engine

subtitle_engine.generate_subtitle = lambda audio_path, subtitle_path: open(subtitle_path, "w", encoding="utf-8").write("")
paths = {getattr(route, "path", "") for route in app.routes}
required = {
    "/drama-adaptation/runs",
    "/chat/sessions",
    "/chat/sessions/{session_id}",
    "/chat/sessions/{session_id}/confirm",
    "/chat/sessions/{session_id}/commit",
    "/chat/sessions/{session_id}/audio-tasks",
    "/chat/sessions/{session_id}/audio-tasks/generate",
    "/chat/sessions/{session_id}/audio-tasks/{task_id}/retry",
    "/chat/sessions/{session_id}/audio-tasks/{task_id}/review",
    "/ws/projects/{project_id}/sessions/{session_id}",
    "/queue/status",
    "/queue/audio-tasks",
    "/lines/generate-audio/{project_id}/{chapter_id}",
    "/lines/{line_id}/attach-audio",
    "/lines/{line_id}/audio",
    "/lines/{line_id}/audio-versions/{version_id}/activate",
    "/sound-library/assets",
    "/sound-library/assets/import-path",
    "/sound-library/assets/upload",
    "/sound-library/assets/{asset_id}/audio",
    "/sound-library/assets/{asset_id}/bind/{line_id}",
    "/projects/{project_id}/readiness",
    "/projects/{project_id}/readiness/repair",
    "/projects/{project_id}/chapters/{chapter_id}/timeline",
    "/projects/{project_id}/chapters/{chapter_id}/timeline/build",
    "/projects/{project_id}/chapters/{chapter_id}/timeline/clips/{clip_id}",
    "/projects/{project_id}/chapters/{chapter_id}/timeline/render",
    "/projects/{project_id}/chapters/{chapter_id}/timeline/render/audio",
}
missing = required - paths
if missing:
    raise SystemExit(f"missing routes: {sorted(missing)}")
print(f"FastAPI routes ok: {len(app.routes)} routes")
if not WORKFLOW_TTS_REVIEW_ENABLED:
    raise SystemExit("TTS review feature should be enabled by default")

with TestClient(app) as client:
    missing_session = client.get("/chat/sessions/sess_missing")
    if missing_session.status_code != 404 or missing_session.json().get("code") != 404:
        raise SystemExit(f"missing chat session status invalid: {missing_session.status_code} {missing_session.text}")

    library = client.get("/sound-library/assets", params={"source_type": "builtin"}).json()
    builtin_assets = library.get("data", [])
    if library.get("code") != 200 or len(builtin_assets) != 32:
        raise SystemExit(f"builtin sound library invalid: {library}")
    builtin_id = builtin_assets[0]["id"]
    builtin_audio = client.get(f"/sound-library/assets/{builtin_id}/audio")
    if builtin_audio.status_code != 200 or len(builtin_audio.content) < 100:
        raise SystemExit(f"builtin sound audio invalid: status={builtin_audio.status_code}")
    uploaded = client.post(
        "/sound-library/assets/upload",
        data={"name": "验证素材", "category": "foley", "tags": "验证,短音"},
        files={"file": ("verify.ogg", builtin_audio.content, "audio/ogg")},
    ).json()
    user_asset_id = uploaded.get("data", {}).get("id")
    if uploaded.get("code") != 200 or not str(user_asset_id).startswith("user_"):
        raise SystemExit(f"user sound upload invalid: {uploaded}")
    deleted = client.delete(f"/sound-library/assets/{user_asset_id}").json()
    if deleted.get("code") != 200 or deleted.get("data") is not True:
        raise SystemExit(f"user sound delete invalid: {deleted}")

    res = client.post("/lines/generate-audio/1/1", json={
        "chapter_id": 1,
        "text_content": "雨声渐近",
        "line_type": "sfx",
        "track": "sfx",
        "should_speak": 0
    })
    payload = res.json()
    if res.status_code != 200 or payload.get("data", {}).get("skipped") is not True:
        raise SystemExit(f"sfx skip check failed: status={res.status_code} payload={payload}")

    project_payload = {
        "name": f"Verify Repair {uuid.uuid4().hex[:8]}",
        "description": "readiness repair smoke",
    }
    project = client.post("/projects/", json=project_payload).json()
    if project.get("code") != 200:
        raise SystemExit(f"create smoke project failed: {project}")
    project_id = project["data"]["id"]
    try:
        chapter = client.post("/chapters", json={
            "project_id": project_id,
            "title": "第一场",
            "text_content": "测试章节",
        }).json()
        if chapter.get("code") != 200:
            raise SystemExit(f"create smoke chapter failed: {chapter}")
        chapter_id = chapter["data"]["id"]

        role = client.post("/roles", json={
            "project_id": project_id,
            "name": "音效",
        }).json()
        if role.get("code") != 200:
            raise SystemExit(f"create smoke role failed: {role}")
        role_id = role["data"]["id"]

        line = client.post(f"/lines/{project_id}", json={
            "chapter_id": chapter_id,
            "role_id": role_id,
            "line_order": 1,
            "text_content": "门被风吹开，走廊低频轰鸣。",
            "line_type": "sfx",
            "track": "sfx",
            "should_speak": 0,
        }).json()
        if line.get("code") != 200:
            raise SystemExit(f"create smoke material line failed: {line}")
        line_id = line["data"]["id"]

        before = client.get(f"/projects/{project_id}/readiness").json()
        before_counts = before.get("data", {}).get("counts", {})
        if before.get("code") != 200 or before_counts.get("missing_material_lines") != 1:
            raise SystemExit(f"readiness before repair invalid: {before}")

        repair = client.post(
            f"/projects/{project_id}/readiness/repair",
            params={"sync_audio_status": True, "create_material_placeholders": True},
        ).json()
        repair_data = repair.get("data", {})
        if repair.get("code") != 200 or repair_data.get("created_material_placeholders") != 1:
            raise SystemExit(f"readiness repair invalid: {repair}")

        after = client.get(f"/projects/{project_id}/readiness").json()
        after_counts = after.get("data", {}).get("counts", {})
        if after.get("code") != 200 or after_counts.get("missing_material_lines") != 0 or after_counts.get("placeholder_material_lines") != 1:
            raise SystemExit(f"readiness after repair invalid: {after}")

        line_after = client.get(f"/lines/{line_id}").json()
        line_data = line_after.get("data", {})
        if not os.path.exists(line_data.get("audio_path", "")) or line_data.get("status") != "done" or line_data.get("is_done") != 1:
            raise SystemExit(f"repaired line invalid: {line_after}")
        if "[AURALIS_PLACEHOLDER_MATERIAL]" not in (line_data.get("production_note") or ""):
            raise SystemExit(f"placeholder note missing: {line_after}")
        bound = client.post(f"/sound-library/assets/{builtin_id}/bind/{line_id}").json()
        if bound.get("code") != 200 or not os.path.exists(bound.get("data", {}).get("audio_path", "")):
            raise SystemExit(f"sound library bind invalid: {bound}")
        bound_line = client.get(f"/lines/{line_id}").json().get("data", {})
        if "[AURALIS_PLACEHOLDER_MATERIAL]" in (bound_line.get("production_note") or ""):
            raise SystemExit(f"sound library bind did not clear placeholder: {bound_line}")
        audio_res = client.get(f"/lines/{line_id}/audio")
        if audio_res.status_code != 200 or len(audio_res.content) < 100:
            raise SystemExit(f"line audio endpoint invalid: status={audio_res.status_code} size={len(audio_res.content)}")
        timeline_build = client.post(f"/projects/{project_id}/chapters/{chapter_id}/timeline/build").json()
        timeline_data = timeline_build.get("data", {})
        if timeline_build.get("code") != 200 or timeline_data.get("track_count") != 4 or timeline_data.get("clip_count") != 1:
            raise SystemExit(f"timeline build invalid: {timeline_build}")
        timeline_read = client.get(f"/projects/{project_id}/chapters/{chapter_id}/timeline").json()
        if timeline_read.get("code") != 200 or timeline_read.get("data", {}).get("duration_ms", 0) <= 0 or timeline_read.get("data", {}).get("status") != "ready":
            raise SystemExit(f"timeline read invalid: {timeline_read}")
        clips = [
            clip
            for track in timeline_read.get("data", {}).get("tracks", [])
            for clip in track.get("clips", [])
        ]
        if len(clips) != 1:
            raise SystemExit(f"timeline clips invalid: {timeline_read}")
        clip_id = clips[0]["id"]
        timeline_edit = client.patch(
            f"/projects/{project_id}/chapters/{chapter_id}/timeline/clips/{clip_id}",
            json={"start_ms": 100, "volume_db": -3, "fade_in_ms": 10},
        ).json()
        edited_clip = next(
            clip
            for track in timeline_edit.get("data", {}).get("tracks", [])
            for clip in track.get("clips", [])
        )
        if timeline_edit.get("code") != 200 or edited_clip.get("start_ms") != 100 or edited_clip.get("volume_db") != -3:
            raise SystemExit(f"timeline edit invalid: {timeline_edit}")
        timeline_render = client.post(f"/projects/{project_id}/chapters/{chapter_id}/timeline/render").json()
        render_data = timeline_render.get("data", {})
        if timeline_render.get("code") != 200 or not os.path.exists(render_data.get("audio_path", "")) or not os.path.exists(render_data.get("manifest_path", "")):
            raise SystemExit(f"timeline render invalid: {timeline_render}")
        latest_render = client.get(f"/projects/{project_id}/chapters/{chapter_id}/timeline/render").json()
        if latest_render.get("code") != 200 or latest_render.get("data", {}).get("render_fingerprint") != render_data.get("render_fingerprint"):
            raise SystemExit(f"latest timeline render invalid: {latest_render}")
        rendered_audio = client.get(f"/projects/{project_id}/chapters/{chapter_id}/timeline/render/audio")
        if rendered_audio.status_code != 200 or len(rendered_audio.content) < 100:
            raise SystemExit(f"timeline render audio invalid: status={rendered_audio.status_code} size={len(rendered_audio.content)}")
    finally:
        client.delete(f"/projects/{project_id}")
print("Multi-track TTS skip ok")
print("Project readiness repair ok")
print("Sound library browse/upload/bind/delete ok")
print("Timeline edit/render/download ok")

class FakeRepo:
    def __init__(self, line):
        self.line = line
        self.updated = None
    def get_by_id(self, line_id):
        return self.line if line_id == self.line.id else None
    def update(self, line_id, data):
        self.updated = data
        for key, value in data.items():
            setattr(self.line, key, value)
        return self.line

with tempfile.TemporaryDirectory() as tmp:
    source = os.path.join(tmp, "rain.mp3")
    target_stub = os.path.join(tmp, "audio", "id_7.wav")
    os.makedirs(os.path.dirname(target_stub), exist_ok=True)
    with open(source, "wb") as fh:
        fh.write(b"fake mp3 bytes")
    line = SimpleNamespace(id=7, chapter_id=3, audio_path=target_stub)
    repo = FakeRepo(line)
    service = LineService(repo, None, None, None)
    target = service.attach_audio_asset(7, source)
    if not target.endswith("id_7_asset.mp3") or not os.path.exists(target):
        raise SystemExit(f"asset attach target invalid: {target}")
    if repo.updated.get("status") != "done" or repo.updated.get("is_done") != 1:
        raise SystemExit(f"asset attach update invalid: {repo.updated}")
    placeholder_line = SimpleNamespace(id=8, chapter_id=3, audio_path=target_stub, production_note="[AURALIS_PLACEHOLDER_MATERIAL] draft")
    repo = FakeRepo(placeholder_line)
    service = LineService(repo, None, None, None)
    service.attach_audio_asset(8, source)
    if "[AURALIS_PLACEHOLDER_MATERIAL]" in (repo.updated.get("production_note") or ""):
        raise SystemExit(f"asset attach did not clear placeholder note: {repo.updated}")
print("Audio asset attach ok")

route_service = LineService(FakeRepo(SimpleNamespace(id=1)), None, None, None)
if route_service.resolve_tts_route(SimpleNamespace(name="旁白", tts_route="auto", role_importance="supporting"), line_type="narration") != "edge":
    raise SystemExit("narration should route to edge")
if route_service.resolve_tts_route(SimpleNamespace(name="女主", tts_route="auto", role_importance="lead"), line_type="dialogue") != "cloud":
    raise SystemExit("lead role should route to cloud")
if route_service.resolve_tts_route(SimpleNamespace(name="路人", tts_route="edge", role_importance="supporting"), emotion_name="生气") != "edge":
    raise SystemExit("explicit edge route should override emotional auto route")
if route_service.resolve_tts_route(SimpleNamespace(name="配角", tts_route="auto", role_importance="supporting"), emotion_name="生气") != "cloud":
    raise SystemExit("emotional auto route should use cloud")
print("TTS route policy ok")

class FakeLineRepo:
    def __init__(self, lines):
        self.lines = {line.id: line for line in lines}
        self.updated = {}
    def get_all(self, chapter_id):
        return [line for line in self.lines.values() if line.chapter_id == chapter_id]
    def get_by_id(self, line_id):
        return self.lines.get(line_id)
    def update(self, line_id, data):
        self.updated[line_id] = data
        line = self.lines[line_id]
        for key, value in data.items():
            setattr(line, key, value)
        return line

class FakeRoleRepo:
    def get_by_id(self, role_id):
        return SimpleNamespace(name=f"role-{role_id}") if role_id else None

with tempfile.TemporaryDirectory() as tmp:
    wav = os.path.join(tmp, "voice.wav")
    mp3 = os.path.join(tmp, "rain.mp3")
    subprocess.run([
        "ffmpeg", "-y", "-f", "lavfi", "-i", "anullsrc=r=44100:cl=mono",
        "-t", "0.05", "-c:a", "pcm_s16le", wav
    ], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    subprocess.run([
        "ffmpeg", "-y", "-f", "lavfi", "-i", "anullsrc=r=22050:cl=mono",
        "-t", "0.05", "-c:a", "libmp3lame", mp3
    ], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    lines = [
        SimpleNamespace(
            id=1, chapter_id=9, line_order=1, role_id=1, text_content="旁白", audio_path=wav,
            scene_title="开场", line_type="narration", track="narration", should_speak=1,
            voice_profile="沉稳", sound_prompt=None, production_note="压低音乐", subtitle_path=None,
            emotion_id=None, strength_id=None, status="done", is_done=1,
        ),
        SimpleNamespace(
            id=2, chapter_id=9, line_order=2, role_id=None, text_content="雨声", audio_path=mp3,
            scene_title="开场", line_type="sfx", track="sfx", should_speak=0,
            voice_profile=None, sound_prompt="窗外细雨", production_note="低频轻一点", subtitle_path=None,
            emotion_id=None, strength_id=None, status="done", is_done=1,
        ),
    ]
    service = LineService(FakeLineRepo(lines), FakeRoleRepo(), None, None)
    export = service.export_audio(9, single=False)
    if not export.get("success") or not os.path.exists(export.get("audio_path", "")):
        raise SystemExit(f"mixed export failed: {export}")
    if not os.path.exists(export.get("manifest_path", "")) or not os.path.exists(export.get("excel_path", "")):
        raise SystemExit(f"production export files missing: {export}")
    with open(export["manifest_path"], encoding="utf-8") as fh:
        manifest = json.load(fh)
    if manifest["tracks"]["sfx"] != 1 or manifest["lines"][1]["sound_prompt"] != "窗外细雨" or manifest["lines"][1]["is_placeholder_material"]:
        raise SystemExit(f"production manifest invalid: {manifest}")
    service.process_audio(2, LineAudioProcessDTO(volume=0.9))
    if not lines[1].audio_path.endswith("_processed.wav") or not os.path.exists(lines[1].audio_path):
        raise SystemExit(f"non-wav process did not convert path: {lines[1].audio_path}")
print("Mixed-format export and processing ok")
PY

cd "$ROOT_DIR/sonicvale-front"
if ! rg -q "fetchChapterTimeline|buildChapterTimeline|updateTimelineClip|renderChapterTimeline" src/pages/TimelineBoard.vue; then
  echo "TimelineBoard must use the real timeline edit and render APIs" >&2
  exit 1
fi
if rg -q "estimateSeconds|text_content.length" src/pages/TimelineBoard.vue; then
  echo "TimelineBoard still contains text-length timeline estimation" >&2
  exit 1
fi
echo "Frontend timeline API integration ok"
node --experimental-default-type=module --test tests/audioMixer.test.mjs
node --check electron/main.js
node --check electron/preload.js
node --check electron/logger.js
npm run build

cd "$ROOT_DIR"
SonicVale/.venv/bin/python scripts/seed_demo.py --config-dir "$DEMO_CONFIG_DIR" --reset --json
