# 悬疑 / 都市 Demo：音色与表演指令实测

日期：2026-09-05。原创台词来自 `sonicvale-front/src/demo/suspense.json` 的《雨夜来件》，不使用用户私人小说。没有改动用户原有项目、角色绑定或阿里云供应商配置；另建的导演 Demo 工程仅导入已有音频。调用时仅从本地配置读取凭证，报告和前端不包含凭证或带签名的下载地址。

## 已完成的结果

使用阿里云真实 API 生成 **22 条剧情音频 + 6 条同文候选试听**，所有请求成功。28 个 MP3 均通过 FFmpeg 完整解码，合计 684,107 字节。导演版对白总长 27.92 秒；无指令版 28.08 秒（均不含雨声、音效与场间停顿）。

- 主模型固定为 `qwen3-tts-instruct-flash-2026-01-26`，避免别名升级影响复现。
- 林澈：`Moon`（月白）；许遥：`Maia`（四月）；旁白：`Vincent`（田叔）。这是根据官方声线描述和角色需求做的初选。
- 每句有 `directed` 与 `neutral` 两个 take，**同文本、同模型、同音色，仅是否提供表演指令不同**。模型采样仍有随机性，一次 A/B 不足以证明普遍优势。
- 资产清单：`sonicvale-front/public/demo-night/manifest.json`。包含原文哈希、音频哈希、时长、调用时间、模型和逐句指令；文件名相对 `demo-night/`。
- 所有 take 均转换成同一 MP3 编码规格，未做音量归一化或改变语速，因此保留模型原有演绎差异。

**验证边界：已验证真实合成、输入分离和完整解码；当前执行通道不支持音频输入，无法人工听感判断。不能把候选称为“自然度最佳”，不能把 API 成功等同于自然或没有错读。** Demo 提供 A/B 与候选播放，供人在耳机下选择。

## 为什么原来的声音可能显得僵硬

当前项目的阿里云供应商使用 `cosyvoice-v3-flash`，默认 `longanhuan`，预置库主要提供 `longanyang`、`longanhuan` 和女童 `longhuhu_v3`。它们接受固定情感语法，不能把“像在门边压低声音，试图安慰对方”一整段表演指导直接当作自由指令。

此次代码审计发现并修正：

1. **错误的语速/音高单位。** 旧代码把指导映射为 `speech_rate=-20/20`、`pitch_rate=-10/10`。官方参数是 **0.5–2.0 倍率，默认 1.0**，不是百分比。现改成温和的 0.94/1.06 与 0.97/1.03，并在联网前校验非法配置；原生指令模型不再叠加机械变调。[官方 Python SDK](https://help.aliyun.com/zh/model-studio/cosyvoice-python-sdk)
2. **旧 Qwen3-TTS 指令没有正确进入请求。** 应为 `input.instructions`（复数），旧实现用了 `input.instruction` 且默认未启用。现按模型自动发送，明确禁止的配置仍优先。[非实时语音合成](https://help.aliyun.com/zh/model-studio/non-realtime-tts-user-guide)
3. **把整个 CosyVoice v3 系列都当作支持同样指令。** 现按音色处理：三个旧情感音色使用固定格式；龙三叔等其他系统音色仅映射基础参数；v3-flash 复刻音色支持自由指令；v3-plus 复刻音色不按自由指令处理。`longanhuan_v3` 的指令主要是方言格式，不等于旧 `longanhuan` 的情感格式。[CosyVoice 音色列表](https://help.aliyun.com/zh/model-studio/cosyvoice-voice-list)
4. 原先已经正确书写的 `你说话的情感是fearful。` 会被中文关键词映射丢成 neutral。现保留正确的固定情感指令。
5. 原声线导入把 v1 音色编号直接用于 v2。现在阻止不兼容导入并给出提示；v3-flash 新增成年男声龙天、女声龙婉君和旁白龙三叔，明确标注“基础韵律”，不标注 Instruct。

## 试听与选角

六个样本都读同一句原创对白：

> 别开门。先听我说，门外的人，刚刚用的是你的声音。

| 候选 | 模型 | 用途初选 | 演绎能力 / 对比边界 |
| --- | --- | --- | --- |
| Moon / 月白 | Qwen3-TTS-Instruct-Flash 2026-01-26 | 青年男角 | 完整自然语言指令 |
| Maia / 四月 | 同上 | 都市女角 | 完整自然语言指令 |
| Vincent / 田叔 | 同上 | 有沙哑辨识度的旁白 | 完整自然语言指令 |
| longanyang / 龙安洋 | CosyVoice-v3-flash | 现有男声对照 | 固定情感 + 基础韵律 |
| longanhuan / 龙安欢 | CosyVoice-v3-flash | 现有女声对照 | 固定情感 + 基础韵律 |
| longsanshu_v3 / 龙三叔 | CosyVoice-v3-flash | 另一种成年旁白 | 仅基础韵律，不支持自由演绎 |

前三个音色均在官方非实时 Instruct 型号支持列表中。官方描述是选角线索，不是本项目的听感评分。[Qwen-TTS 音色列表](https://help.aliyun.com/zh/model-studio/qwen-tts-voice-list)

建议先隐藏型号盲听，逐项记录 1–5 分：日常对话自然度、人物辨识度、潜台词/紧张递进、停顿与重音、发音准确性。先比较同句的 directed / neutral，再比较六种声线；不同模型的候选比较同时含模型与声线差异，不能归因于某个提示词。不要只用“越激动越好”选声音。

## 新增 Qwen-Audio 3.0 候选，保留原成片

按用户最新要求，已有 28 个 MP3、原 `manifest.json`、工程 12 的当前 take **全部保留原样**，不替换已生成配音。后续新建配置默认使用用户指定的 `qwen-audio-3.0-tts-plus`，也提供 `qwen-audio-3.0-tts-flash` 模板；不再通过本轮生成脚本调用旧收费型号。可用额度和仅免费调用设置以用户百炼控制台为准，这两个型号本身并非永久免费。

通过真实 API 只新增三条独立短句试听，均完整解码成功。首先验证 Plus 一条成功后才继续另外两条，总共发送 102 个输入字符（含三次对白和表演指导）。未改数据库或现有角色绑定。

| 新候选 | 实际模型 | 时长 | 本地文件 |
| --- | --- | --- | --- |
| 龙安灵心 `longanlingxin` | qwen-audio-3.0-tts-plus | 3.504 秒 | free-auditions/qwen-audio-plus-lingxin.mp3 |
| 龙安鲁风 `longanlufeng` | qwen-audio-3.0-tts-plus | 3.648 秒 | free-auditions/qwen-audio-plus-lufeng.mp3 |
| 龙安风悦 `longanfengyue` | qwen-audio-3.0-tts-flash | 3.888 秒 | free-auditions/qwen-audio-flash-fengyue.mp3 |

新增清单为 `sonicvale-front/public/demo-night/free-candidates.json`，路径均相对 `demo-night/`。三条都使用“别开门。门外的人，刚刚用的是你的声音。”，指令为“低声克制，句间换气，尾音收住。”。这句比最初六条少“先听我说”，因此只作为新增候选，**不能与原六条标作严格同文 A/B**。Plus/Flash 的模型也不同，仍需人工盲听，不宣称自然度最佳。

新引擎按官方文档使用 `POST /api/v1/services/audio/tts/SpeechSynthesizer`，表演指导放 `input.instruction`（单数），语种为 `input.language_hints`，音频格式与采样率也在 `input` 中。官方确认现有 `dashscope.aliyuncs.com` 域名继续可用；工作空间域名亦支持。旧 Qwen3-TTS 仍走多模态端点及 `input.instructions`（复数）。两个系列与 Plus/Flash 音色不能混用，现会在请求前拒绝不匹配音色。[官方 HTTP API](https://help.aliyun.com/zh/model-studio/cosyvoice-tts-http-api)、[官方音色列表](https://help.aliyun.com/zh/model-studio/qwen-audio-tts-voice-list)

## 重现

在仓库根目录运行（默认只显示计划，不联网）：

```bash
SonicVale/.venv/bin/python scripts/generate_voice_demo.py
```

已有目录受到保护，`--generate` 会在读取凭据/联网前拒绝，不提供覆盖开关。若未来另行授权新实验，必须传入新的 `--output-dir`；该脚本只允许指定的 Qwen-Audio 3.0 型号，逐条执行，任何失败立即停止。原台词两套配音本轮不再重新生成。

新增候选脚本默认仅显示计划：

```bash
SonicVale/.venv/bin/python scripts/probe_free_voice_candidates.py
```

它要求先 `--probe` 单条成功才允许 `--generate`，已有候选会核对哈希并跳过；已存在清单时拒绝，失败后禁止自动重试。新音频路径、原文哈希和参数独立记录，原 Demo 文件不变。

回归验证：

```bash
PYTHONPATH=SonicVale SonicVale/.venv/bin/python -m unittest discover -s SonicVale/tests -p 'test_tts*.py'
```

本轮 28 项 TTS 单测通过，覆盖原生/结构化/基础映射能力、Qwen 请求体、固定情感保留、非法倍率拒绝、CJK 指令长度、新 Qwen-Audio 专属端点与单数指令、跨模型音色拒绝、SDK 实际调用参数，以及用户改音色显示名后仍使用正确 Qwen 音色 ID。台词继续走现有 `LineService.clean_tts_text`，括号备注在送入 TTS 之前清理；声音指导放在指令字段，音效作为独立时间线素材，不串进朗读文本。

## 从音色库使用新配音

1. 音色管理点击“配置 Qwen 广播剧配音”，打开新增引擎表单。模型、接口与参数已填写；若已有同一阿里云接口的凭证，会填入未保存表单的密码框。用户保存前不会写入配置。
2. 保存后回到音色管理，选中该引擎，点击“导入对应模型音色”。Plus 导入龙安灵心、龙安鲁风，Flash 导入龙安风悦、龙安欢 v3.6、龙川叔 v3.6；旧 Qwen3 引擎仍可使用月白、四月、田叔的原试听。重复导入跳过同音色，现有记录与角色绑定不变。
3. 音色库可播放已经生成的 MP3 试听，未实测候选不显示虚构播放入口。导入、试听均不调用 TTS API；实际生成新台词时才使用配置的云端接口。
4. 在项目中选择需要改配的角色，再绑定新音色。音色标签中的 `qwen_voice` 保存 API 声线 ID，显示名可以自行修改。

配置中心展示的是默认音色能力；音色库每行按具体音色标注“原生表演指令”“固定情感指令”或“基础韵律”。前端构建及能力映射检查通过；这些检查不等于浏览器实际播放验证。
