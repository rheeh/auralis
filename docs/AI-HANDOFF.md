# Auralis 项目交接文档

> 状态日期：2026-07-31
> 工作目录：`/Users/go/Desktop/sonic-drama-studio`
> 当前分支：`master`
> 当前默认远端：`github` -> `git@github.com:rheeh/auralis.git`
> 公开仓库：https://github.com/rheeh/auralis
> 旧远端保留：`origin` -> `https://gitee.com/green1149/auralis-studio.git`
> 最新提交：接手时执行 `git log -1 --oneline`，不要依赖交接文档中的静态提交号

本文档给下一位 AI 助手接手执行用。它不是聊天总结，所有判断都应以当前 checkout 为准。

## 2026-09-07 TTS 选型与模型分组选音色

- 后续音乐素材：新增 4 首经来源页核对的 CC0 完整配乐及 2 条 CC0 笑声，内置可见素材 85 条；来源及哈希在 `assets/audio/cc0/`，抓取脚本 `scripts/add_stock_bgm.py` / `scripts/add_stock_laughter.py`。素材库新增「背景音乐」「笑声反应」快捷筛选并显示作者；已有 BGM 入轨流程复用。当前雨夜 Demo 的持续背景是 alxl 的 Rain on Window Loop，不是歌曲，原 Demo 音频保持不变。
- 角色笑声修复：共享改编规则要求明确角色的笑声、叹息沿用角色 voice，仅背景群体笑声归 sfx；括号清洗将轻笑等表演提示放入 productionNote，不再一律变为音效。纯括号轻笑转为“呵。”，大笑转为“哈哈。”，保留发声角色。无需重新运行旧台本。
- 工作台 `ProductionScriptPanel` 每行新增「修改类型 / 角色」，调用 `PUT /lines/{id}/type`，可转人物/旁白/音效/BGM、选角色及编辑文本/指导。验证章节/角色归属并阻止 queued/processing 时修改；旧完整行与音频引用存至本地 `line_type_history/`，旧音频文件不改。转换清除当前音频及事件/版本选用，人物行分配独立新输出路径，标记 pending、编排 stale，等待重新配音/选素材。仅隔离测试自动执行转换；不擅自转换用户正在制作的台词。
- 用户取消 MiniMax 接入，未增加相关配置或调用路径。官方音乐 API 2026-08-20 已停止向新用户开放且免费接口停服，历史付费用户可继续使用；依据 https://platform.minimaxi.com/docs/api-reference/music-generation 于 2026-09-07 现场读取，勿沿用搜索缓存中的免费版本描述。

- 现场核对北京账户：Qwen-Audio 3.0 Plus / Flash 和 CosyVoice v1 有免费额度，较新 CosyVoice、旧 Qwen3-TTS / MiniMax 当前无免费额度。精确余额和期限仅保存在 `.local-data/voice-setup-20260907.json`，不视为其他账户的免费承诺。
- 本地新增 Plus / Flash 两个配置，优先级最高；按官方音色表选 10 种基础音色供两模型分别使用，加系统音色共 27 条。官方音色前缀必须匹配模型。官方试听文件只保存在本地；又用两个模型各新生成一条同文中文试听，5.256 / 9.096 秒，未替换项目角色或已有配音。选型依据是免费额度、中文角色描述及表演指令能力，不宣称已经人工评定自然度最优。
- `ModelVoicePicker.vue` 用于人物草稿和已确认人物卡；所有模型默认收起、点击展开，Edge 同模型配置并组但保留音色 ID，搜索自动展开匹配项，独立试听不改变绑定。无额度的旧配置标明状态；草稿自动绑定避开已标无额度的配置。
- 音色管理默认打开优先模型，增加「从参考录音复刻」。当前仅接入北京 Qwen-Audio Plus / Flash / CosyVoice v1 的公开 HTTPS 音频链接；不把本地文件路径当作上传成功。创建使用 voice-enrollment，返回的 ID 存入现有音色描述标记，云端回执及授权来源留在本地；失败不重试，回执可避免本地保存失败后重复创建。
- 隔离测试覆盖云端失败、授权字段、模型约束和回执复用；真实浏览器验证模型收起/展开、搜索、试听以及复刻表单。完整验证 117 项后端 + 15 项前端检查通过。变更前 203 个音频哈希未变。
- 用户随后明确批准两段 Kyutai CC0 参考录音（0a67 / 1410）提交阿里云北京；已创建 Plus 复刻音色，本地 ID 72、73。原 Hugging Face 链接下载失败，换成同一文件的原站 CDN 直链成功。回执保留本地，不重复创建。
- 用户偏好自然对白、不要播音腔。选角面板新增用途筛选，自然对白优先，电台/朗读类排后，复刻单列待试听；这些是描述分类而非听感评分。两种复刻与四种官方对白候选已按同文同指令生成独立试听，私人 `测评库/2026-09-07-音色选型/自然对白对照/` 提供试听页及参数，不进入 Demo 或 Git。未修改已有项目配音或角色绑定。
- 官方资料：<https://help.aliyun.com/zh/model-studio/qwen-audio-tts-voice-list>、<https://help.aliyun.com/zh/model-studio/voice-clone-design-http-api>、<https://help.aliyun.com/zh/model-studio/voice-cloning-user-guide>。代码内基础音色元数据来自官方 Excel，音频未随代码发布。

## 2026-09-07 标签检索替代音效推荐

- 台本生成在原有编剧请求中产出 `soundTags`，按统一词表归一；提交时保存至 `lines.sound_tags`。SQLite migration 5 为旧数据库无损添加字段。旧行缺少标签时按声音描述本地提取，不重新调用模型；修改音效文本时更新提取标签。
- `POST /sound-library/matches` 进行本地标签排序，优先声源，显示命中/缺失标签。`PUT /sound-library/lines/{id}/tags` 保存用户修改，不动音频和时间线。旧 `/recommendations` 接口也转接本地匹配，刷新前的客户端不会产生新模型请求。
- 工作台入口改为「标签匹配音效」，移除模型选择器；标签可修改、保存或转到全库。全库标签可点击，多个关键词采用 AND；公共 Demo 同步展示样片标签与快速筛选。
- 内置库新增 29 个外部 CC0 声音和 2 个现有原创 Demo 拟音，补充键盘、动物、交通、心跳/呼吸、拉链、锁具、抽屉、厨房/卫生间等；24 个同类编号变体从列表归档，保留原路径/ID兼容旧项目。默认 79 个，Demo 默认 55 个；未发现字节完全相同的文件，不把同类变体称为相同录音。来源、数量、归档清单见 `assets/audio/cc0/curation-20260907.json` 和 `LICENSES.md`。
- 库标签改为逐文件维护，不继承会导致声源混淆的分类标签。匹配依据是标签，不声称已经听辨音频；特定节奏仍需试听。Demo 的台词标签是审定样片配置，实际项目标签来自解析结果/用户保存。
- 验证：114 项后端、14 项前端检查、完整 verify smoke 和静态 Demo 构建通过；覆盖解析标签归一、提交持久化、旧数据迁移、无模型匹配、未知标签/空标签、旧接口转接、标签修改不动音频、归档素材旧 ID 可读。真实浏览器已验证旧台本拉链匹配、键盘标签筛选与 6.25 秒素材完整播放、Demo 的 55 项列表及本句纸张匹配；变更前 187 个音频 SHA256 不变。

## 2026-09-07 旧项目修复与场景插画

- 后续现场修复：旧知识音频项目仍有 `article_sources` / `knowledge_review_answers` 外键引用会话；删除时仅在这些已知旧表存在时反射并清理目标记录，不为新安装重新建表。数据库异常转为带 CORS 的可读 409 响应，保留回滚和文件保护。110 项后端、14 项前端检查通过，当前数据库隔离副本中 7 个现有项目（含知识音频项目）逐一删除通过；真实项目不用于删除测试。
- 修复台本音效抽屉 `min(900px,95vw)` 被 Element Plus 解析为零宽度的问题；改用百分比尺寸和 CSS 最大宽度。旧项目的 AI / 手动入口已在浏览器验证。
- 项目删除集中到 ProjectService：按外键依赖顺序在同一事务中删除，先隔离目录，提交失败恢复目录；音频生成中的项目拒绝删除。独立测试覆盖历史外键失败、文件权限失败、提交失败、运行任务与缺省目录。
- 内置音效从 32 扩充到 72 个；静态 Demo 音效从 7 扩充到 47 个；新增 40 个来自 rubberduck 的 CC0 素材，来源和校验和随库记录。压缩音频元数据按文件大小和修改时间缓存。
- 内置 image_gen 生成《雨夜来件》3 张场景图，文件与完整提示词在 `sonicvale-front/public/demo-night/scenes/`。Demo 按实际配音版本的台词时间切图；本地工程成片按实际时间线台词锚点切图。仅为该样片接入插画，不给其他小说套用。
- 推荐请求后端限时 150 秒，前端 180 秒；避免先前前端 90 秒超时而后台成功。仍仅允许 qwen3.8-27b / kimi-k3，单次调用与缓存复用。
- 验证：108 项后端、14 项前端测试及完整 verify smoke 通过；旧项目 test4 两入口和 72 项列表、真实 qwen3.8-27b 推荐、Demo 自动切图与回跳、本地样片时间线场景定位已验证。变更前 179 个音频 SHA256 均保持原样。

## 2026-09-05 音效库与情节推荐

- 本地侧栏新增「音效库」`/#/sound-library`，可浏览 32 个内置 CC0 素材、搜索、试听和导入个人音频。公共静态 Demo 继续使用随附音效，不连接模型。
- 台本音效行与时间线提供「AI 推荐音效」和手动挑选入口；根据小说原文、当前音效提示和前后台词推荐真实库内素材，说明匹配或近似差异，用户选择后才替换或加入。
- `POST /sound-library/recommendations` → `SoundRecommendationService`，仅允许 `qwen3.8-27b` / `kimi-k3`；单次请求、不自动重试、不因额度失败切换模型。当前本地 qwen3.8-27b 已真实验证；Kimi 需用户配置对应服务商。
- 推荐缓存位于配置目录 `sound_recommendations/`；原文、台词、候选目录、模型变化后失效，手动「重新推荐」绕过缓存。缓存不进入 Git。
- MP3 等压缩素材元数据由共用 `audio_metadata.probe_audio` 的 FFprobe 子进程探测，规避 macOS libsndfile MPEG 并发初始化崩溃；选择素材用独立副本，保留以前的文件。原位替换同步目标音轨素材，保留位置与混音，短素材限制片段长度；其他片段不变，成片需重新渲染。

## 2026-09-05 章节工作台整合

- 以 [当前架构说明](architecture-2026-09-05.md) 为本次整合依据：一个章节工作台承载五个视图，旧 `/timeline` 和 `/studio` 路由作兼容跳转。
- 后台仍是数据库工作流 + 制作助手 Agent。旧结构化生成 API 标记弃用并保留兼容，新 UI 不再调用。
- 实际声音配置与模型能力来自后端；共用音频选择规则，换音色或改指导会标记需重新配音，Agent 与界面操作遵循相同规则。
- TTS 工作者不再导入 routers；个人测评库和原音频保持原约束。

## 2026-09-05 增量状态

- 新演示入口 `/#/demo`：《雨夜来件》导演审定稿、22 个真实 A/B take、6 个候选试音、音效编排和浏览器 WAV 导出。见 [本次验收](demo-2026-09-05.md)。
- 本地真实工程由 `scripts/seed_director_demo.py` 导入；不覆盖已有项目、不请求云端。历史 `scripts/seed_demo.py` 仍是静音流程 smoke，不当作听感样片。
- 用户明确禁止后续使用 `qwen-plus`；LLM 评测和 Demo 新建项目仅选择 `qwen3.8-27b` / `kimi-k3`，默认前者。历史错误调用保留型号和用量记录；不能混入新型号结果。真实评测受 `Arrearage` 限制，详见 [实验报告](../evals/audio_drama_v2/REPORT.md)。
- 修复旧 Qwen3 TTS 的 `input.instructions`、CosyVoice 倍率和音色级能力判断；接入免费 `qwen-audio-3.0-tts-plus/flash` 独立协议（`input.instruction`）。原 28 个音频与 manifest 保留，新增 3 条免费短句候选使用独立文件。TTS 型号独立于上述 LLM 型号约束，已合成的 Demo 试听不消耗额度。
- 音效库增加 `POST /sound-library/assets/{asset_id}/insert`，可按原始台词锚点加入，持久化加入意图并保护手动时间线。前端工作台和时间线均有入口。

下文为先前基线；发生冲突时以上述增量和当前代码为准。

## 1. 项目背景和最终目标

Auralis 是一个本地优先的 AI 广播剧制作工作台，用于把小说或叙事文本改编成可审查、可修改、可配音、可连播的音频项目。

最终目标不是做一个通用 Agent 框架，也不是扩展成平台型产品，而是形成一个能给面试官展示的完整 AI 产品原型：

- 用户在一个项目工作台内提交小说正文。
- AI 完成小说解析、人物草稿、广播剧台本初稿、独立审查和必要返修。
- 用户能看到中间产物和每轮迭代，而不是只看到一个漫长等待。
- 用户能通过左侧制作助手自由提出修改意见，由系统定位到角色、场景或台词再修改。
- 用户确认后再写入正式项目，避免未确认草稿污染项目数据。
- 每句台词可以绑定音色、生成 TTS、重生成多个 take、选择当前版本、连播和导出。

产品表达上要清楚：Auralis 是“AI 广播剧制作助手”，不是单纯的小说朗读器，也不是只会线性跑流程的工作流 Demo。

## 2. 当前任务和优先级

当前项目已经进入面试展示整理阶段。下一位助手不要默认继续大规模扩展，优先级如下：

| 优先级 | 任务 | 当前状态 | 下一步标准 |
|---|---|---|---|
| P0 | 保持项目可启动、可验证、可演示 | 已通过 `./scripts/verify.sh` | 任意改动后至少运行相关测试；较大改动跑全量 verify |
| P0 | 保持 README 和交接文档准确 | README 已重写，本文档已更新 | 不要再以“基于某项目二次开发”作为 README 开头 |
| P0 | 稳定主流程：解析 -> 角色确认 -> 台本初稿 -> 审查/返修 -> 用户确认 -> 写入项目 | 已实现 | 修 bug 时不要重新引入 LangGraph |
| P0 | 制作助手自由对话和工具调用 | 已实现 `ProductionAssistantService` | 后续只做能力补强，不要把小说解析提示词混进助手对话 |
| P0 | 音频版本管理 | 已实现生成 take 和后期处理版本 | 修复时确保原音频不被覆盖 |
| P1 | UI 继续收敛为工作台体验 | 已完成一轮重构 | 不要添加解释性大横幅或过多固定栏 |
| P1 | 真实模型/TTS 适配 | 已做能力分层 | 新 provider 必须明确能力差异 |

当前用户偏向“面试可展示、结构清楚、不要过度扩展”。任何新任务都要服务这个目标。

## 3. 已完成的工作和关键产出

### 3.1 架构调整

- 已去掉 LangGraph 运行架构。
- `SonicVale/app/workflows/drama/graph.py`、`checkpoint.py`、`state.py` 已删除。
- 主流程改为 SQLAlchemy 数据库状态机和显式 service 编排。
- 数据库会话、adaptation run、draft revision 是业务状态源，不再依赖额外 graph checkpoint。
- `docs/auralis-langgraph-implementation-plan.md` 仍保留为历史方案文档，只能用于理解背景，不能当作当前实现。

关键文件：

- `SonicVale/app/services/drama_workflow_service.py`
- `SonicVale/app/services/chat_session_service.py`
- `SonicVale/app/services/source_parser_service.py`
- `SonicVale/app/services/role_draft_service.py`
- `SonicVale/app/services/script_draft_service.py`
- `SonicVale/app/services/script_review_service.py`
- `SonicVale/app/services/workflow_llm_service.py`

### 3.2 制作助手

- 已新增常驻制作助手：`SonicVale/app/services/production_assistant_service.py`。
- 制作助手用于自由对话、定位用户修改意图、调用项目/角色/台词/音频相关工具。
- 用户可以在左侧输入框提出修改意见，不再只依赖右侧按钮点击。
- 输入框按钮已简化为“发送”，不再显示冗长的“发送给制作助手”。
- 顶部固定的“制作助手”栏已按用户要求移除或压缩，不再浪费空间。

重要决策：

- 制作助手可以复用项目配置中的通用 LLM provider/model。
- 但制作助手、小说解析、角色设计、台本生成、台本审查必须使用各自独立的 system prompt。
- 每轮对话不能自动带入小说解析 prompt，避免自由对话变成“解析小说任务”。

### 3.3 小说改编和审查流程

主流程已调整为：

```text
小说输入
  -> source parser 解析原文
  -> role draft 生成人物草稿
  -> 用户确认或修改角色
  -> script draft 生成第一版台本
  -> script reviewer 审查广播剧规范
  -> 如有问题，编剧按审查报告返修
  -> 用户看到初稿、审查状态和修订结果
  -> 用户确认台本
  -> 幂等写入正式项目
```

广播剧审查重点：

- 零旁白优先，能用角色对话表达的不要写旁白。
- 所有信息尽量转成可听元素：对白、音效、动作声、沉默、环境声。
- 听众视角按“看不到画面”处理。
- 心理活动应外化成台词、呼吸、沉默或动作声。
- 视觉描述要删除或转化为可听内容。
- 时间跳转必须有听觉标记。

已修复的结构化输出问题：

- `SourceAnalysis` 收到 `[]` 时不再直接崩溃。
- `RoleDraftList` 收到 `characters` 而不是 `roles` 时有兼容处理。
- 工作流对空数据、非字典模型输出、字段缺失有更清晰的兜底和错误信息。

相关测试：

- `SonicVale/tests/test_drama_workflow.py`
- `SonicVale/tests/test_workflow_llm_service.py`
- `SonicVale/tests/test_llm_engine_messages.py`
- `SonicVale/tests/test_audio_drama_prompts.py`

### 3.4 TTS 指导和模型能力适配

已新增：

- `SonicVale/app/core/tts_guidance.py`
- `SonicVale/app/core/tts_runtime.py`
- `SonicVale/tests/test_tts_guidance.py`
- `SonicVale/tests/test_tts_engine_capabilities.py`

当前策略：

- Cloud TTS 根据 provider 能力接收 richer instruction 或结构化指令。
- Edge-TTS 不理解自然语言表演提示，不支持精细情绪语义和分段停顿。
- Edge-TTS 只能近似映射整句 `rate / pitch / volume`。
- UI 文案应明确区分：声音指导对不同模型的效果不同。

强度含义已确定：

- 强度指“情绪/表达强度”，不是音量。
- 例如同样是“愤怒”，强度越高，表达越激烈；落到不同模型时由能力映射决定。

情绪候选已扩展，不应只保留“平静/开心/生气”这种窄集合。

### 3.5 音频版本管理

已实现两层版本概念：

- TTS 重新生成的 take：保留多个生成版本。
- 后期处理版本：基于当前 take 做速度、音量、局部变速等处理。

用户要求的能力已经落地：

- 每句音频处显示版本序号，例如 `版本 n/N`。
- 有多个版本时可用下拉框选择当前采用版本。
- 播放、连播、后期处理、导出应读取当前采用版本。
- 重新生成不会破坏旧版本。

关键文件：

- `SonicVale/app/services/line_service.py`
- `SonicVale/app/routers/line_router.py`
- `SonicVale/app/entity/line_entity.py`
- `SonicVale/app/dto/line_dto.py`
- `sonicvale-front/src/api/line.js`
- `sonicvale-front/src/components/workflow/ProductionScriptPanel.vue`
- `SonicVale/tests/test_audio_variants.py`

### 3.6 UI 重构

已按用户反馈完成一轮工作台 UI 收敛：

- 下方连播控件不再过度突兀。
- 左侧发送按钮文案简化为“发送”。
- 用户气泡不再使用渐变。
- 制作助手顶部固定栏已移除或压缩。
- 助手区和侧边栏之间的浪费空白已减少。
- 侧边栏收缩展开箭头缩小，减少占位。

相关文件：

- `sonicvale-front/src/App.vue`
- `sonicvale-front/src/pages/ProjectWorkspace.vue`
- `sonicvale-front/src/components/workflow/ChatComposer.vue`
- `sonicvale-front/src/components/workflow/ChatMessageList.vue`
- `sonicvale-front/src/components/workflow/ChatProductionPanel.vue`
- `sonicvale-front/src/components/workflow/ProductionScriptPanel.vue`
- `sonicvale-front/src/components/workflow/ScriptDraftConfirmCard.vue`
- `sonicvale-front/src/components/workflow/SessionStageStepper.vue`

### 3.7 Auralis 0.3.2：真实时间线正确性与前端坐标

- 时间线页面通过真实时间线 API 展示 `start_ms`、`duration_ms`、音频资产状态和构建状态，不再按文字长度估算片段宽度。
- SQLite 已改为版本化迁移入口 `SonicVale/app/db/migrations.py`，当前 schema version 为 4；历史字段迁移集中管理，`main.py` 不再继续堆叠 `add_*_column()`。
- 新增 `AudioAssetPO`、`TimelineTrackPO`、`TimelineClipPO`，保留现有 `lines.audio_path`、`audio_versions` 和 `audio_variants` 作为兼容来源。
- `TimelineService` 会探测真实音频时长，按人物声、旁白、音效、BGM 四条固定轨道生成章节时间线。
- 新增只读接口 `GET /projects/{project_id}/chapters/{chapter_id}/timeline` 和显式构建接口 `POST /projects/{project_id}/chapters/{chapter_id}/timeline/build`。
- 时间线支持 `not_built`、`building`、`ready`、`stale`、`missing_audio`、`failed` 状态；台词、音频版本或素材变化会通过失效钩子和来源指纹标记旧结果。
- 删除台词、章节、项目或替换章节台词时会清理轨道、片段和音频资产；SQLite 连接已启用外键约束。手工编辑片段默认受保护，只有显式 `overwrite_manual=true` 才允许重建覆盖。
- 空轨道只有在该轨道确实存在台词且其中有台词缺少音频时才显示 `missing_audio`；正常空轨道显示为 `ready`。
- `AudioAsset` 是项目级共享资源，`TimelineClip` 承担引用关系；删除台词/章节/项目时只删除无任何片段引用的资产。BGM、环境音等跨章节复用由测试覆盖。
- 多轨时间线使用统一时间坐标画布：所有轨道共享同一标尺，片段位置由 `start_ms × scale`，宽度由 `duration_ms × scale` 计算。
- 数据库迁移失败会阻止应用继续启动，避免半迁移状态继续对外提供 API。
- Auralis 0.4 已实现参数式片段编辑、重叠编排、拖拽移动、左右边缘裁剪和混音导出；拖拽操作按 100 ms 吸附并复用现有片段 PATCH 校验，波形显示仍未实现。旧的按台词顺序导出仅保留为兼容路径，不能冒充时间线渲染。

### 3.8 README 和 GitHub 同步

- README 已重写为英文面试项目说明。
- README 开头直接介绍 Auralis，不再第一句话强调“基于某项目改编”。
- 许可与原项目署名保留在末尾的 `License And Attribution`，满足合规但不喧宾夺主。
- GitHub 仓库已创建并推送：`https://github.com/rheeh/auralis`。
- 用户已明确表示仓库可以保持 public，不再继续做 private 切换。
- 本地 `master` 已跟踪 `github/master`。

### 3.9 Auralis 0.3.3：共享音效素材库

- `assets/audio/cc0/` 内置 32 个 CC0 环境音和拟音文件，包含来源、作者、许可、分类、中英文标签和 SHA-256 清单。
- “音频素材库”页面分为“项目素材”和“共享素材库”：可按内置/我的素材、分类和标签筛选，并通过后端接口试听。
- 用户可在 Electron 中选择本地音频，或在浏览器模式上传 wav/mp3/m4a/ogg/flac；文件会复制到 `Auralis/sound_library/user/`，数据库保存管理信息。
- 用户素材使用独立的 `SoundLibraryAssetPO`，不复用时间线 `AudioAssetPO`，避免项目生命周期误删共享原件。
- 内置素材只读，用户素材可删除；删除素材库原件不影响已经复制到项目中的音频。
- 素材只能绑定到音效或 BGM 台词。绑定继续调用 `LineService.attach_audio_asset()`，会清除占位标记、更新台词状态并使旧时间线失效。
- 固定资产以常用环境音和拟音为主，不内置版权边界较复杂的商业 BGM；用户可自行导入合法音乐素材。
- Electron 打包通过 `extraResources` 携带固定素材，并给后端设置 `AURALIS_STOCK_AUDIO_DIR`；不能只验证源码目录下的开发路径。

### 3.10 Auralis 0.4.0：时间线驱动的真实混音导出

- 多轨页面已正式命名为“多轨时间线”。点击片段可编辑开始时间、片段长度、音量、静音、淡入和淡出；编辑结果持久化到 `TimelineClipPO`，并把轨道标记为手工编排。
- 新增 `PATCH /projects/{project_id}/chapters/{chapter_id}/timeline/clips/{clip_id}`。片段长度不能超过源音频，淡入和淡出总长不能超过片段长度。
- 新增 `TimelineRenderService` 和章节渲染接口：`POST/GET /projects/{project_id}/chapters/{chapter_id}/timeline/render`、`GET .../render/audio`。
- FFmpeg 渲染以数据库时间线为唯一输入，应用真实 `start_ms`、`duration_ms`、`volume_db`、`fade_in_ms`、`fade_out_ms`、`is_muted`，支持人物声、旁白、音效和 BGM 重叠混合。
- 输出固定为 44.1 kHz、双声道、PCM 16-bit WAV，并生成 `timeline_render_manifest.json`。清单记录渲染指纹、轨道 revision、片段参数和源资产，方便复现与排查。
- 片段或源文件变化后，旧成片会因 fingerprint 不一致而被判定过期；前端不会把过期文件继续当作当前结果。
- 渲染保护边界为单章最多 500 个片段、最长 4 小时；空时间线、缺失资产、stale/missing_audio 状态会拒绝渲染。
- 旧接口 `/lines/export-audio/{chapter_id}` 仍按台词顺序拼接，仅用于兼容旧调用。面试演示中的“最终混音”必须走时间线渲染接口。
- 前端支持生成后直接试听和下载 WAV。桌面和 390px 窄屏已通过真实浏览器检查，无页面横向溢出或控制台错误。
- 时间线片段支持在统一坐标画布中直接拖动、左右边缘裁剪；保存后继续沿用服务端源音频长度和淡入淡出约束，点击片段仍可打开精确编辑对话框。波形显示暂不纳入当前面试展示范围。

关键文件：

- `SonicVale/app/services/timeline_render_service.py`
- `SonicVale/app/services/timeline_service.py`
- `SonicVale/app/routers/timeline_router.py`
- `SonicVale/app/dto/timeline_dto.py`
- `SonicVale/tests/test_timeline_render_service.py`
- `sonicvale-front/src/pages/TimelineBoard.vue`
- `sonicvale-front/src/api/timeline.js`

## 4. 当前进展状态

当前 checkout 状态：

- `master` 跟踪 `github/master`。
- 最新提交号以 `git log -1 --oneline` 为准。
- 工作区存在未跟踪目录 `personal-site/`，不属于 Auralis 交接文档任务；不要误提交。
- `origin` Gitee 远端仍保留，但默认 push 目标已经是 GitHub。

最近完整验证：

```bash
./scripts/verify.sh
```

结果：

- Python unittest：55 tests OK（包含真实音频时长、时间线片段编辑、重叠混音、音量/淡入/静音、成片过期保护、共享资产回收、音频版本切换、章节清理和素材库测试）。
- FastAPI route smoke check 通过。
- TTS review feature 默认开启检查通过。
- 多轨非朗读行跳过 TTS 检查通过。
- project readiness repair smoke check 通过。
- audio asset attach 检查通过。
- TTS route policy 检查通过。
- SQLite schema migration、时间线编辑和渲染 API 路由检查通过。
- 共享素材库 32 个内置文件读取、音频流、用户上传、删除和项目绑定 smoke check 通过。
- 时间线编辑 -> FFmpeg 渲染 -> 最新成片读取 -> WAV 下载的 API smoke chain 通过。
- 前端时间线页面已静态校验为调用 `src/api/timeline.js`，不再调用章节台词接口或文字长度估算。
- 前端 `vite build` 通过。
- Vite 仍提示部分 chunk 超过 500kB，这是体积优化提示，不是失败。
- 产品版本已统一为 `0.4.0`：前端 `package.json`、FastAPI metadata 和本次交接状态一致。

开发服务通常使用：

```text
Frontend: http://127.0.0.1:5173
Backend:  http://127.0.0.1:8200
API docs: http://127.0.0.1:8200/docs
```

不要假设服务正在运行。需要联调时先执行 `./scripts/dev.sh`。

## 5. 已确定的方案、决策和原因

1. **不使用 LangGraph 作为当前架构**
   - 原因：当前流程是清晰的业务状态机，SQLAlchemy 会话和 revision 已足够表达状态；引入 LangGraph 会让面试项目显得架构过重。

2. **主流程是工作流，但制作助手是常驻 agent-like 入口**
   - 原因：解析、角色确认、台本确认、写入项目属于确定性阶段流；用户自由修改、定位问题、调用制作工具需要常驻助手。

3. **编剧和审查分离，但不必包装成两个长期 agent**
   - 原因：当前实现本质上是两次或多次受控 LLM 调用。可以称为 writer/reviewer service，但不要为了名词引入多 Agent 框架。

4. **初稿要先显示，再进行审查**
   - 原因：用户明确担心速度慢时会误以为模型卡住；中间产物可见能展示实际工作内容。

5. **用户修改意见由制作助手接收，再转给对应 service**
   - 原因：用户自然语言反馈需要意图识别和定位，但实际改稿仍由台本服务执行，避免助手直接乱改底层数据。

6. **TTS 文本和声音指导分离**
   - 原因：否则括号里的情绪、停顿、音效会被模型朗读，广播剧输出会失真。

7. **Edge-TTS 做能力降级，不做虚假承诺**
   - 原因：Edge 的情绪和自然语言提示并不等价于云端指令模型；UI 和后端都要让用户知道参数只是近似映射。

8. **音频生成版本必须可逆**
   - 原因：用户需要比较不同 take；重新生成不能覆盖旧音频。

9. **README 面向面试展示**
   - 原因：用户明确表示项目不准备扩展成长期平台，README 只要清楚表达项目能力和架构，不要强调“基于某项目改编”。

10. **GitHub 仓库保持 public**
    - 原因：用户在 2026-07-18 明确表示“不用，就一直保持 public”。

## 6. 用户偏好、要求和约束条件

- 用户希望 AI 直接在真实项目里执行，不要只给建议。
- 较大改动完成后默认提交并推送。
- 当前默认推送目标是 GitHub `rheeh/auralis`，不是 Gitee。
- 用户更重视面试展示效果和架构清晰度，不希望继续无边界扩展。
- 中文沟通优先；产品界面当前主要是中文。
- UI 要工作台化、克制、紧凑，少解释性固定栏，少浪费空间。
- 左侧制作助手必须真的能承接自由输入，而不是只有形式上的输入框。
- 不同角色应使用不同音色。
- 广播剧旁白要克制，优先把视觉和心理描写转成可听内容。
- 不得朗读括号里的音效、情绪、停顿或制作提示。
- 不要把制作助手和小说解析共用同一套 system prompt。
- 不要恢复旧 LangGraph 架构，除非用户明确要求重新评估。
- 不要把 `.local-data/`、`.verify-data/`、`.venv/`、`node_modules/`、`dist/`、数据库、生成音频、密钥提交到 git。
- 不要误提交当前未跟踪的 `personal-site/`。
- 不要继续尝试把 GitHub 仓库改 private；用户已经取消该要求。

## 7. 已有文件、素材、代码、数据或重要链接

### 必读文件

- `README.md`：当前项目定位、启动、验证和架构说明。
- `docs/AI-HANDOFF.md`：当前交接文档。
- `docs/project-map.md`：历史项目结构地图，可能部分过期，读后要用当前文件验证。
- `docs/project-workspace-single-page.md`：单页工作台早期方案。
- `docs/frontend-interaction-redesign.md`：交互重构说明。
- `docs/auralis-langgraph-implementation-plan.md`：旧 LangGraph 方案，只能当历史背景。

### 后端入口

- `SonicVale/app/main.py`
- `SonicVale/app/models/po.py`
- `SonicVale/app/db/migrations.py`
- `SonicVale/app/routers/chat_router.py`
- `SonicVale/app/routers/line_router.py`
- `SonicVale/app/routers/sound_library_router.py`
- `SonicVale/app/services/drama_workflow_service.py`
- `SonicVale/app/services/production_assistant_service.py`
- `SonicVale/app/services/script_review_service.py`
- `SonicVale/app/services/workflow_llm_service.py`
- `SonicVale/app/services/sound_library_service.py`
- `SonicVale/app/core/llm_engine.py`
- `SonicVale/app/core/tts_engine.py`
- `SonicVale/app/core/tts_guidance.py`
- `SonicVale/app/core/tts_runtime.py`

### 前端入口

- `sonicvale-front/src/pages/ProjectWorkspace.vue`
- `sonicvale-front/src/components/workflow/ChatComposer.vue`
- `sonicvale-front/src/components/workflow/ChatMessageList.vue`
- `sonicvale-front/src/components/workflow/ChatProductionPanel.vue`
- `sonicvale-front/src/components/workflow/ProductionScriptPanel.vue`
- `sonicvale-front/src/components/workflow/RoleDraftConfirmCard.vue`
- `sonicvale-front/src/components/workflow/ScriptDraftConfirmCard.vue`
- `sonicvale-front/src/pages/ConfigCenter.vue`
- `sonicvale-front/src/pages/QueueBoard.vue`
- `sonicvale-front/src/pages/MediaBoard.vue`
- `sonicvale-front/src/components/SoundLibraryPanel.vue`

### 测试入口

- `SonicVale/tests/test_drama_workflow.py`
- `SonicVale/tests/test_production_assistant.py`
- `SonicVale/tests/test_workflow_llm_service.py`
- `SonicVale/tests/test_llm_engine_messages.py`
- `SonicVale/tests/test_tts_guidance.py`
- `SonicVale/tests/test_tts_engine_capabilities.py`
- `SonicVale/tests/test_audio_variants.py`
- `SonicVale/tests/test_audio_drama_prompts.py`

### 重要链接

- 当前 GitHub 仓库：https://github.com/rheeh/auralis
- 旧 Gitee 远端：https://gitee.com/green1149/auralis-studio
- 原 SonicVale 项目：https://github.com/xcLee001/SonicVale

### 本地运行数据

- `.local-data/`：本地开发数据，已忽略，不得提交。
- `.verify-data/`：验证数据，已忽略，不得提交。
- `SonicVale/.venv/`：Python 虚拟环境，已忽略，不得提交。
- `sonicvale-front/node_modules/`、`sonicvale-front/dist/`：前端依赖和构建产物，已忽略，不得提交。
- Provider 本地备份通常在用户本机目录下，README 已提示不要把 API Key 写入仓库。

## 8. 未解决的问题和风险

1. **GitHub 仓库当前是 public**
   - 用户已接受 public 状态，但如果后续要私有化，需要 GitHub sudo mode 密码确认，AI 不能代输密码。

2. **存在未跟踪目录 `personal-site/`**
   - 当前不属于 Auralis 工作范围。任何 `git add -A` 前必须再次检查，避免误提交。

3. **真实 LLM/TTS 端到端速度和稳定性仍依赖外部 provider**
   - 本地 verify 覆盖结构、路由、服务、构建和 mock/smoke 场景；不等价于每次都真实调用云模型。

4. **审查/返修质量取决于模型输出**
   - 已做 schema 校验和 fallback，但模型可能给出保守或过度审查结论；需要真实项目样本继续调 prompt。

5. **Edge-TTS 参数效果有限**
   - 用户曾反馈 Edge 下改声音指导差异不明显，这是模型能力限制，不应包装成 bug 修复完成。

6. **Vite chunk 体积提示仍存在**
   - 当前不影响构建，但面试演示若关注性能，可做 code splitting。

7. **音频版本垃圾回收还可继续完善**
   - 生成 take、后期处理版本、导出文件之间的批量清理策略仍有提升空间。

8. **时间线交互仍是参数表单，不是完整 DAW**
   - 当前可精确编辑和真实渲染，但还没有拖拽移动、边缘裁剪、波形、吸附和撤销。不要在演示中宣称已具备专业音频工作站能力。

9. **历史文档可能有过期内容**
   - 特别是 LangGraph、Gitee、旧 UI 相关文档。下一位助手必须以当前代码和 README/本文档为准。

10. **AGPL 署名需要保留**
   - README 末尾已保留 SonicVale 许可与署名。不要为了“看起来完全原创”删除合规信息。

## 9. 下一步具体行动计划

建议下一位助手从高价值、低风险事项继续：

1. **先做状态确认**
   - 运行 `git status -sb`、`git log -1 --oneline`、`git remote -v`。
   - 确认 `master...github/master` 且只有预期未跟踪文件。

2. **保持演示可用**
   - 任意功能改动后运行对应后端测试。
   - UI 改动至少运行前端 build。
   - 较大改动运行 `./scripts/verify.sh`。

3. **下一项首选：时间线直接操作**
   - 在 `TimelineBoard.vue` 上增加片段拖拽移动和边缘裁剪，沿用当前 PATCH 接口提交最终值。
   - 增加时间刻度吸附和“撤销本次编辑”，但不要在第一步引入复杂 DAW 状态框架。
   - 继续保留参数弹窗作为精确输入入口。

4. **第二优先：自动声音设计建议**
   - 根据台本中的 `sfx`、`bgm` 和场景信息，从共享素材库给出可审查的候选素材与建议位置。
   - 先做“建议 -> 用户确认 -> 写入时间线”，不要让模型未经确认直接覆盖手工编排。

5. **第三优先：项目级成片导出**
   - 在章节时间线渲染稳定后，再实现多章节排序、章间停顿、章节级清单和项目总 WAV/压缩格式导出。
   - 项目导出必须消费各章节最新且未过期的时间线成片，不能回退到旧台词顺序拼接。

6. **如果用户要求再次发布**
   - 默认推 GitHub：

     ```bash
     git push
     ```

   - 不要推旧 Gitee，除非用户明确要求。

7. **如果有较大修改**
   - 提交前检查敏感文件和未跟踪目录。
   - 提交后推送 GitHub。
   - 最终回复给出提交哈希、验证结果、关键文件和风险。

## 10. 给下一位 AI 助手的启动指令

请从这里继续，不要重新做已经完成的架构迁移或产品判断。

第一步运行：

```bash
cd /Users/go/Desktop/sonic-drama-studio
git status -sb
git log -1 --oneline
git remote -v
```

预期状态：

```text
master...github/master
github git@github.com:rheeh/auralis.git
origin https://gitee.com/green1149/auralis-studio.git
```

注意：可能存在未跟踪 `personal-site/`，不要提交它。

继续工作前阅读：

```bash
sed -n '1,220p' README.md
sed -n '1,260p' docs/AI-HANDOFF.md
```

不要重复做这些事：

- 不要重新引入 LangGraph。
- 不要重新把 README 改成“基于 SonicVale 二次开发”的开头。
- 不要继续把 GitHub 仓库改 private。
- 不要恢复已删除的旧 `image/` 截图，除非用户明确要求。
- 不要把制作助手和小说解析 prompt 合并。
- 不要把括号音效、停顿、情绪写回 TTS 朗读文本。
- 不要用 `git add -A` 直接提交所有文件，除非先确认未跟踪文件全都属于本次任务。

最低验证策略：

```bash
./scripts/verify.sh
git diff --check
```

如果只是文档改动，可至少运行：

```bash
git diff --check
```

最终交付格式：

- 说明改了哪些文件。
- 给出验证命令和结果。
- 如果提交推送，给出 commit hash 和远端链接。
- 明确剩余风险，不要假装没有不确定性。
