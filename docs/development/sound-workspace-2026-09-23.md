# 台词与声音编排入口调整

基线：`master@7bef443`。本轮按用户截图调整正式章节制作页面，保留已有音效行、素材、音频版本与手工时间线；未改数据库结构或供应商调用。

- 台本视图只显示对白、旁白及文字编辑；配音视图保留人声生成和试听。音效/BGM 数量提供到编排页的入口，原始行号保留。
- 编排页新增 `ChapterSoundMaterials`，显示声音说明、标签和可用素材的原音播放器。可用性来自已有 `audio_sources` 解析结果；缺少文件或尚未绑定素材时显示文字提示。
- 播放一个素材时暂停其他试听；刷新和离开页面时停止播放。原音试听不模拟时间线的裁剪、循环、音量和淡入淡出，最终效果仍通过 FFmpeg 成片检查。
- 复用已有片段编辑、铺满人声、循环和时长调整。素材选择、类型修改与移除仍在编排页可用；`LineTypeDialog` 由台词页和声音列表共用，调用原类型修改 API。
- 浏览器验证发现“刷新时间线”未同步更新章节条目，补回归后修复，避免新增背景音乐未出现在列表中。缺失声音从导出页跳回编排，从编排页进入素材选择。
- 改编审查阶段的完整声音设计仍可审阅；本轮显示过滤只影响正式制作视图，不删除声音设计或自动保存编辑。

## 验证

先运行 `node --experimental-default-type=module --test sonicvale-front/tests/sound-workspace.test.mjs`：原实现的台词列表包含 4 行而预期 2 行，且编排页缺少声音列表，两项失败。文字视图的播放器检查随后复现失败；刷新新增声音的回归也先得到 `0 !== 1`，再修复。

最终 `./scripts/verify.sh` 通过：220 项后端测试（9.351 秒）、39 项前端测试、147 个 API 路由、隔离 API/FFmpeg smoke、Electron 语法检查、普通构建（3.00 秒）与 Demo 构建（2.88 秒）。既有大 chunk 告警仍在。`git diff --check` 通过。

实际浏览器使用临时 SQLite/配置和假模型：

```bash
SonicVale/.venv/bin/python scripts/fake_workspace.py
# 另一个终端，在 sonicvale-front 目录：
VITE_API_BASE_URL=http://127.0.0.1:18200 npm run dev -- --host 127.0.0.1 --port 5175 --strictPort
# 仓库根目录，按顺序运行：
~/.local/bin/tabbit-cli nodejs --task auralis-sounds --request-id fixture --timeout-ms 60000 < scripts/browser_smoke.js
~/.local/bin/tabbit-cli nodejs --task auralis-sounds --request-id sounds --timeout-ms 60000 < scripts/browser_sound_smoke.js
```

完整制作、WAV 文件验证通过；声音专项通过：2 条对白、3 条声音说明、2 个可播放素材、1 个未绑定条目；媒体进入实际播放状态，第二个试听会暂停第一个，离开编排后停止播放；背景音乐保存后从 API 读回 `duration_ms=60000`；类型编辑入口可用，页面无 `pageerror`。已检查桌面截图。

测试准备阶段一次因缺少定位台词被 API 拒绝，读取状态后补齐，未重复新增条目。一次媒体检查早于刷新完成，等待刷新结束后通过；没有移除播放断言。日志保存在本机 `/tmp/auralis-sound-*.log`，可用以上入口重跑。

未调用真实 LLM/TTS、未访问真实项目数据库；未验收人工听感、打包 Electron 或所有屏幕尺寸。没有部署公开 Demo。
