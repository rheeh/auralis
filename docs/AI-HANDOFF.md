# Auralis 项目交接文档

> 状态日期：2026-07-31
> 工作目录：`/Users/go/Desktop/sonic-drama-studio`
> 当前分支：`master`
> 当前默认远端：`github` -> `git@github.com:rheeh/auralis.git`
> 公开仓库：https://github.com/rheeh/auralis
> 旧远端保留：`origin` -> `https://gitee.com/green1149/auralis-studio.git`
> 最新关键提交：`bcf6182 feat: close timeline lifecycle and frontend loop`

本文档给下一位 AI 助手接手执行用。它不是聊天总结，所有判断都应以当前 checkout 为准。

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

- “多轨时间线”页面已改名为“多轨内容概览”。页面现在通过真实时间线 API 展示 `start_ms`、`duration_ms`、音频资产状态和构建状态，不再按文字长度估算片段宽度。
- SQLite 已改为版本化迁移入口 `SonicVale/app/db/migrations.py`，当前 schema version 为 3；历史字段迁移集中管理，`main.py` 不再继续堆叠 `add_*_column()`。
- 新增 `AudioAssetPO`、`TimelineTrackPO`、`TimelineClipPO`，保留现有 `lines.audio_path`、`audio_versions` 和 `audio_variants` 作为兼容来源。
- `TimelineService` 会探测真实音频时长，按人物声、旁白、音效、BGM 四条固定轨道生成章节内容概览。
- 新增只读接口 `GET /projects/{project_id}/chapters/{chapter_id}/timeline` 和显式构建接口 `POST /projects/{project_id}/chapters/{chapter_id}/timeline/build`。
- 时间线支持 `not_built`、`building`、`ready`、`stale`、`missing_audio`、`failed` 状态；台词、音频版本或素材变化会通过失效钩子和来源指纹标记旧结果。
- 删除台词、章节、项目或替换章节台词时会清理轨道、片段和音频资产；SQLite 连接已启用外键约束。手工编辑片段默认受保护，只有显式 `overwrite_manual=true` 才允许重建覆盖。
- 空轨道只有在该轨道确实存在台词且其中有台词缺少音频时才显示 `missing_audio`；正常空轨道显示为 `ready`。
- `AudioAsset` 是项目级共享资源，`TimelineClip` 承担引用关系；删除台词/章节/项目时只删除无任何片段引用的资产。BGM、环境音等跨章节复用由测试覆盖。
- 多轨内容概览使用统一时间坐标画布：所有轨道共享同一标尺，片段位置由 `start_ms × scale`，宽度由 `duration_ms × scale` 计算。
- 数据库迁移失败会阻止应用继续启动，避免半迁移状态继续对外提供 API。
- 当前刻意未实现拖拽、音量编辑、重叠编排和混音导出；这些属于 Auralis 0.4。未来渲染服务必须把时间线作为成片导出的唯一真实来源，旧的按台词顺序导出仅保留为兼容路径，不能冒充时间线渲染。

### 3.8 README 和 GitHub 同步

- README 已重写为英文面试项目说明。
- README 开头直接介绍 Auralis，不再第一句话强调“基于某项目改编”。
- 许可与原项目署名保留在末尾的 `License And Attribution`，满足合规但不喧宾夺主。
- GitHub 仓库已创建并推送：`https://github.com/rheeh/auralis`。
- 用户已明确表示仓库可以保持 public，不再继续做 private 切换。
- 本地 `master` 已跟踪 `github/master`。

## 4. 当前进展状态

当前 checkout 状态：

- `master` 跟踪 `github/master`。
- 最新项目提交：`bcf6182 feat: close timeline lifecycle and frontend loop`；随后会有本交接文档更新提交。
- 工作区存在未跟踪目录 `personal-site/`，不属于 Auralis 交接文档任务；不要误提交。
- `origin` Gitee 远端仍保留，但默认 push 目标已经是 GitHub。

最近完整验证：

```bash
./scripts/verify.sh
```

结果：

- Python unittest：49 tests OK（包含真实音频时长、空轨道 ready、幂等构建、旧 SQLite 迁移、失效保护、共享资产回收、音频版本切换和章节清理测试）。
- FastAPI route smoke check 通过。
- TTS review feature 默认开启检查通过。
- 多轨非朗读行跳过 TTS 检查通过。
- project readiness repair smoke check 通过。
- audio asset attach 检查通过。
- TTS route policy 检查通过。
- SQLite schema migration 和时间线 API 路由检查通过。
- 前端时间线页面已静态校验为调用 `src/api/timeline.js`，不再调用章节台词接口或文字长度估算。
- 前端 `vite build` 通过。
- Vite 仍提示部分 chunk 超过 500kB，这是体积优化提示，不是失败。
- 产品版本已统一为 `0.3.2`：前端 `package.json`、FastAPI metadata 和本次交接状态一致。

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
- `SonicVale/app/services/drama_workflow_service.py`
- `SonicVale/app/services/production_assistant_service.py`
- `SonicVale/app/services/script_review_service.py`
- `SonicVale/app/services/workflow_llm_service.py`
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

8. **历史文档可能有过期内容**
   - 特别是 LangGraph、Gitee、旧 UI 相关文档。下一位助手必须以当前代码和 README/本文档为准。

9. **AGPL 署名需要保留**
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

3. **如果用户继续调工作台 UI**
   - 只围绕 `ProjectWorkspace.vue` 和 `components/workflow/*` 做小步修改。
   - 改完用真实浏览器检查，不要只凭代码判断。

4. **如果用户继续调改编质量**
   - 先检查 `script_draft_service.py`、`script_review_service.py`、`workflow_llm_service.py`。
   - 保持“初稿可见 -> 审查中 -> 返修结果可见”的进度表达。
   - 不要把审查器改成直接写稿的组件。

5. **如果用户继续调 TTS 效果**
   - 先确认当前 provider 是 Edge 还是 cloud。
   - Edge 问题优先解释能力边界，再优化 rate/pitch/volume 映射。
   - Cloud provider 才考虑自然语言声音指导和结构化 instruction。

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
