#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
export PYTHONPYCACHEPREFIX="$ROOT_DIR/.pycache"
TEST_CONFIG_DIR="$(mktemp -d)"
export AURALIS_CONFIG_DIR="$TEST_CONFIG_DIR"
export AURALIS_TEST_OFFLINE=1
export PYTHONPATH="$ROOT_DIR/scripts/offline:$ROOT_DIR/SonicVale"
cleanup() {
  rm -rf "$TEST_CONFIG_DIR"
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

.venv/bin/python "$ROOT_DIR/scripts/test_backend.py"

.venv/bin/python "$ROOT_DIR/scripts/smoke_api.py"

cd "$ROOT_DIR/sonicvale-front"
if ! rg -q "fetchChapterTimeline|buildChapterTimeline|updateTimelineClip|renderChapterTimeline" src/components/production/ChapterTimeline.vue; then
  echo "ChapterTimeline must use the real timeline edit and render APIs" >&2
  exit 1
fi
if rg -q "estimateSeconds|text_content.length" src/components/production/ChapterTimeline.vue; then
  echo "ChapterTimeline still contains text-length timeline estimation" >&2
  exit 1
fi
echo "Frontend timeline API integration ok"
npm test
node --check electron/main.js
node --check electron/preload.js
node --check electron/logger.js
npm run build
npm run build:demo
