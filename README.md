# Auralis

Auralis is a local-first AI production workspace for turning novels into editable audio dramas and knowledge articles into evidence-linked, reviewable audio lessons. It combines source ingestion, structured adaptation, script review, voice assignment, TTS generation, audio take management, playback, and learning review in one desktop-oriented workflow.

The project is built as an interview-ready product prototype: the emphasis is on a complete production loop, clear state management, recoverable AI steps, and an interface that lets users inspect and correct every important output before audio generation.

## What It Does

- Converts novel-style source text into an audio-drama workflow: source analysis, character draft, script draft, independent review, user confirmation, and final project write-in.
- Converts pasted articles or accessible public article URLs into knowledge audio: source preview, evidence-backed knowledge points, outline confirmation, learning design, script generation, three-part review, TTS, and review questions.
- Preserves the boundary between source facts, source opinions, AI explanations, and externally verified material. Every core knowledge point keeps a source excerpt and can be traced to script lines after commit.
- Keeps draft data separate from the formal project until the user confirms it, so incomplete AI output does not pollute production data.
- Shows script iterations visibly: the first script draft can appear before review finishes, then the reviewer result and revised draft are surfaced as workflow progress instead of hidden latency.
- Provides a resident production assistant for free-form requests such as revising a scene, locating a line, changing a voice, regenerating audio, or checking missing takes.
- Supports targeted user revision: user feedback is routed to the relevant character, scene, or line instead of blindly rerunning the whole pipeline.
- Manages generated audio versions per line. Re-generated takes are preserved, and the user can choose which version is currently active for playback and export.
- Makes TTS capability differences explicit. Cloud TTS models can receive richer voice guidance; Edge-TTS receives approximate rate, pitch, and volume mappings rather than natural-language acting instructions.
- Provides a single project workspace for source text, roles, script lines, voice binding, TTS queue state, audio preview, continuous playback, and project-level checks.

## Typical Workflow

Novel audio drama:

1. Paste source text into the production assistant.
2. Confirm or revise extracted roles.
3. Generate the first script draft.
4. Let the reviewer check whether the script follows audio-drama rules such as minimizing narration, externalizing inner thoughts, and replacing visual-only description with audible information.
5. Review the revised script and make targeted changes through the assistant when needed.
6. Write the confirmed script into the project.
7. Assign voices, generate audio, compare takes, and choose active versions for playback/export.

Knowledge article audio:

1. Choose Knowledge Article Audio and import a public article URL or paste the article text.
2. Confirm the cleaned text; restricted WeChat pages fall back to paste mode instead of being treated as article content.
3. Generate and confirm an evidence-linked knowledge outline.
4. Generate a learning plan, knowledge script, review questions, and independent accuracy/learning/audio review.
5. Revise or confirm the script, write it into the project, and reuse the existing TTS take and export workflow.
6. Review knowledge points, replay related audio lines, and answer source-backed review questions.

## Architecture

```text
.
├── SonicVale/app
│   ├── main.py                         # FastAPI application entry
│   ├── routers                         # Project, line, chat, provider, and queue APIs
│   ├── services                        # Workflow, assistant, TTS, script, role, and line logic
│   ├── workflows/article               # Knowledge analysis, script, evidence, and review schemas
│   ├── core                            # Provider config, LLM/TTS engines, websocket manager
│   └── models / entity / dto           # SQLAlchemy models and API payloads
├── sonicvale-front
│   ├── src/pages                       # Desktop workspace pages
│   ├── src/components/workflow          # Assistant, script, role, and production panels
│   ├── src/components/article           # Article import, outline, evidence, script, and review UI
│   └── electron                         # Electron shell integration
├── scripts
│   ├── dev.sh                          # Local development startup
│   ├── verify.sh                       # Backend and frontend verification
│   └── seed_demo.py                    # Local demo project generator
└── docs                                # Architecture and handoff notes
```

The current production workflow is implemented with explicit SQL-backed service state instead of LangGraph. That choice keeps the interview project easier to inspect: the database tables are the source of truth, each workflow transition is visible in application services, and retry/review behavior can be tested without an additional graph runtime.

## Technical Stack

- Desktop/web shell: Electron, Vue 3, Element Plus, Vite
- Backend: FastAPI, SQLAlchemy, Pydantic, SQLite
- AI integration: OpenAI-compatible chat providers with structured JSON validation and fallback parsing
- TTS integration: Edge-TTS, DashScope-compatible TTS paths, and configurable HTTP providers
- Audio processing: FFmpeg-based local processing and export helpers
- Validation: Python tests plus frontend production build through `scripts/verify.sh`

## Design Highlights

- Separate prompts for production assistant, source parsing, role drafting, script writing, and script review. The production assistant does not inherit the novel-analysis prompt by accident.
- Structured-output guardrails around model responses, including schema validation, fallback normalization, and tests for malformed model output.
- Reviewer pass after initial script generation to enforce audio-drama adaptation rules before the user is asked to approve the final script.
- Evented workflow updates through WebSocket plus REST recovery, so long-running AI steps can still show visible progress in the UI.
- Audio take versioning at the line level, so regeneration is reversible and playback/export reads the user's selected take.
- Local provider snapshots for recovery from accidental provider configuration changes.

## Local Setup

Requirements:

- macOS or Linux development environment
- Python 3.12
- Node.js and npm
- FFmpeg

Start both backend and frontend:

```bash
./scripts/dev.sh
```

Expected local URLs:

```text
Frontend: http://127.0.0.1:5173
Backend:  http://127.0.0.1:8200
API docs: http://127.0.0.1:8200/docs
```

Run verification:

```bash
./scripts/verify.sh
```

Generate a local sample project without external AI/TTS providers:

```bash
SonicVale/.venv/bin/python scripts/seed_demo.py --reset
```

## Configuration

Runtime data is stored locally by default. The development script uses `.local-data` for project state, provider snapshots, logs, and generated workflow artifacts.

Common workflow flags:

```text
WORKFLOW_CHAT_UI_ENABLED=true
WORKFLOW_TTS_REVIEW_ENABLED=true
KNOWLEDGE_ARTICLE_ENABLED=true
KNOWLEDGE_ARTICLE_URL_ENABLED=true
KNOWLEDGE_ARTICLE_EXTERNAL_VERIFY_ENABLED=false
KNOWLEDGE_ARTICLE_VISION_ENABLED=false
DRAMA_WORKFLOW_MAX_ITERATIONS=8
DRAMA_WORKFLOW_MAX_SOURCE_CHARS=120000
DRAMA_WORKFLOW_MAX_DRAFT_CHARS=180000
CHAT_EVENT_REPLAY_LIMIT=100
```

Provider keys should be configured locally through the app or local environment files. Secrets, runtime databases, generated audio, virtual environments, and frontend build outputs are intentionally excluded from git.

## Verification Scope

`scripts/verify.sh` checks the parts most likely to break during product iteration:

- backend imports and syntax
- FastAPI route registration
- drama workflow services and structured model handling
- TTS guidance and audio version logic
- local demo project generation path
- Electron preload/main script syntax
- frontend production build

## License And Attribution

This repository contains substantial product, workflow, and UI changes for the Auralis prototype. It also retains components derived from the open-source SonicVale project:

https://github.com/xcLee001/SonicVale

SonicVale is distributed under AGPL-3.0. Keep the original attribution and comply with AGPL-3.0 obligations when distributing or deploying modified versions.
