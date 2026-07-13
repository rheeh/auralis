# Auralis 项目执行交接

> 状态日期：2026-07-12
> 工作目录：`/Users/go/Desktop/sonic-drama-studio`
> 主分支：`master`
> 唯一远程：`https://gitee.com/green1149/auralis-studio.git`

## 1. 项目背景和最终目标

Auralis 是一个本地优先的 AI 广播剧制作工具，技术栈为 Vue 3 + Element Plus + Electron 前端、FastAPI + SQLAlchemy + SQLite 后端。产品目标不是“把小说朗读出来”，而是在一个项目工作台内完成：

1. 用户新建或打开项目；
2. 在左侧与制作助手交流并提交小说；
3. AI 先解析人物卡，用户确认人物、头像和独立音色；
4. AI 生成声音优先、旁白克制的广播剧台本；
5. 用户逐句生成音频、修改声音提示、试听并做非破坏性后期处理；
6. 台本、角色、音色、声音事件和音频结果始终在同一工作台内完成，不额外跳转。

最终产品应兼顾普通创作者的低门槛和广播剧制作所需的可控性，所有 UI 文案默认使用中文。

## 2. 当前任务和优先级

截至本文件提交，最近一轮三个高优先级需求已经实现并通过验证：

| 优先级 | 功能 | 状态 |
|---|---|---|
| P0 | 首页用二次元女歌姬替换几何剪影 | 已完成 |
| P0 | 同一条原音频可保存多个不同速度/音量处理版本 | 已完成 |
| P0 | 处理版本可设为当前采用，播放、连播和导出读取当前版本 | 已完成 |
| P0 | 单条音频支持选区局部变速，区间外保持原速 | 已完成 |
| P0 | 角色绑定音色时可直接试听，不必离开工作台 | 已完成 |
| P0 | 把本轮代码提交并推送到 Gitee | 已完成 |
| P1 | 保持广播剧台词为纯净 TTS 文本，声音提示进入独立字段 | 已完成 |
| P1 | 工作台左助手承担阶段引导和快捷操作 | 已完成 |

## 3. 已完成的工作和关键产出

### 3.1 首页

- `/` 进入 `/home`，首页不再显示后台侧栏和工作区顶栏。
- 首页圆环由四层 SVG 独立动画组成，包含顺/逆时针旋转、呼吸发光和流动光点。
- Canvas 波形使用 `requestAnimationFrame`，Demo 播放时提高振幅，页面隐藏及组件卸载时停止动画。
- 30 个低透明粒子围绕圆环漂浮；桌面视差最大不超过 8px，移动端关闭。
- 首页导航和按钮都连接真实页面：作品库、音色库、模型设置和最近项目。
- 女歌姬通过内置生图工具生成，使用绿色背景抠图为透明 PNG；项目最终素材：
  - `sonicvale-front/src/assets/visuals/auralis-anime-singer.png`
  - 约 1.4MB，946×1663，RGBA，透明四角。
- 生成规格：银蓝长发、深蓝与珍珠白舞台服、金色细节、耳机、全身、日系动画立绘、无文字和水印。

### 3.2 单页项目工作台

- 主入口：`sonicvale-front/src/pages/ProjectWorkspace.vue`。
- 左侧制作助手显示当前任务、阶段说明和快捷操作；消息为左右气泡。
- 右侧按阶段显示人物卡、台本确认、人物档案以及逐句音频制作。
- 小说原文折叠在逐句台本上方；人物卡在确认后仍可独立查看。
- 结果区顶栏只保留“当前制作 / 人物卡”；点击台词卡空白处展开编辑，再点一次收起。
- 逐句制作组件：`sonicvale-front/src/components/workflow/ProductionScriptPanel.vue`。
- 每条可朗读台词都可单独生成音频，不必先生成全部。
- 每个角色必须绑定不同音色；音色按 TTS 模型来源分组。

### 3.3 广播剧台本规则

- 核心规则在 `SonicVale/app/core/prompts.py` 和 `SonicVale/app/services/script_draft_service.py`。
- `dialogue/narration` 的朗读文本严禁包含 `()、（）、[]、【】` 中的音效或表演提示。
- 表演、语速、重音、停顿进入 `productionNote`。
- 音效、环境音、BGM、混响、静音进入 `audioEvents`，包含 timing/type/content/volume_db。
- Pydantic 在 `SonicVale/app/workflows/drama/schemas.py` 做第二层清洗；TTS 前 `LineService.clean_tts_text` 再次防御，旧台本也不会朗读括号提示。
- 空 SFX/BGM 会补场景相关声音提示，不再显示空内容。

### 3.4 非破坏性音频版本

- `lines` 新增 `audio_variants` JSON 字段；SQLite 启动迁移由 `add_drama_line_columns()` 自动完成。
- 每次处理都复制 `line.audio_path` 原音频，再应用速度、音量、裁剪或停顿，绝不覆盖原始文件，也不从上一个变速版本继续叠加。
- 后端接口：
  - `POST /lines/{line_id}/audio-variants`
  - `GET /lines/{line_id}/audio-variants/{variant_id}/audio`
  - `DELETE /lines/{line_id}/audio-variants/{variant_id}`
- 前端展开某句后点击“保存为新音频版本”，版本列表可独立播放和删除。
- 新保存版本自动设为“当前采用”，也可手动切换；顶部播放、整章连播和导出统一读取当前版本，编辑器仍固定从生成原音派生。
- 可在波形中选择局部变速区间，例如仅把 0–1.5 秒设为 0.8×，后半段继续保持 1.0×；后端按前段、变速选区、后段重新拼接。
- 自动标签包含速度和音量，例如 `0.75x 速度 · 1x 音量`。
- 单元测试 `SonicVale/tests/test_audio_variants.py` 已验证 0.8× 与 1.25× 生成不同文件、时长不同且源文件 SHA-256 不变。

### 3.5 音色试听

- `RoleDraftConfirmCard.vue` 的每个音色选项右侧都有试听/停止按钮。
- 已选音色下方也有明确的试听按钮。
- 已确认人物档案 `CharacterCardsArchive.vue` 也可试听绑定音色。
- 人物档案不再重复显示 AI 声线建议框，逐句卡也不再重复提供角色音色下拉框。
- 人物档案可重新选择项目角色音色；每个候选音色右侧均有独立试听按钮，更新后逐句制作会提示按新音色重新生成。
- 试听复用 `GET /voices/{voice_id}/audio`；真实浏览器验证返回 HTTP 206 音频流。
- 没有 `reference_path` 的音色显示“暂无试听样音”，不会触发必然失败的请求。

## 4. 当前进展状态

- 前端生产构建通过：`npm --prefix sonicvale-front run build`。
- 后端 7 项音频/广播剧测试通过。
- Python 关键模块 `py_compile` 通过。
- 临时 API 集成测试成功创建 0.75× 和 1.3× 两个版本，版本音频 HTTP 200；临时台词、版本文件和数据库记录均已删除。
- 桌面首页 1600×900 和移动端 390×844 已做截图检查，无横向溢出。
- 女歌姬透明图已验证 natural size 946×1663，桌面和移动端都完整显示。
- 人物档案音色试听真实请求成功，按钮切换为“停止”。
- 真实 API 验证原音 2.808s、0.8× 版本 3.482s、1.25× 版本 2.232s；切换后顶部音频接口返回对应时长，原音 SHA-256 不变。
- 局部变速实测原音 2.016s，仅 0–1.5s 使用 0.8× 后为 2.374s；验证版本和数据库记录均已清理。
- 旧台词缺失的情绪/强度已在启动时补为“平静/中等”；新台本在结构化校验和提交时双重兜底。

开发服务通常运行在：

- 前端：http://127.0.0.1:5173
- 后端：http://127.0.0.1:8200
- API 文档：http://127.0.0.1:8200/docs

若端口未监听，从 README 的启动命令重新启动，不要假设旧进程仍存在。

## 5. 已确定的方案、决策和原因

1. **工作台不拆成多页**：人物确认、台本确认、音色与音频必须在同一页面，减少上下文丢失。
2. **人物卡先于台本**：人物身份和说话方式直接影响台词写法，也让音色在台本生成前确定。
3. **不是纯 Multi-Agent 堆叠**：SQLAlchemy 项目数据是业务真相，LangGraph/工作流只负责编排；避免状态只存在 Agent 对话里。
4. **台词与制作控制分离**：TTS 文本必须纯净，声音提示进入结构化字段，防止模型朗读括号。
5. **音频处理非破坏性**：不同速度必须从同一原音频生成，避免 0.8× 后再做 1.2× 导致累计失真，也方便 A/B 比较。
6. **音色试听放在绑定现场**：选择前可试听比跳到音色库更符合决策路径。
7. **首页角色使用项目内透明 PNG**：视觉质量优先于代码生成剪影，同时保留 Canvas、SVG 圆环和粒子的实时动画。
8. **Gitee 使用干净历史**：当前仓库 `master` 从 Auralis 单一根提交开始，不推送旧 SonicVale 上游多人历史；远程只保留 `origin`。

### 2026-07-13 全站视觉统一

- 非首页页面改为与首页同源的浅蓝、暖白渐变背景和半透明白色卡片，侧栏不再使用深色霓虹底。
- 侧栏“作品”统一改名为“项目”，顶部面包屑与项目页文案同步使用“项目”。
- 首页和应用侧栏的 Auralis 标志都改为七段动态均衡器；标志仍链接 `/home`。
- 首页横向声场改为蓝青到珊瑚色的双向柱状波形，播放 Demo 时有移动光点；歌姬从 `340×500` 缩小至约 `226×334`。
- 项目页新增声场式横幅和抽象音频封面，保留原有创建、配置检查、工作流节点、删除与进入工作台能力。
- 已浏览器巡检 `/home`、`/projects`、`/voices`、`/queue`、`/prompts`、`/config`；桌面视口无横向溢出，控制台无 error/warning。

### 2026-07-13 TTS 模型能力适配

- `ConfigurableCloudTTSEngine` 不再把所有云端 TTS 当成相同能力：`instruction_mode` 支持 `native`、`structured`、`mapped`、`none`。
- CosyVoice v1/v2 只做语速、音高、音量参数映射；v3 Flash/Plus 将台词情绪和声音指导转换为 DashScope 系统音色接受的结构化 Instruct；v3.5 复刻/设计音色可透传自然语言指令。
- 通用 HTTP TTS 模板新增 `{{instruction}}`，也可用 `instruction_field` 配置 `instructions`、`input.instruction` 等厂商字段路径。
- 配置中心 TTS 表格会显示“原生指令 / 结构化指令 / 基础参数映射 / 基础生成”，测试接口也会返回实际使用的模式。
- 本机 Provider #2 已迁移为 `cosyvoice-v3-flash` 结构化指令模式；旧 v1 音色移至停用的兼容 Provider #4，没有删除。迁移前数据库备份位于 `.local-data/backups/app_test-before-cosyvoice-v3-20260713.db`。
- 已真实调用 DashScope：Provider 测试 HTTP 200，并成功生成 3 个 v3 Instruct 兼容音色样例；项目 5/6/7 中原先使用 v1 女声的角色已改绑“元气女声·龙安欢”。

## 6. 用户偏好、要求和约束

- 用户希望直接修改真实项目，不只提供建议或伪代码。
- 较大改动完成后默认提交并推送 Gitee。
- 中文界面与中文交付文档优先。
- 工作台减少无关顶部说明，保留与当前任务直接相关的信息。
- 风格偏二次元，但要高级、克制、可用于生产工具，避免廉价游戏特效。
- 不同人物必须使用不同音色。
- 音色需要覆盖所有已安装模型来源，不只 Edge。
- 广播剧旁白要克制：先删除视觉无效信息、环境、动作、转场、背景信息，再处理心理描写；目标旁白占比不超过15%。
- 不得朗读括号音效、情绪和停顿提示。
- 不得关联或推送到别人的仓库；唯一目标仓库是 `https://gitee.com/green1149/auralis-studio.git`。
- 工作区中 `image/` 下的删除是既有未提交状态。除非用户明确要求，不要恢复、提交或清理这些删除。

## 7. 已有文件、素材、代码、数据和链接

### 必读入口

- `README.md`：真实启动与验证命令。
- `docs/project-map.md`：项目结构地图。
- `docs/project-workspace-single-page.md`：单页工作台方案。
- `docs/frontend-interaction-redesign.md`：交互重构说明。
- `docs/auralis-langgraph-implementation-plan.md`：工作流与数据边界方案。
- `sonicvale-front/src/router/index.js`：路由真相。
- `sonicvale-front/src/pages/Home.vue`：动态首页。
- `sonicvale-front/src/pages/ProjectWorkspace.vue`：项目工作台。
- `sonicvale-front/src/components/workflow/ProductionScriptPanel.vue`：逐句制作、音频版本和播放。
- `SonicVale/app/routers/line_router.py`：台词音频与版本 API。
- `SonicVale/app/services/line_service.py`：TTS 清洗和音频处理实现。
- `SonicVale/app/services/script_draft_service.py`：台本提示词与旁白审校。

### 外部链接

- Gitee：https://gitee.com/green1149/auralis-studio
- 音谷参考 Wiki（可能需要登录）：https://sw4s2hg7k5y.feishu.cn/wiki/WjbUw1t7JiWIa7k2pFXcxqSbnde

### 本地数据

- 开发数据目录：`.local-data/`，已被忽略，不得提交。
- SQLite 与生成音频属于运行数据，不要在未备份时手工删除。
- 音频版本保存在原音频目录的 `variants/` 子目录。

## 8. 未解决的问题和风险

1. 音频版本随台词删除或重新生成时尚未做统一垃圾回收；当前只能从 UI 单独删除版本。
2. 没有参考样音的自定义音色无法试听，UI 会明确提示；如果要求“所有音色必可试听”，需增加按 provider 动态生成预览样音的后端任务。
3. 当前采用版本已经贯通播放和导出，但重新生成原音后旧处理版本尚未提供“上一 take”归档分组。
4. 女歌姬 PNG 约 1.4MB，可进一步输出 WebP/AVIF 降低首页首载，但必须保留透明边缘质量。
5. Vite 构建仍提示主包超过 500kB，可通过 manualChunks 或进一步懒加载优化；目前不影响功能。
6. WaveSurfer 和浏览器原生 `<audio>` 并存，后续若统一播放器，需要保证整章连播逻辑不回退。
7. 飞书 Wiki 曾无法通过自动浏览器公开读取；不要声称已完整同步其中全部规范。

## 9. 下一步具体行动计划

1. 在重新生成台词原音时提示旧版本来自上一 take，允许保留、归档或批量删除。
2. 为音频版本 API 增加路由级 TestClient 测试和异常场景测试（缺文件、非法速度、重复删除）。
3. 为音色试听抽取可复用 composable，覆盖人物草稿和人物档案，避免播放器状态代码重复。
4. 如用户要求全音色试听，为无 `reference_path` 音色增加后台预览生成队列，而不是在 GET 请求里同步调用云端 TTS。
5. 优化首页女歌姬素材体积，并复测 1600×900、1366×768、390×844 三个视口。
6. 处理任何新改动后运行全套验证并按用户偏好提交推送。

## 10. 给下一位 AI 助手的启动指令

1. 进入 `/Users/go/Desktop/sonic-drama-studio`，先运行：

   ```bash
   git status --short
   git log -1 --oneline
   git remote -v
   ```

2. 确认唯一远程仍是 `https://gitee.com/green1149/auralis-studio.git`；不要重新添加原 SonicVale GitHub upstream。
3. 不要处理 `image/` 下已有删除，除非用户明确授权。
4. 阅读本文件、`README.md`、`docs/project-map.md`，然后从用户最新需求涉及的文件继续；不要重新设计已经完成的单页工作台、台词纯净化、音频多版本或音色试听。
5. 启动项目：

   ```bash
   ./scripts/dev.sh
   ```

6. 最低验证命令：

   ```bash
   cd SonicVale
   .venv/bin/python -m unittest discover -s tests -p 'test_audio*.py' -v
   cd ../sonicvale-front
   npm run build
   cd ..
   git diff --check
   ```

7. 涉及 UI 时必须做真实浏览器检查；涉及音频处理时必须验证原文件没有被覆盖，并清理临时数据库记录和文件。
8. 较大改动完成后提交并推送 `master`，最终回复中给出提交哈希、测试结果、关键文件和仍存在的风险。
