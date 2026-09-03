# Auralis

[简体中文](README.md) | **English**

Auralis is a local-first AI production workspace for turning narrative text into an editable audio-drama project. It combines manuscript adaptation, role design, script review, voice assignment, TTS generation, audio take management, and project playback in one desktop-oriented workflow.

The project emphasizes a complete production loop, clear state management, and recoverable AI steps. Users can inspect and correct every important output before audio generation instead of accepting a one-shot black-box result.

## Live Demo

[▶ Start the Auralis static demo](https://rheeh.github.io/auralis/)

The demo uses the real Vue pages and production components from this repository, with the actual `test4` project, *Undercurrents Before Morning Reading*, as its content. The source text, parsed characters, audio-drama script, voice bindings, and existing generated audio are preloaded, so the complete workflow can be explored without configuring a backend, model provider, or API key.

## Core Capabilities

- Converts novel-style source text into an audio-drama workflow: source analysis, character draft, script draft, independent review, user confirmation, and final project write-in.
- Keeps drafts separate from formal project data until the user confirms them, preventing incomplete AI output from polluting production data.
- Makes script iteration visible: the first draft can appear before review finishes, followed by the review result and repaired version.
- Provides a resident production assistant for revising scenes, locating lines, changing voices, regenerating audio, and checking missing takes.
- Routes feedback to the relevant character, scene, or line instead of blindly rerunning the entire pipeline.
- Preserves generated audio versions per line and lets the user choose the active take for playback and export.
- Includes 32 bundled CC0 ambience and Foley assets with search, preview, upload, and direct SFX/BGM line binding.
- Provides a persisted four-track timeline for timing, duration, gain, fades, and mute controls, with FFmpeg chapter rendering to WAV.
- Makes TTS capability differences explicit: cloud models can receive richer voice guidance, while Edge-TTS approximates guidance through rate, pitch, and volume.
- Brings source text, characters, lines, voice binding, generation state, preview, continuous playback, and project checks into one workspace.

## Typical Workflow

1. Paste source text into the production assistant.
2. Confirm or revise the extracted characters.
3. Generate the first audio-drama script draft.
4. Run an independent review for narration ratio, externalized inner thoughts, and visual-only descriptions that cannot be heard.
5. Inspect the repaired script and make targeted changes through the assistant.
6. Write the confirmed script into the formal project.
7. Assign voices, generate audio, compare takes, and select active versions.
8. Arrange voice, narration, SFX, and BGM clips on the timeline, then render and download the mixed chapter.

## Project Structure

```text
.
├── SonicVale/app
│   ├── main.py                         # FastAPI application entry
│   ├── routers                         # Project, line, chat, provider, and queue APIs
│   ├── services                        # Workflow, assistant, TTS, script, role, and line logic
│   ├── core                            # Provider config, LLM/TTS engines, WebSocket manager
│   └── models / entity / dto           # SQLAlchemy models and API payloads
├── sonicvale-front
│   ├── src/pages                       # Desktop workspace pages
│   ├── src/components/workflow         # Assistant, script, role, and production panels
│   └── electron                        # Electron shell
├── scripts
│   ├── dev.sh                          # Local development startup
│   ├── verify.sh                       # Backend and frontend verification
│   └── seed_demo.py                    # Local demo project generator
└── docs                                # Architecture and handoff notes
```

The core production workflow is implemented with explicit SQL-backed service state instead of LangGraph. Database tables are the source of truth, each transition is visible in application services, and retry/review behavior can be tested without an additional graph runtime.

## Technical Stack

- Desktop/web: Electron, Vue 3, Element Plus, Vite
- Backend: FastAPI, SQLAlchemy, Pydantic, SQLite
- AI: OpenAI-compatible chat providers with structured JSON validation and fallback parsing
- TTS: Edge-TTS, DashScope-compatible paths, and configurable HTTP providers
- Audio: FFmpeg-based local processing and export
- Validation: Python tests plus frontend production builds through `scripts/verify.sh`

## Design Highlights

- Separate prompts for the production assistant, source parsing, role design, script writing, and script review.
- Schema validation, fallback normalization, and malformed-output tests around structured model responses.
- An independent reviewer pass after initial script generation and before user confirmation.
- WebSocket workflow updates with REST recovery for long-running AI steps.
- Non-destructive, line-level audio versioning; playback and export use the user-selected active take.
- Persisted timeline coordinates as the final-mix source of truth, with a reproducible manifest and stale-output detection.
- Local provider snapshots for recovery from accidental configuration changes.

## Local Setup

Requirements: macOS or Linux, Python 3.12, Node.js, npm, and FFmpeg.

Start the backend and frontend:

```bash
./scripts/dev.sh
```

Default URLs:

```text
Frontend: http://127.0.0.1:5173
Backend:  http://127.0.0.1:8200
API docs: http://127.0.0.1:8200/docs
```

Run full verification:

```bash
./scripts/verify.sh
```

Build the static demo used by GitHub Pages:

```bash
cd sonicvale-front
npm run build:demo
```

Generate a local sample project without external AI/TTS providers:

```bash
SonicVale/.venv/bin/python scripts/seed_demo.py --reset
```

## Configuration

Runtime data is stored locally by default. The development script uses `.local-data` for project state, provider snapshots, logs, and workflow artifacts.

Common workflow flags:

```text
WORKFLOW_CHAT_UI_ENABLED=true
WORKFLOW_TTS_REVIEW_ENABLED=true
DRAMA_WORKFLOW_MAX_ITERATIONS=8
DRAMA_WORKFLOW_MAX_SOURCE_CHARS=120000
DRAMA_WORKFLOW_MAX_DRAFT_CHARS=180000
CHAT_EVENT_REPLAY_LIMIT=100
```

Provider keys should be configured through the app or local environment files. Secrets, runtime databases, generated audio, virtual environments, and frontend build outputs are excluded from Git.

## Verification Scope

`scripts/verify.sh` checks backend imports and syntax, FastAPI route registration, audio-drama workflows and structured model handling, TTS guidance and audio version logic, local demo generation, Electron script syntax, and frontend production builds.

## License and Attribution

This repository contains substantial product, workflow, and UI changes for the Auralis prototype while retaining components derived from the open-source [SonicVale](https://github.com/xcLee001/SonicVale) project.

SonicVale is distributed under AGPL-3.0. Keep the original attribution and comply with AGPL-3.0 when distributing or deploying modified versions.
