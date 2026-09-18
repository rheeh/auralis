# 本地验证结果与验收覆盖

日期：2026-09-16。分支 `master`，HEAD `5aed5b8391d848e7e7e1191c551caa882d5de82f`，修改保留在本地工作区，未提交/推送/部署。此文件记录工程证据；完整剩余清单以 [BACKLOG](../../../BACKLOG.md) 为准。

## 最终执行结果

执行：

```bash
./scripts/verify.sh
```

真实结果：

| 检查 | 结果 |
| --- | --- |
| 隔离后端 unittest | 202 项通过，7.397 秒 |
| 所有 src/tests 前端 Node 测试 | 31 项通过，0 失败，937.101 毫秒 |
| API 路由注册 | 147 个路由检查通过 |
| API + 真实 FFmpeg smoke | TTS 素材跳过、readiness、素材浏览/上传/绑定/删除、时间线编辑/渲染/下载、素材附加、路由策略、混合格式导出/处理均通过 |
| Electron main/preload | Node 语法检查通过；不等于打包运行验收 |
| 普通前端 build | 通过，2.54 秒 |
| 静态 Demo build | 通过，2.54 秒 |
| git diff --check | 通过 |

两次 build 都有 >500 kB chunk warning，未为消除警告改动构建策略。开发服务器另提示既有 DemoSceneFrame 的 figcaption 嵌套语义警告，未改变该视觉组件。故障注入测试会写预期异常日志；测试进程最终退出 0，不能把预期 ERROR 行隐藏或当作产品事故。原始本机过程输出在 `/tmp/auralis-verification-final.log`，临时日志可能随系统清理消失；上面的命令可独立复现。

隔离方式：测试配置在 TemporaryDirectory；SQLite 和音频 fixture 为临时创建；AURALIS_TEST_OFFLINE=1 的 sitecustomize 拒绝 Python 外部网络连接。FFmpeg 处理是真实本机执行，LLM/TTS 输出为固定 fake/mock。测试没有打开真实 `.local-data` 数据库。

## 浏览器实际闭环

`tabbit-cli nodejs --task auralis-reliability --request-id final-full-browser --timeout-ms 120000 < scripts/browser_smoke.js`：通过，9.557 秒，`errors=[]`、WAV HTTP 200 / `audio/wav`。

覆盖固定原文 → fake 人物/台本/审查 → 用户确认 → 两句 fake TTS → 重新生成第二 take → 切回版本 1/2 → 加入内置环境素材 → 真实 FFmpeg 渲染 10.1 秒、3 个片段 → 刷新仍能读取当前成片。测试数据在临时目录，退出 fake 后端后清理。

另验静态 Demo 的预生成声明、播放/暂停、截图布局；播放请求只有 `demo-night/audio` / `demo-night/sfx` 预置文件，没有模型生成接口。没有修改用户已有公开网站，也没有重新部署。

下载边界：页面下载按钮触发的成片读取已验证 HTTP 200/audio/wav，服务端烟测也验证了 WAV 内容。Tabbit 的 download 事件等待超时，**未验证用户下载目录中的最终文件落盘**。

复现浏览器闭环（两个终端，均在仓库根目录开始）：

```bash
# 终端 1：只创建临时库与固定 fake 模型，后端固定监听 18200
SonicVale/.venv/bin/python scripts/fake_workspace.py

# 终端 2：前端连隔离后端
cd sonicvale-front
VITE_API_BASE_URL=http://127.0.0.1:18200 npm run dev -- --host 127.0.0.1 --port 5175 --strictPort
```

然后从仓库根目录运行 Tabbit 命令。脚本先验证 `/test-fixture` 身份，避免误对真实后端操作。操作会创建新的测试章节；无需 API key。最后停止两个终端，并结束 Tabbit 任务。浏览器 smoke 尚未加入 GitHub CI（需要浏览器运行环境）；其余本地检查已接入 checks workflow。

## T01–T35 逐项核对

“通过”仅表示列出的工程场景有实际自动化/浏览器证据，不外推到真实供应商或所有并发组合。“部分”表示未达到任务书完整门槛。

| ID | 状态 | 证据与限制 |
| --- | --- | --- |
| T01 | 通过核心场景 | test_reliability_commands 同名创建独立章节且旧台词不变；手工时间线保留另由 T10 回归覆盖，未将两者组合成单一用例 |
| T02 | 部分 | 显式目标/版本/确认有测试，活动任务 guard 已实现；所有覆盖组合尚未独立验证 |
| T03 | 部分 | 修改失效异常回滚、项目文件/提交失败回滚已有测试；章节替换每个中断点未全部注入 |
| T04 | 通过 | 显式 null、未传不变、解绑、角色删除回滚 |
| T05 | 通过 | DTO 拒绝状态、路径、版本数组、章节归属字段 |
| T06 | 通过 | Agent 仅改备注触发与页面相同的 pending/时间线 stale |
| T07 | 通过已测场景 | 入队后改文本/项目上下文旧结果保留不选用；其他影响通过 builder 指纹覆盖，未逐个做真实调用 |
| T08 | 部分 | 重复完成/旧 token 条件及超时晚到已覆盖；取消和全部竞态组合未穷尽 |
| T09 | 通过主路径 | audio variants/selection、时间线选源测试和浏览器版本切换；来源关联由当前 API 保留 |
| T10 | 通过 | 原有 timeline_service/timeline_render_service 手工位置、时长、裁剪、淡入淡出、gain 回归保留 |
| T11 | 通过 | test_render_snapshot 在渲染期间修改片段，旧 manifest 被过期检查拒绝 |
| T12 | 通过 | 初审、返修失败、返修后复审失败各自从 checkpoint 恢复，不重复前序生成 |
| T13 | 部分 | 独立线程/文件 SQLite 并发入队只一次；陈旧 lease 不能二次抢占；真正并发确认/提交的全部组合未测试 |
| T14 | 通过主流程 | 重复确认先查幂等键、重复 commit、重复 Agent turn 复用结果 |
| T15 | 部分 | 恢复函数识别遗留任务且无模型调用；单实例锁测试；未做操作系统强杀矩阵 |
| T16 | 部分 | 入队抛异常可恢复；有界队列与跨线程确认已实现；队列满/loop 停止组合未全部注入 |
| T17 | 部分 | 畸形 item 后有效任务继续，单任务异常有外围保护；trace/通知故障每个位置未分别注入 |
| T18 | 通过假传输 | 真实 executor 线程在 timeout 后完成，独立文件不选用；不代表真实 provider SLA |
| T19 | 通过 | 第一工具成功第二失败显示部分成功；重复 turn 不重放第一动作 |
| T20 | 部分 | strict tool contracts、归属/模糊定位/只读保护已实现；对抗/混合自然语言意图矩阵未完成 |
| T21 | 通过原有回归 | scene_performance/workflow 定向返修与引用范围校验，未调用真实模型 |
| T22 | 部分 | speech_direction、engine capability、scene 测试和共用 builder；未穷尽所有供应商实际请求 |
| T23 | 通过 | 显式音色优先、旧 description 保留与无歧义回填，歧义拒绝 |
| T24 | 通过已测依赖 | 上下文/场景设计过期回归、项目输入指纹变化；场景失效采取保守策略 |
| T25 | 部分 | Node 可控 A→B/同章请求乱序/卸载 token 测试；主工作台已应用，完整子面板浏览器延迟注入未做 |
| T26 | 部分 | dirty merge 与 scope disposal 测试，页面卸载清理；未做所有资源泄漏长时运行测试 |
| T27 | 通过 | HTTP 错误和历史业务错误统一拒绝，空列表改为正常 200；浏览器实际读取通过 |
| T28 | 通过 | Demo 未知端点与生成端点 Node 回归；预生成声明和本地播放请求观察 |
| T29 | 通过原有+新增回归 | 部分渲染、过期选源和占位标记检查；历史无指纹音频明确未知 |
| T30 | 部分 | 新库与合成旧库副本迁移，源 hash/文件引用/文件内容/外键检查；真实历史库按用户要求未读取 |
| T31 | 部分 | health 身份/ready Node 测试与临时 FastAPI smoke；桌面实际进程复用未验证 |
| T32 | 部分 | 已有递归脱敏/凭据与 URL 测试，新增指纹不依赖凭据；所有旧异常响应未全面审计 |
| T33 | 部分 | Origin/token、素材格式和已选路径/大小/IPC 来源实现；打包 IPC/平台 symlink 全矩阵未测 |
| T34 | 通过应用闭环，下载落盘未核对 | scripts/browser_smoke.js 实测，WAV 返回、版本/素材/渲染/刷新通过；见上方下载限制 |
| T35 | 通过当前支持项 | sound_library_placement 实际改变音轨和 FFmpeg；未支持事件显示制作备注；未扩建自然语言声音解释器 |

## 迁移和兼容

Schema 9–11 均为增量变更；未重命名表、库或用户目录。副本迁移工具拒绝已存在的目的文件，通过 SQLite backup API 从只读源复制。合成旧库升级后源文件 SHA-256 不变，历史音频路径与字节不变，PRAGMA integrity_check/foreign_key_check 通过。

删除/替换前记录元数据历史，音频保留。新的输出文件按 attempt/variant/render 分配独立名字。旧直接写 status/path 的台词编辑、按标题覆盖，以及直接改 canonical 路径不再受支持；兼容映射见 [架构图](../../project-map.md)。

没有执行生产迁移。若之后部署代码，需先停止实际服务、做一致性备份并在副本验收；仅回退代码不能回退 schema。历史无指纹音频仍保留来源未知的兼容状态。

清理：本次临时后端、Vite 和 preview 已停止。批量关浏览器页被自动审批拒绝（担心误关用户未保存页面），未再关闭；finish 返回任务名不存在，未据此宣称标签页已清理。
