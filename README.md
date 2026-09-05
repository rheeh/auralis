# Auralis

**简体中文** | [English](README_EN.md)

Auralis 是一个本地优先的 AI 广播剧生产工作台，可将小说等叙事文本转换为可编辑的广播剧项目。它将原文改编、人物设计、台本审查、音色分配、TTS 生成、音频版本管理和项目播放整合在一套桌面工作流中。

项目以完整生产闭环、清晰状态管理和可恢复的 AI 步骤为重点。用户可以在音频生成前检查并修正每一项关键输出，而不是接受一次性生成的黑盒结果。

## 在线体验

[▶ 体验《雨夜来件》导演 Demo](https://rheeh.github.io/auralis/#/demo)

原创都市悬疑短篇，约 46 秒真实成片。可以修改台词、对比同音色的有/无导演指导版本、试听 6 个候选声音、把音效加到指定台词附近并导出立体声 WAV。预置 22 个真实合成 take，无需配置后端或 API Key。修改文本后会提示重新配音，不冒充实时生成。

本地前端也可直接访问 `/#/demo`；`scripts/seed_director_demo.py` 可将相同素材导入独立制作工程。提示词评测仅允许 `qwen3.8-27b` / `kimi-k3`，实测与限制见[实验报告](evals/audio_drama_v2/REPORT.md)。[演示与验收记录](docs/demo-2026-09-05.md)包含操作路径与复现方法。

## 核心能力

- 将小说原文转换为“原文分析 → 人物草稿 → 台本初稿 → 独立审查 → 用户确认 → 正式写入”的广播剧工作流。
- 草稿与正式项目数据分离；用户确认前，不完整的 AI 输出不会污染生产数据。
- 显式展示台本迭代：初稿可先出现，随后呈现审查结果和返修版本，不把等待过程隐藏在黑盒中。
- 内置常驻制作助手，可处理修改场景、定位台词、更换音色、重新生成音频和检查缺失音频等自由指令。
- 支持定向返修，将反馈定位到相关人物、场景或台词，而不是盲目重跑整个流程。
- 逐句保存生成音频版本；重新生成不会覆盖旧版本，可选择当前用于播放和导出的版本。
- 内置 32 个 CC0 环境声与拟音素材，支持搜索、试听、上传，以及一键加入任意台词前后/同时，调整音量与淡入淡出。
- 提供持久化四轨时间线，可调整片段时间、时长、增益、淡入淡出和静音状态，并通过 FFmpeg 渲染章节 WAV。
- 明确展示 TTS 能力差异：云端模型可接收更丰富的声音指导；Edge-TTS 将指导近似映射为语速、音高和音量。
- 在单一项目工作台中完成原文、人物、台词、音色、生成队列、音频试听、连续播放和项目检查。

## 典型流程

1. 将小说原文粘贴给制作助手。
2. 确认或修改识别出的人物。
3. 生成第一版广播剧台本。
4. 由独立审查步骤检查旁白比例、内心活动外化和不可听视觉描述等问题。
5. 查看返修台本，并通过制作助手进行定向修改。
6. 将确认后的台本写入正式项目。
7. 分配人物音色，生成和比较逐句音频版本。
8. 在时间线上编排对白、旁白、音效和音乐，渲染并下载章节成片。

## 当前架构

Auralis 采用 Vue 3 + FastAPI + SQLAlchemy/SQLite 的本地优先架构。主改编流程由数据库状态机推进，制作助手是最多三轮“规划 → 工具执行 → 观察”的受控 Agent；项目事实、音频版本与流程检查点保存在数据库中。

正式制作统一在章节工作台完成：原文 → 人物与台本 → 配音 → 声音编排 → 导出，旧时间线与 Studio 链接会定位到对应项目。详见 [当前架构与本轮整合](docs/architecture-2026-09-05.md)。

## 项目结构

```text
.
├── SonicVale/app
│   ├── main.py                         # FastAPI 应用入口
│   ├── routers                         # 项目、台词、会话、Provider 与队列 API
│   ├── services                        # 工作流、助手、TTS、台本、人物与台词逻辑
│   ├── core                            # Provider 配置、LLM/TTS 引擎、WebSocket
│   └── models / entity / dto           # SQLAlchemy 模型与 API 数据结构
├── sonicvale-front
│   ├── src/pages                       # 桌面工作台页面
│   ├── src/components/workflow         # 助手、台本、人物与生产面板
│   └── electron                        # Electron 桌面壳
├── scripts
│   ├── dev.sh                          # 本地开发启动
│   ├── verify.sh                       # 后端与前端验证
│   └── seed_demo.py                    # 本地演示项目生成器
└── docs                                # 架构与交接文档
```

当前核心生产流程由显式 SQL 状态和服务层驱动，而不是 LangGraph。数据库表是流程状态的事实来源，每一次状态转换都可以在应用服务中检查，重试和审查逻辑也能在不引入额外图运行时的情况下测试。

## 技术栈

- 桌面与 Web：Electron、Vue 3、Element Plus、Vite
- 后端：FastAPI、SQLAlchemy、Pydantic、SQLite
- AI：兼容 OpenAI 协议的对话模型服务、结构化 JSON 校验与回退解析
- TTS：Edge-TTS、兼容 DashScope 的 TTS 路径和可配置 HTTP Provider
- 音频：基于 FFmpeg 的本地处理与导出
- 验证：Python 测试与 `scripts/verify.sh` 前端生产构建

## 设计要点

- 制作助手、原文解析、人物设计、台本写作和台本审查分别使用独立 Prompt。
- 对模型结构化输出进行 Schema 校验、回退归一化和异常格式测试。
- 初稿生成后执行独立审查，再交由用户确认最终台本。
- 长耗时 AI 步骤通过 WebSocket 推送进度，并使用 REST 进行状态恢复。
- 音频重新生成采用逐句版本管理，播放和导出读取用户选择的当前版本。
- 时间线以持久化片段坐标作为最终混音的事实来源，并生成可复现 Manifest 和过期检测信息。
- 本地保存 Provider 配置快照，用于恢复误操作造成的配置变化。

## 本地运行

环境要求：macOS 或 Linux、Python 3.12、Node.js、npm 和 FFmpeg。

启动后端和前端：

```bash
./scripts/dev.sh
```

默认地址：

```text
前端:     http://127.0.0.1:5173
后端:     http://127.0.0.1:8200
API 文档: http://127.0.0.1:8200/docs
```

运行完整验证：

```bash
./scripts/verify.sh
```

构建 GitHub Pages 使用的静态 Demo：

```bash
cd sonicvale-front
npm run build:demo
```

无需外部 AI/TTS Provider 生成本地样例项目：

```bash
SonicVale/.venv/bin/python scripts/seed_demo.py --reset
```

## 配置

运行数据默认保存在本地。开发脚本使用 `.local-data` 保存项目状态、Provider 快照、日志和工作流产物。

常用工作流配置：

```text
WORKFLOW_CHAT_UI_ENABLED=true
WORKFLOW_TTS_REVIEW_ENABLED=true
DRAMA_WORKFLOW_MAX_ITERATIONS=8
DRAMA_WORKFLOW_MAX_SOURCE_CHARS=120000
DRAMA_WORKFLOW_MAX_DRAFT_CHARS=180000
CHAT_EVENT_REPLAY_LIMIT=100
```

Provider 密钥应通过应用界面或本地环境文件配置。密钥、运行数据库、生成音频、虚拟环境和前端构建产物不会提交到 Git。

## 验证范围

`scripts/verify.sh` 检查后端导入与语法、FastAPI 路由注册、广播剧工作流与结构化模型输出、TTS 声音指导与音频版本逻辑、本地 Demo 生成路径、Electron 脚本语法和前端生产构建。

## 许可证与来源

本仓库包含 Auralis 原型的大量产品、工作流和界面改造，同时保留了来自开源项目 [SonicVale](https://github.com/xcLee001/SonicVale) 的组件。

SonicVale 使用 AGPL-3.0 许可证。分发或部署修改版本时，请保留原始署名并遵守 AGPL-3.0。
