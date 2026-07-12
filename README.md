# Auralis

本项目是基于开源项目《音谷 SonicVale》的个人二次开发版本，用 SonicVale 的多角色配音、角色库、音色绑定、批量生成、FFmpeg 音频处理能力作为底座，并加入“小说改编为广播剧工程”的 Agent 工作流。界面信息架构参考 Fish TTS Workshop 的桌面制作台形态，但不复制其代码或素材。

## 架构

- `SonicVale/app`：FastAPI 后端，保留 SonicVale 原有项目、章节、角色、音色、台词、TTS 队列、音频处理模块。
- `sonicvale-front`：Electron + Vue + Element Plus 前端，新增 Studio / Scripts / Roles / Voices / Media / Queue / Settings 工作区导航。
- `SonicVale/app/workflows/drama`：LangGraph 单章改编图、人工确认节点与 SQLite checkpoint。
- `SonicVale/app/services/drama_workflow_service.py`：会话恢复、动作校验、草稿版本和事件发布。
- `SonicVale/app/routers/chat_router.py`：对话式改编会话 API；旧 `drama_adaptation_router.py` 继续保留。

## 新增能力

- 可恢复的对话式改编：解析原文 → 确认角色 → 确认剧本 → 幂等写入项目。
- 草稿与正式项目隔离：确认前只写会话、revision 和 checkpoint，不创建正式角色或台词。
- 会话级 WebSocket：`/ws/projects/{project_id}/sessions/{session_id}`，支持事件序号和 REST 补发。
- Studio 默认使用对话式模式，并保留“结构化编辑”作为旧链路回退入口。

- 三阶段广播剧 Agent：
  - 解析小说：剧情、人物、场景、冲突、声音线索。
  - 生成台本：分场、台词、旁白、音效、BGM。
  - 整理可播语言：稳定输出人物声、旁白、音效、BGM 多轨结构。
- 广播剧台词扩展字段：
  - `line_type`: `dialogue | narration | sfx | bgm`
  - `track`: `voice | narration | sfx | bgm`
  - `should_speak`: 人物/旁白朗读，音效/BGM 不朗读
  - `scene_title`, `sound_prompt`, `voice_profile`, `production_note`
- 改编运行记录 `adaptation_runs`，保存解析结果、台本草稿、最终工程 JSON、错误信息和写入状态。
- Studio 页面可把小说正文改编为广播剧工程，支持立即写入项目，也支持先预览再写入。
- Queue 页面读取后端 TTS 队列状态，展示广播剧改编运行历史、最近音频任务和失败任务，并可返回对应会话处理。
- Media 页面按项目/章节查看已生成音频素材。
- Roles 页面按项目查看角色和音色绑定状态。
- Timeline 页面按人物声、旁白、音效、BGM 四条轨道查看章节片段。

## 在终端启动项目

### 推荐：一条命令同时启动前端和后端

打开 macOS 的“终端”应用，复制执行：

```bash
cd /Users/go/Desktop/sonic-drama-studio
./scripts/dev.sh
```

第一次启动时，脚本会自动完成以下工作：

- 检查 Python 3.12。
- 创建或复用 `SonicVale/.venv` Python 虚拟环境。
- 安装后端依赖。
- 检查并安装前端依赖。
- 同时启动 FastAPI 后端和 Vue 前端。

看到下面两类提示后，说明启动完成：

```text
Uvicorn running on http://127.0.0.1:8200
Local: http://127.0.0.1:5173/
```

然后在浏览器打开：

- 前端界面：[http://127.0.0.1:5173](http://127.0.0.1:5173)
- 后端接口文档：[http://127.0.0.1:8200/docs](http://127.0.0.1:8200/docs)

启动项目的终端窗口必须保持打开。需要停止项目时，在该终端按：

```text
Control + C
```

如果提示 `permission denied: ./scripts/dev.sh`，先执行一次：

```bash
cd /Users/go/Desktop/sonic-drama-studio
chmod +x scripts/dev.sh
./scripts/dev.sh
```

后端工作流固定使用 Python 3.12。`scripts/dev.sh` 会优先寻找 Homebrew 的
`python@3.12`，并在解释器版本变化时重建项目虚拟环境。本地数据库、日志和工作流文件默认保存在项目根目录的 `.local-data`。

可通过环境变量控制工作流：

```text
LANGGRAPH_ENABLED=true
LANGGRAPH_CHAT_UI_ENABLED=true
LANGGRAPH_CHECKPOINT_DB=./auralis-checkpoints.sqlite3
DRAMA_GRAPH_MAX_ITERATIONS=8
DRAMA_GRAPH_MAX_SOURCE_CHARS=120000
DRAMA_GRAPH_MAX_DRAFT_CHARS=180000
CHAT_EVENT_REPLAY_LIMIT=100
```

### 分别启动前端和后端

一般使用上面的一键命令即可。如果需要分别观察日志，可以打开两个终端窗口。

终端一：启动后端

```bash
cd /Users/go/Desktop/sonic-drama-studio
export AURALIS_CONFIG_DIR="$PWD/.local-data"
cd SonicVale
.venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8200
```

终端二：启动前端

```bash
cd /Users/go/Desktop/sonic-drama-studio
npm --prefix sonicvale-front run dev -- --host 127.0.0.1 --port 5173
```

分别启动的方式假设项目已经执行过一次 `./scripts/dev.sh`，因此 `.venv` 和 `node_modules` 已经准备好。如果这是第一次运行项目，请先使用推荐的一键启动方式，不需要手动创建虚拟环境或逐项安装依赖。

如果只有前端依赖缺失，可以单独执行：

```bash
cd /Users/go/Desktop/sonic-drama-studio
npm --prefix sonicvale-front install --registry=https://registry.npmmirror.com
```

### 启动 Electron 桌面端

```bash
cd /Users/go/Desktop/sonic-drama-studio
npm --prefix sonicvale-front run start
```

如果出现 `Electron failed to install correctly`，说明前端依赖曾用 `--ignore-scripts` 安装，Electron 二进制没有下载。确认你接受 Electron 官方安装脚本后，在项目根目录执行：

```bash
npm --prefix sonicvale-front install --registry=https://registry.npmmirror.com
```

开发模式下 Electron 会优先复用 `http://127.0.0.1:8200` 上已运行的后端；如果没有检测到后端，会使用 `SonicVale/.venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port 8200` 自动启动，并把本地数据写入 `.local-data`。

### 无法访问 5173 或 8200

先确认服务是否正在监听：

```bash
lsof -nP -iTCP:5173 -sTCP:LISTEN
lsof -nP -iTCP:8200 -sTCP:LISTEN
```

如果两条命令都没有输出，说明项目没有运行，重新执行：

```bash
cd /Users/go/Desktop/sonic-drama-studio
./scripts/dev.sh
```

如果提示端口已被占用，先查看上面 `lsof` 输出中的 PID，再停止对应的旧进程：

```bash
kill <PID>
```

例如 PID 是 `12345`：

```bash
kill 12345
```

不要直接关闭终端后仍期待开发服务继续运行；电脑重启后也需要重新执行启动命令。

## 验证

```bash
./scripts/verify.sh
```

验证内容：

- Python 关键后端模块语法检查
- FastAPI 应用导入和新增路由检查
- 本地样例广播剧工程写入、多轨静音素材生成和导出检查
- Electron 主进程、预加载脚本和日志脚本语法检查
- 前端生产构建

## 本地样例工程

不配置任何外部 LLM/TTS 时，也可以生成一个完整的本地样例工程，用于检查 Studio 后续制作链路、多轨素材库、导出清单和结果音频：

```bash
SonicVale/.venv/bin/python scripts/seed_demo.py --reset
```

脚本会创建 `Auralis Demo Project`，写入人物声、旁白、音效、BGM 四类轨道，生成占位 WAV，并导出 `result.wav`、`all_lines.xlsx` 和 `production_manifest.json`。

## TTS 兼容配置

TTS 不再只依赖模型名猜接口。建议在 `自定义参数` 里显式写 `driver`：

- `dashscope_cosyvoice`：阿里云百炼 CosyVoice，走 DashScope SDK/WebSocket。
- `dashscope_sambert`：阿里云 Sambert，走 DashScope 旧 TTS SDK。
- `http`：通用 HTTP 厂商，适合 OpenAI-compatible 或其它 REST TTS。

CosyVoice 示例：

```json
{
  "driver": "dashscope_cosyvoice",
  "voice": "longxiaochun",
  "format": "mp3"
}
```

其它 HTTP 厂商示例：

```json
{
  "driver": "http",
  "endpoint": "https://example.com/v1/audio/speech",
  "auth_header": "Authorization",
  "auth_prefix": "Bearer ",
  "payload": {
    "model": "{{model}}",
    "input": "{{text}}",
    "voice": "{{voice}}"
  },
  "audio_url_path": "data.audio_url",
  "audio_base64_path": "data.audio_base64"
}
```

如果厂商返回的是二进制音频，配置好 `endpoint` 和 `payload` 即可；如果返回 JSON，可用 `audio_url_path`、`audio_base64_path` 或 `audio_path_path` 指定音频字段路径。常见鉴权头可用 `auth_header` 和 `auth_prefix` 配置，不需要把 API Key 写进 JSON 参数。

LLM/TTS Provider 每次创建、更新、删除都会写入本机快照：

```text
~/Auralis/backups/provider_config_snapshots.jsonl
```

该文件用于恢复误删、误覆盖的 Base URL、模型、API Key 和自定义参数；它只在本机保存，不会显示到界面或日志。换新厂商时优先新增一个 Provider 做测试，测试通过后再切换项目绑定，不要直接覆盖原来的可用配置。

## 使用路径

1. 在配置中心配置 LLM Provider、TTS Provider、模型和项目保存路径。
2. 创建项目或点击已有项目，直接进入该项目的单页工作台。
3. 在左侧对话框粘贴小说正文并发送给 AI。
4. 在右侧确认主要角色身份卡；不满意时在左侧直接提出修改意见。
5. 确认角色后检查广播剧台本、对白、旁白比例、音效和 BGM。
6. 台本满意后，在同一页面逐句绑定角色音色；也可以让 AI 自动分配互不重复的音色。
7. 在每句台本旁生成、试听和重做对应音频；任务页面用于查看全局生成状态和失败任务。

## 授权和署名

本软件基于开源项目《音谷》二次开发，原项目地址：

https://github.com/xcLee001/SonicVale

原项目采用 AGPL-3.0。继续分发、网络部署或发布修改版时，需要遵守 AGPL-3.0，并保留原项目署名。Fish TTS Workshop 仅作为产品信息架构参考。
