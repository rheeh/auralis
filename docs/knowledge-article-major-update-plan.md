# Auralis 知识文章音频大版本更新方案

> 文档状态：Knowledge Audio v1 核心闭环已实现（2026-07-18）
>
> 目标版本：Auralis Knowledge Audio v1
>
> 适用项目：`/Users/go/Desktop/sonic-drama-studio`
>
> 本方案基于当前 checkout 和 `docs/AI-HANDOFF.md` 制定。当前项目使用 SQLAlchemy 数据库状态机，不恢复 LangGraph。

> 实施记录：Phase 0-5 已完成，包括内容分流、URL/正文导入、文章分析、知识大纲、学习设计、知识脚本、三维审查、幂等提交、TTS 复用和复习问题。首页、项目列表、新建项目弹窗和已有项目卡均已补齐“小说广播剧 / 知识文章音频”双入口，并完成桌面端与窄屏真实页面验收。Phase 6 联网查证及 Phase 7 OCR/长文/系列课程未实现，对应功能开关保持关闭。

## 1. 版本目标

Auralis 当前已经能够把小说改编为广播剧。本次大版本增加第二条内容生产能力：

> 将公众号文章、科普文章、技术文章、商业和管理文章，转化为可听、可理解、可复习的知识音频。

本版本不是把“小说正文输入框”换成“文章正文输入框”，而是新增一个独立的内容改编领域，同时复用已有的项目工作台、会话、LLM、TTS、音频版本、制作助手和导出基础设施。

### 1.1 产品表达

```text
小说广播剧：把故事变成广播剧
知识文章音频：把知识变成可听、可理解、可复习的音频课程
```

对外不建议宣传为“任何文章一键变广播剧”，因为知识文章的首要目标是理解和记忆，戏剧化只是表达形式。

### 1.2 本版本的核心体验

用户导入一篇文章后，Auralis 应该能够：

1. 识别文章主题、结构、观点和知识点。
2. 根据文章类型自动推荐音频表现形式。
3. 生成一段约 5 到 10 分钟的知识音频。
4. 展示音频中的核心知识点及其原文依据。
5. 明确标记 AI 额外补充和外部查证内容。
6. 生成听后复习问题，帮助用户检验是否真正记住。
7. 继续使用现有 TTS、试听、音频版本和导出能力。

## 2. 当前架构基线

### 2.1 必须保留的现状

根据 [AI-HANDOFF.md](/Users/go/Desktop/sonic-drama-studio/docs/AI-HANDOFF.md)，当前架构已经明确：

- 不使用 LangGraph。
- 主流程是 SQLAlchemy 数据库状态机。
- `chat_sessions`、`adaptation_runs` 和 draft revision 是业务状态源。
- 制作助手是常驻的项目级对话入口。
- 小说改编已经包含角色草稿、台本初稿、独立审查、返修和用户确认。
- TTS 生成支持任务队列和音频版本管理。
- README 和 UI 当前以面试展示和工作台体验为目标。

本次更新不能重新引入 LangGraph，也不能为了文章功能重构整个项目。

### 2.2 当前小说流程

```text
小说正文
  -> SourceParserService
  -> RoleDraftService
  -> 用户确认角色
  -> ScriptDraftService
  -> ScriptReviewService
  -> 编剧返修
  -> 用户确认台本
  -> DramaCommitService
  -> Chapter / Role / Line
  -> TTS
  -> 试听、版本选择、导出
```

### 2.3 当前代码中与本次更新直接相关的模块

后端：

- `SonicVale/app/models/po.py`
- `SonicVale/app/db/migrations.py`
- `SonicVale/app/dto/chat_dto.py`
- `SonicVale/app/routers/chat_router.py`
- `SonicVale/app/services/chat_session_service.py`
- `SonicVale/app/services/drama_workflow_service.py`
- `SonicVale/app/services/drama_commit_service.py`
- `SonicVale/app/services/source_parser_service.py`
- `SonicVale/app/services/role_draft_service.py`
- `SonicVale/app/services/script_draft_service.py`
- `SonicVale/app/services/script_review_service.py`
- `SonicVale/app/services/production_assistant_service.py`
- `SonicVale/app/services/workflow_llm_service.py`
- `SonicVale/app/core/tts_engine.py`
- `SonicVale/app/core/tts_guidance.py`
- `SonicVale/app/core/tts_runtime.py`

前端：

- `sonicvale-front/src/pages/Studio.vue`
- `sonicvale-front/src/pages/ProjectWorkspace.vue`
- `sonicvale-front/src/pages/ProjectOverview.vue`
- `sonicvale-front/src/pages/QueueBoard.vue`
- `sonicvale-front/src/pages/ProjectDubbingDetail.vue`
- `sonicvale-front/src/components/workflow/ChatProductionPanel.vue`
- `sonicvale-front/src/components/workflow/ChatMessageList.vue`
- `sonicvale-front/src/components/workflow/ChatComposer.vue`
- `sonicvale-front/src/components/workflow/ProductionScriptPanel.vue`
- `sonicvale-front/src/components/workflow/RoleDraftConfirmCard.vue`
- `sonicvale-front/src/components/workflow/ScriptDraftConfirmCard.vue`
- `sonicvale-front/src/api/drama.js`
- `sonicvale-front/src/api/queue.js`

## 3. 产品范围

### 3.1 支持的文章类型

第一版聚焦以下内容：

- 科普文章
- 技术文章
- 商业文章
- 管理文章

暂不承诺对以下内容提供稳定效果：

- 医疗诊断和治疗建议
- 法律意见
- 实时新闻
- 金融投资建议
- 纯图片漫画
- 高度依赖复杂图表的文章
- 需要登录或付费才能读取的文章

后续可以接入这些内容，但需要单独的风险提示、资料引用和内容处理方案。

### 3.2 第一版输入方式

支持：

1. 公众号文章链接。
2. 粘贴文章正文。

链接抓取失败时，必须提供粘贴正文的备用入口。

暂不把截图导入作为 MVP 主路径。截图能力依赖视觉模型稳定性，且需要 OCR、版面解析和人工校对。它可以作为后续增强输入。

### 3.3 第一版输出方式

统一生成一个知识音频项目，表现形式由 AI 根据文章自动选择：

- 主持人讲解
- 主持人 + 学习者对话
- 案例化知识剧场

用户可以在生成大纲后切换表现形式，但不需要在第一步面对过多参数。

### 3.4 第一版不做的内容

- 全自动无限长度文章处理。
- 多篇文章自动合并为完整课程。
- 自动订阅公众号更新。
- 强制把所有文章改编成多角色广播剧。
- 默认联网补充所有事实。
- 自动声称用户已经掌握知识。
- 复杂学习积分、排行榜和社交系统。
- 面向公众的内容分发平台。

## 4. 用户流程设计

### 4.1 新建制作入口

现有 Studio 页面进入制作前增加内容类型选择：

```text
新建制作

[小说广播剧]
解析人物和情节，制作角色化广播剧

[知识文章音频]
提炼文章核心观点，制作可听、可复习的知识音频
```

用户选择后，表单和后续工作流完全不同。

### 4.2 知识文章流程

#### 步骤一：导入文章

支持两种输入：

```text
[公众号链接] [粘贴正文]
```

链接输入后显示：

- 页面标题
- 作者
- 公众号名称
- 发布时间
- 正文长度
- 抓取状态
- 内容预览

用户必须确认“实际导入的正文”，避免链接标题和正文不一致。

#### 步骤二：内容设置

只保留必要设置：

- 文章领域：科普、技术、商业、管理、自动判断。
- 学习目标：快速理解、掌握概念、了解实际应用、强化记忆。
- 音频时长：5 分钟、10 分钟、15 分钟。
- 信息策略：忠实压缩、通俗解释、案例化讲解。
- 查证模式：仅基于原文、联网查证并标记。

推荐默认值：

```text
领域：自动判断
学习目标：快速理解
时长：10 分钟
信息策略：通俗解释
查证模式：仅基于原文
```

#### 步骤三：文章分析

页面展示分析进度：

```text
正在识别文章结构
正在提取核心观点
正在整理关键术语
正在判断适合的音频形式
```

结果至少包含：

- 一句话摘要
- 文章结构
- 核心知识点
- 关键术语
- 主要例子
- 可能的前置知识
- 需要谨慎表达的观点

#### 步骤四：知识大纲确认

用户先确认知识大纲，再生成音频脚本。

大纲卡片包含：

- 知识点标题
- 简短解释
- 原文依据
- 在音频中的预计位置
- 是否必须保留
- 是否由 AI 补充

这一步是文章流程的关键人工确认点，防止 AI 生成一段流畅但重点错误的音频。

#### 步骤五：音频脚本生成

AI 根据已确认知识大纲生成脚本。

脚本需要包含：

- 主持人或讲解者
- 学习者提问
- 知识解释
- 例子
- 过渡
- 小结
- 听后复习问题

生成过程中继续使用现有“先展示初稿，再独立审查”的策略。

#### 步骤六：审查与确认

文章脚本需要展示两种审查结果：

```text
内容准确性
  是否忠实于原文
  是否遗漏关键知识点
  是否增加未经标记的内容

学习效果
  是否容易理解
  是否有清晰结构
  是否有足够例子
  是否有复习节点

音频表现
  对话是否自然
  节奏是否适合朗听
  语音提示是否混入朗读文本
```

用户可以：

- 接受脚本
- 修改某个知识点
- 修改表达形式
- 删除 AI 补充
- 要求更通俗或更专业
- 要求缩短或延长

#### 步骤七：配音和复习

脚本确认后进入现有音频生产流程：

```text
确认脚本
  -> 角色/讲解者音色
  -> TTS 任务
  -> 试听和版本选择
  -> 连播和导出
```

音频完成后增加学习结果区域：

- 核心知识点回顾
- 关键术语卡片
- 3 到 5 个听后问题
- “再听一遍相关片段”入口
- 复习问题答案和原文依据

## 5. 内容类型和工作流架构

### 5.1 统一入口，内部分流

不建议建立两个完全独立的项目系统。建议统一使用项目和会话，但根据 `source_type` 选择不同 Pipeline：

```text
ContentAdaptationService
  -> NovelDramaPipeline
  -> KnowledgeArticlePipeline
```

共享：

- 项目管理
- ChatSession
- ChatMessage
- LLM provider
- TTS provider
- 音频任务
- 音频版本
- WebSocket 事件
- 导出
- 制作助手基础设施

小说专属：

- 人物草稿
- 场景规划
- 剧情冲突
- 角色关系
- 广播剧声音设计

文章专属：

- 文章结构
- 知识点
- 术语
- 原文证据
- 外部查证
- 学习目标
- 复习问题

### 5.2 推荐新增服务

```text
ArticleIngestService
  负责链接、正文、清洗、来源信息和导入失败处理

ArticleAnalysisService
  负责文章结构、知识点、术语、观点和例子提取

LearningDesignService
  负责学习目标、时长、知识顺序和复习节点设计

KnowledgeScriptService
  负责主持人、师生对话和案例剧场脚本生成

KnowledgeReviewService
  负责事实一致性、知识覆盖、可理解性和音频表达审查

SourceEvidenceService
  负责原文片段、外部来源和音频台词之间的对应关系

KnowledgeCommitService
  负责知识文章结果写入项目、章节、台词和知识点表
```

现有小说服务继续保持职责清晰，不要把文章逻辑加入 `SourceParserService` 的小说 Prompt。

## 6. 数据模型设计

### 6.1 会话和运行记录扩展

在 `ChatSessionPO` 和 `AdaptationRunPO` 增加或确认以下字段：

```text
source_type
input_method
source_url
source_title
source_author
source_account_name
source_published_at
article_category
adaptation_mode
learning_goal
target_duration_minutes
verification_mode
```

推荐值：

```text
source_type:
  novel
  knowledge_article

adaptation_mode:
  drama
  audio_lesson
  knowledge_drama

verification_mode:
  source_only
  external_verification
```

### 6.2 原文资料表

如果当前 `SourceDocumentPO` 已经满足来源保存需求，应扩展它；否则新增文章来源表。

字段建议：

```text
ArticleSourcePO
  id
  project_id
  session_id
  input_method
  source_url
  title
  author
  account_name
  published_at
  raw_content
  normalized_content
  content_hash
  fetch_status
  rights_confirmed
  created_at
  updated_at
```

重要约束：

- URL 和正文都必须允许保存。
- 正文清洗后仍要保留原始版本或可追溯内容。
- 同一文章可以形成多个改编 revision。
- 不要把链接抓取成功等同于用户拥有内容使用权。

### 6.3 文章分析表或 JSON

第一版可以复用 `AdaptationRunPO` 的 JSON 字段快速落地，但结构必须固定：

```text
article_analysis_json
learning_plan_json
knowledge_review_json
external_sources_json
```

长期建议增加规范化表：

```text
KnowledgePointPO
  id
  session_id
  revision
  title
  explanation
  importance
  category
  source_excerpt
  source_location
  is_ai_supplement
  status

KnowledgeEvidencePO
  id
  knowledge_point_id
  source_type
  source_url
  source_title
  excerpt
  verification_status
```

### 6.4 音频台词与知识点关联

用户要求查看“原文依据”和“音频中对应的知识点”，因此必须建立以下关系：

```text
KnowledgePoint
  -> source excerpts
  -> script lines
  -> audio tasks
  -> audio variants
```

可以有两种实现路径：

第一版：

- 在草稿 revision JSON 中保存映射。
- 提交后将映射保存到台词 metadata JSON。

长期版：

- 新增 `KnowledgePointLinePO` 映射表。
- 支持一个知识点对应多句台词。
- 支持一条台词解释多个知识点。

## 7. 文章分析结构

建议 `ArticleAnalysis` 至少包含：

```text
title
summary
category
audience
estimated_reading_level
sections
key_points
terms
examples
claims
assumptions
limitations
source_spans
recommended_format
recommended_duration
```

### 7.1 核心知识点

每个知识点应包含：

```text
id
title
one_sentence_summary
explanation
importance
source_excerpt
source_location
example
common_misunderstanding
audio_order
```

### 7.2 事实、观点和补充内容

分析时必须区分：

```text
fact_from_source
opinion_from_source
example_from_source
ai_explanation
external_verified_fact
uncertain_claim
```

这一区分直接影响脚本中的措辞和界面标识。

## 8. AI 生成策略

### 8.1 文章模式必须使用独立 Prompt

不得直接调用小说专用规则，例如：

- 零旁白优先。
- 心理活动必须转为动作声。
- 场景冲突优先。
- 删除视觉描写。

文章模式应采用自己的规则：

- 保留核心事实和原文论证关系。
- 先讲结论，再解释原因。
- 复杂概念必须给出通俗解释。
- 每个重要概念至少配一个例子。
- 将专业术语首次出现时解释清楚。
- 对不确定观点保留限定语。
- 不把 AI 补充写成原文观点。
- 每个知识点都要能回指原文或外部来源。
- 每隔一段设置自然的总结或回忆提示。

### 8.2 自动选择音频形式

`LearningDesignService` 根据文章特征推荐：

```text
信息密度高、论点明确 -> 主持人讲解
概念多、初学者导向 -> 师生对话
案例多、商业管理类 -> 案例化知识剧场
```

界面显示推荐理由，但允许用户切换。

### 8.3 生成长度控制

不能只用原文字符数估算，需要同时考虑：

- 目标音频分钟数
- 语速
- 知识点数量
- 对话角色数量
- 复习问题数量
- 文章原始信息密度

若文章太长，应先生成“文章地图”和章节摘要，再让用户选择处理整篇或指定部分。

## 9. 文章审查系统

### 9.1 内容准确性审查

检查：

- 核心结论是否保留。
- 关键限定条件是否被删除。
- 因果关系是否被改写。
- 数字、时间、人物、概念是否准确。
- AI 是否生成原文没有的事实。
- 外部补充是否有来源。

### 9.2 学习质量审查

检查：

- 是否有清晰的开头和结尾。
- 知识点顺序是否合理。
- 是否解释了专业术语。
- 是否出现长时间单向信息倾倒。
- 是否有例子或类比。
- 是否提供了复习和回忆机会。
- 是否为了戏剧效果破坏准确性。

### 9.3 音频质量审查

继续复用现有能力：

- TTS 纯文本不能含制作提示。
- 音效和配乐不能混入朗读文本。
- 角色声音指导和朗读文本分离。
- Edge-TTS 的能力差异必须明确展示。

## 10. 联网查证策略

### 10.1 两种模式

```text
仅基于原文
  只压缩和解释用户提供的内容

联网查证并标记补充
  对重要事实进行外部检索
  允许补充背景
  所有补充内容展示来源和标记
```

默认使用“仅基于原文”。

### 10.2 外部补充的展示规则

音频脚本中不应该让用户猜测内容来源。可以使用以下标识：

```text
[原文观点]
[AI 解释]
[外部资料补充]
[待确认]
```

界面中显示来源，音频中不必机械朗读这些标签，但对应知识点卡片必须标记。

### 10.3 链接抓取失败处理

必须支持以下失败状态：

- 链接无法访问。
- 文章内容为空。
- 页面包含大量非正文内容。
- 需要登录或权限。
- 抓取内容与用户预期不符。
- 正文超过处理长度。

每种失败都提供“粘贴正文继续”的路径。

## 11. API 方案

### 11.1 创建会话

现有 `POST /chat/sessions` 扩展请求字段：

```json
{
  "project_id": 1,
  "source_type": "knowledge_article",
  "input_method": "url",
  "source_url": "https://example.com/article",
  "source_text": null,
  "article_category": "technology",
  "learning_goal": "quick_understanding",
  "target_duration_minutes": 10,
  "adaptation_mode": "auto",
  "verification_mode": "source_only",
  "instruction": "用容易理解的方式解释给没有技术背景的人"
}
```

### 11.2 文章来源 API

建议增加：

```text
POST /chat/article-sources/preview
POST /chat/article-sources/import
GET  /chat/article-sources/{id}
POST /chat/article-sources/{id}/normalize
```

其中 `preview` 只做抓取和内容预览，不启动 LLM 改编。

### 11.3 文章分析 API

```text
POST /chat/sessions/{session_id}/article/analyze
GET  /chat/sessions/{session_id}/article/analysis
POST /chat/sessions/{session_id}/article/learning-plan
```

### 11.4 大纲确认 API

```text
POST /chat/sessions/{session_id}/article/outline/confirm
POST /chat/sessions/{session_id}/article/outline/revise
```

### 11.5 脚本和审查 API

```text
POST /chat/sessions/{session_id}/article/script/generate
GET  /chat/sessions/{session_id}/article/review
POST /chat/sessions/{session_id}/article/script/revise
POST /chat/sessions/{session_id}/article/script/confirm
```

### 11.6 知识复习 API

```text
GET  /chat/sessions/{session_id}/knowledge-points
GET  /chat/sessions/{session_id}/review-questions
POST /chat/sessions/{session_id}/review-questions/{id}/answer
```

这些接口不要求第一版实现完整学习系统，但数据结构应提前留出扩展空间。

## 12. 工作流状态机

### 12.1 小说状态机保持现状

```text
created
  -> parsing
  -> awaiting_role_confirmation
  -> generating_script
  -> reviewing_script
  -> awaiting_script_confirmation
  -> completed
```

### 12.2 文章状态机

```text
created
  -> importing_source
  -> source_ready
  -> analyzing_article
  -> outline_ready
  -> awaiting_outline_confirmation
  -> designing_learning_plan
  -> generating_knowledge_script
  -> reviewing_knowledge_script
  -> awaiting_script_confirmation
  -> committed
  -> generating_audio
  -> audio_ready
  -> completed
```

失败和取消状态可以复用：

```text
failed
cancelled
expired
```

### 12.3 文章模式的人工确认点

第一版至少保留两个确认点：

1. 知识大纲确认。
2. 音频脚本确认。

后续可增加：

- 外部查证结果确认。
- 学习问题确认。
- 音频试听确认。

## 13. 前端改造方案

### 13.1 新增页面或视图

建议不新增独立产品导航，而是在现有 Studio 内切换制作类型。

新增组件：

```text
sonicvale-front/src/components/article/
  ContentTypeSelector.vue
  ArticleSourceInput.vue
  ArticlePreview.vue
  ArticleSettingsPanel.vue
  ArticleAnalysisCard.vue
  KnowledgeOutlineCard.vue
  KnowledgePointCard.vue
  SourceEvidencePanel.vue
  LearningPlanCard.vue
  ArticleScriptPanel.vue
  KnowledgeReviewPanel.vue
  ReviewQuestionCard.vue
```

### 13.2 需要修改的现有页面

| 文件 | 改造内容 |
| --- | --- |
| `src/pages/Studio.vue` | 增加内容类型选择和文章模式入口 |
| `src/pages/ProjectWorkspace.vue` | 根据小说/文章模式展示不同工作区布局 |
| `src/pages/ProjectOverview.vue` | 展示文章分析、知识大纲、音频和复习状态 |
| `src/pages/QueueBoard.vue` | 增加文章分析任务、查证任务和知识音频任务 |
| `src/pages/ProjectDubbingDetail.vue` | 展示文章音频章节和知识点关联 |
| `src/components/workflow/ChatProductionPanel.vue` | 适配文章模式的消息、阶段和操作 |
| `src/components/workflow/ChatMessageList.vue` | 支持知识点卡片、证据卡片和审查结果 |
| `src/components/workflow/ProductionScriptPanel.vue` | 增加文章脚本和知识点定位展示 |
| `src/components/workflow/ChatComposer.vue` | 支持文章模式下的自然语言修改 |
| `src/api/drama.js` | 增加文章会话和文章流程接口 |
| `src/api/queue.js` | 增加文章相关任务接口 |
| `src/App.vue` | 统一文章音频事件、错误和恢复处理 |

### 13.3 文章工作台布局

建议采用三栏结构：

```text
左侧：制作助手和用户反馈
中间：文章分析、知识大纲或脚本
右侧：原文依据、知识点和审查结果
```

生成音频后，中间区域切换为播放器和台词，右侧保留知识点定位。

不要把原文、脚本、知识点和审查结果全部堆叠在一个长页面中。用户需要清楚知道当前正在确认什么。

## 14. 制作助手适配

当前制作助手已经具备项目级工具调用能力。文章模式下增加以下能力：

```text
inspect_article
inspect_knowledge_points
inspect_source_evidence
revise_knowledge_point
revise_learning_plan
revise_article_script
remove_ai_supplement
find_related_script_lines
generate_review_questions
play_knowledge_segment
```

助手必须继续使用独立 system prompt：

- 不能复用小说解析 Prompt。
- 不能把文章知识点直接当成小说角色。
- 不能在没有用户确认时直接覆盖正式脚本。
- 不能把外部查证结果伪装成原文内容。

用户可以自然语言提出：

```text
把第二个知识点讲得更适合完全没有技术背景的人。

删除所有不是原文内容的补充。

用一个商业案例解释这个概念。

告诉我这段音频对应文章哪一部分。

重新生成第 3 个复习问题。
```

## 15. TTS 与音频设计

### 15.1 角色设计

文章模式不需要默认生成大量角色。

推荐角色模板：

```text
主持人/讲解者
学习者/提问者
案例人物，可选
```

最多建议使用 2 到 3 个声音，避免知识音频变成复杂广播剧，增加用户认知负担。

### 15.2 音频段落

文章音频可按知识点分段：

```text
开场
知识点 1
知识点 2
案例
知识点 3
总结
复习问题
```

每个段落都应能单独播放和重新生成。

### 15.3 复习问题不一定需要 TTS

第一版可以先在页面中展示复习问题，不强制将问题全部合成音频。后续可以增加：

- 音频中停顿后提问。
- 用户思考后播放答案。
- 错题对应片段重听。

## 16. 版权、隐私和内容风险

公众号文章功能必须增加产品提示：

- 用户应确认有权使用导入内容。
- Auralis 不默认公开分发原文或生成音频。
- 原文链接、作者和公众号信息应保留归属说明。
- 用户可以删除原文和生成内容。
- 外部查证不等于事实保证。
- 医疗、法律、投资等高风险领域需要额外提示。

面试展示可以使用用户拥有或明确允许使用的文章，避免展示不必要的版权争议。

## 17. 性能与可靠性

### 17.1 长文处理

文章长度超过单次 LLM 处理限制时：

```text
文章切分
  -> 分段摘要
  -> 合并文章地图
  -> 统一提取知识点
  -> 生成最终大纲
```

不能简单截断文章尾部，否则容易漏掉结论和限制条件。

### 17.2 任务拆分

文章流程应拆分为可观察任务：

- source fetch
- normalize
- article analysis
- learning plan
- script generation
- knowledge review
- external verification
- TTS generation

每个任务都要显示状态、耗时、失败原因和重试入口。

### 17.3 幂等

以下操作必须幂等：

- 文章导入。
- 文章分析。
- 大纲确认。
- 脚本确认。
- 写入项目。
- 音频批量生成。
- 单句音频重新生成。

## 18. 测试方案

### 18.1 文章输入测试

- 正常公众号链接。
- 无法访问的链接。
- 页面中正文为空。
- 内容包含大量广告和导航。
- 文章包含代码、表格和列表。
- 文章包含多个图片说明。
- 粘贴正文超过长度限制。
- URL 和正文同时提交。

### 18.2 知识结构测试

- 核心知识点不为空。
- 文章观点和事实正确区分。
- 每个核心知识点有原文依据。
- AI 补充内容有单独标记。
- 无法确认的内容进入待确认列表。

### 18.3 脚本测试

- 主持人模式生成成功。
- 师生对话生成成功。
- 案例剧场生成成功。
- 复习问题生成成功。
- 台词包含知识点关联。
- 制作提示不会进入 TTS 文本。
- 脚本局部修改不会破坏其他知识点。

### 18.4 恢复和并发测试

- 页面刷新后恢复文章会话。
- LLM 失败后重试当前步骤。
- 外部查证失败后继续使用原文模式。
- 重复确认不产生重复章节。
- 多个文章会话同时运行时相互隔离。
- WebSocket 断线后可以恢复事件和状态。

### 18.5 回归测试

现有小说流程必须继续通过：

- 小说解析。
- 角色确认。
- 台本生成。
- 广播剧审查。
- 台本提交。
- TTS 生成。
- 音频 take 管理。
- 连播和导出。

## 19. 分阶段开发计划

### Phase 0：架构准备

工作量：中。收益：高。

目标：为内容类型分流建立边界，不改变小说流程。

任务：

- 增加 `source_type` 和 `adaptation_mode`。
- 增加文章会话阶段枚举。
- 抽离统一的内容改编入口。
- 设计文章 JSON schema。
- 确认 SourceDocument 的复用或扩展方案。
- 增加文章模式功能开关。

验收：小说流程行为不变，文章模式可以显示“开发中”或关闭。

### Phase 1：文章导入与预览

工作量：中到大。收益：高。

任务：

- 支持粘贴正文。
- 支持公众号 URL 预览。
- 保存标题、作者、来源链接和正文。
- 增加清洗和正文确认。
- 处理抓取失败和正文过长。

验收：用户可以导入文章并确认实际正文，失败时可以粘贴正文继续。

### Phase 2：文章分析和知识大纲

工作量：大。收益：高。

任务：

- 新增 ArticleAnalysisService。
- 提取章节、观点、术语、例子和知识点。
- 增加学习目标和音频时长设置。
- 生成知识大纲。
- 支持用户确认或修改知识点。

验收：文章分析结果可读，每个核心知识点都能回指原文。

### Phase 3：知识音频脚本

工作量：大。收益：高。

任务：

- 新增 LearningDesignService。
- 新增 KnowledgeScriptService。
- 实现主持人、师生对话和案例剧场模板。
- 根据文章特征自动推荐模板。
- 输出知识点到音频台词的映射。
- 生成复习问题。

验收：用户可以确认文章大纲后生成可编辑的知识音频脚本。

### Phase 4：知识审查和证据展示

工作量：大。收益：高。

任务：

- 新增 KnowledgeReviewService。
- 增加事实准确性审查。
- 增加知识覆盖率检查。
- 增加学习质量检查。
- 展示原文依据。
- 支持删除 AI 补充内容。

验收：用户能分清原文内容、AI 解释和外部补充。

### Phase 5：TTS 和复习闭环

工作量：中到大。收益：高。

任务：

- 复用现有 TTS 任务队列。
- 文章音频按知识点分段。
- 支持知识点片段重听。
- 展示核心知识点和复习问题。
- 记录用户的复习结果。

验收：文章可以完成“导入 -> 生成 -> 配音 -> 播放 -> 复习”的完整闭环。

### Phase 6：联网查证

工作量：大。收益：中到高。

任务：

- 增加外部检索服务。
- 对关键事实做来源匹配。
- 保存外部来源。
- 标记 AI 补充内容。
- 支持用户删除或忽略补充。

验收：联网查证失败不会阻塞原文改编，所有补充内容都有来源和标签。

### Phase 7：截图、长文和系列课程

工作量：大。收益：中。

任务：

- OCR/视觉输入。
- 文章图片和图表解析。
- 多篇文章合并。
- 课程目录。
- 文章版本更新。
- 个性化学习计划。

## 20. 发布开关和回滚

建议增加：

```text
KNOWLEDGE_ARTICLE_ENABLED
KNOWLEDGE_ARTICLE_URL_ENABLED
KNOWLEDGE_ARTICLE_EXTERNAL_VERIFY_ENABLED
KNOWLEDGE_ARTICLE_VISION_ENABLED
```

发布顺序：

1. 先发布数据库和兼容 DTO。
2. 开启正文导入和文章分析。
3. 开启知识大纲确认。
4. 开启知识脚本生成。
5. 开启 TTS 和复习问题。
6. 最后开启 URL 抓取和联网查证。

回滚时关闭文章功能开关，不影响小说广播剧流程和已经完成的项目。

## 21. 大版本验收标准

### 产品验收

用户能够：

1. 选择“小说广播剧”或“知识文章音频”。
2. 通过公众号链接或正文导入文章。
3. 看到并确认清洗后的正文。
4. 选择学习目标和音频时长。
5. 查看文章结构和核心知识点。
6. 查看每个知识点的原文依据。
7. 确认或修改知识大纲。
8. 让 AI 自动选择或切换音频表现形式。
9. 生成知识音频脚本。
10. 查看脚本对应的知识点。
11. 查看内容审查结果和学习质量审查结果。
12. 区分原文、AI 解释和外部补充。
13. 确认脚本后生成音频。
14. 按知识点播放、重听和重新生成。
15. 完成听后复习问题。

### 技术验收

- 现有小说流程无回归。
- 文章和小说会话状态互相隔离。
- 文章导入和改编支持恢复。
- 重复请求不会重复写入项目。
- URL 抓取失败有正文兜底。
- 长文本不会静默截断。
- TTS 不朗读制作提示。
- 外部补充有来源记录。
- WebSocket 事件按项目和会话隔离。
- `./scripts/verify.sh` 继续通过。

## 22. 面试展示建议

面试演示不要展示所有功能，建议准备一个完整的 5 分钟流程：

```text
1. 新建知识文章音频
2. 粘贴一篇技术或商业文章
3. 展示文章来源和清洗结果
4. 展示 AI 提取的 5 个核心知识点
5. 展示每个知识点的原文依据
6. 让 AI 推荐“师生对话”形式
7. 用户确认大纲
8. 展示脚本和事实审查结果
9. 展示一段已生成的音频
10. 展示听后复习问题
```

演示重点不是“模型生成了很多文字”，而是：

- 用户目标明确。
- AI 中间产物可见。
- 知识点有来源。
- AI 补充有标记。
- 用户可以修改和确认。
- 音频与学习结果连接起来。

## 23. 下一次开发对话的执行顺序

新对话开始后，建议严格按以下顺序执行：

1. 阅读 `docs/AI-HANDOFF.md`。
2. 阅读本方案文件。
3. 检查当前工作区和最新分支状态。
4. 阅读现有 `ChatSessionPO`、`AdaptationRunPO`、`SourceDocumentPO` 和迁移逻辑。
5. 阅读 `Studio.vue`、`ProjectWorkspace.vue` 和现有工作流 API。
6. 先输出当前代码与本方案的差异清单。
7. 设计并实现 Phase 0 的数据字段和功能开关。
8. 先完成粘贴正文的文章模式，再实现 URL 抓取。
9. 每个阶段完成后运行相关测试。
10. 不修改小说流程，除非发现明确回归问题。

下一次对话可以直接使用以下启动指令：

```text
请阅读当前项目的 docs/AI-HANDOFF.md 和 docs/knowledge-article-major-update-plan.md。

基于当前代码仓库作为唯一真实来源，先不要修改代码。

请检查文章模式 Phase 0 所需的现有模型、DTO、路由、服务和 Vue 页面，输出：

1. 当前实现与方案的差异。
2. 最小修改文件清单。
3. 数据库字段和迁移方案。
4. 小说流程不受影响的兼容方案。
5. 实施顺序和测试方案。

确认后再开始实现。
```

## 24. 最终决策摘要

- 增加“内容类型选择”，不是增加一个普通场景选项。
- 小说流程保持现有实现。
- 文章流程作为第二条业务流水线加入同一个工作台。
- 第一版聚焦科普、技术、商业和管理文章。
- 第一版支持公众号链接和粘贴正文。
- 截图输入后置。
- 默认目标是“比阅读更轻松，并帮助用户记住核心观点”。
- 输出不是强制完整广播剧，而是自动选择知识音频表达形式。
- 文章必须有知识大纲、原文依据和复习问题。
- AI 外部补充必须显式标记并保存来源。
- 文章模式必须使用独立 Prompt、schema 和审查服务。
- 现有 TTS、音频版本和导出能力继续复用。
- 当前架构继续使用 SQLAlchemy 状态机，不恢复 LangGraph。
- 先实现文章正文闭环，再实现 URL 抓取、联网查证和截图输入。
