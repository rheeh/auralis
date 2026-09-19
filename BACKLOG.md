# 架构整理与可靠性状态

更新于 2026-09-19；首轮基于 master@5aed5b8，后续在 5a44ee7 上完成 R1–R6 定向修复。已落地核心修复，但**不是所有 B0–B6 门槛都已完成验收**。此文件是唯一实时状态表；[原任务书](docs/development/reliability/Auralis_Implementation_Brief.md)仅为实施规格。

## 本轮 R1–R6

均已复现并完成针对性修复，详见 [触发场景、调用链、测试和限制](docs/development/reliability/followup-5a44ee7.md)。

- R1：新指导重生成原子拒绝活动任务，409 不落库；前端保留输入。
- R2：Agent turn 数据库调度/执行领取、步骤键、中断保留、失效 token 拒绝晚到工具。
- R3：人物草稿唯一所有者与 revision 冲突选择；保存快照；视图间保留、章节离开保护。
- R4：created 重启后可显式继续；角色生成重试复用解析。
- R5：超时/晚到/中断 trace 与任务一致，执行槽位可观测；CosyVoice 完成等待上界。
- R6：实际文件与来源统一解析，标签、时间线、导出一致。

R7 轮询失败恢复及请求量测量、R8 依赖漏洞分类/可达性核查保留为后续，未自动升级依赖。

## 首轮问题登记

| ID | 状态 | 事实与记录 |
| --- | --- | --- |
| ARCH-01 | 部分完成 | 命令、请求、生产 adapter、音频处理已提取；同步旧方法仍需缩减。[B4](docs/development/reliability/B4-modules.md) |
| ARCH-02 | 已实施/局部边界保留 | 常用构造统一 factory，main/runtime 不依赖 router 构造；不是通用容器。[B4](docs/development/reliability/B4-modules.md) |
| ARCH-03 | 热路径完成，旧路径待审计 | 修改/解绑/版本/类型/任务完成有短事务；旧导入与仓储默认 commit 保留。[B1](docs/development/reliability/B1-data-protection.md) |
| DATA-01 | 已解决 | null、未传、解绑有回归。[B1](docs/development/reliability/B1-data-protection.md) |
| API-01 | 已解决公共创建/更新边界 | 内部兼容 LineCreateDTO 尚未完全替名。[B1](docs/development/reliability/B1-data-protection.md) |
| CONS-01 | 已解决 | 页面/助手修改共享命令与失效。[B1](docs/development/reliability/B1-data-protection.md) |
| CONS-02 | 已解决新生成主路径 | 快照/完整指纹/token/唯一输出/条件完成。[B2](docs/development/reliability/B2-generation-consistency.md) |
| CONS-03 | 已实施，历史来源未知 | 当前性/可播放/选用分开；历史无指纹保留兼容。[B2](docs/development/reliability/B2-generation-consistency.md) |
| FLOW-01 | 已解决 | 初审/返修/复审失败分别恢复。[B3](docs/development/reliability/B3-recovery-actions.md) |
| FLOW-02 | 已实施，竞争覆盖非穷尽 | 条件 lease、token、幂等、原子事件序号。[B3](docs/development/reliability/B3-recovery-actions.md) |
| DATA-02 | 已解决隐式覆盖 | 无目标新建独立章节；覆盖需 ID/版本/确认，旧提交共用实现。[B1](docs/development/reliability/B1-data-protection.md) |
| TASK-01 | 已实施/函数级验收 | 启动恢复与单实例锁；未做所有阶段进程强杀矩阵。[B3](docs/development/reliability/B3-recovery-actions.md) |
| TASK-02 | 已实施/假传输验收 | Session 不跨线程、晚到隔离、槽位保留。[B2](docs/development/reliability/B2-generation-consistency.md) |
| AGENT-01 | 已解决部分成功重试，尚需扩展矩阵 | 工具结果/pending 持久化、schema、只读意图保护；需更完整并发/模糊指令测试。[B3](docs/development/reliability/B3-recovery-actions.md) |
| UI-01 | 部分完成 | 请求/生产数据提取，确认/发送调度仍在页面。[B5](docs/development/reliability/B5-frontend.md) |
| UI-02 | 主工作台已解决/部分验收 | session/history/生产读取有 scope；全子面板乱序浏览器测试未做。[B5](docs/development/reliability/B5-frontend.md) |
| UI-03 | 部分完成 | 数据/草稿与来源显示已提取；播放器/版本动作仍集中。[B5](docs/development/reliability/B5-frontend.md) |
| CFG-01 | 已实施/工程测试 | 共享 routing、builder、显式音色迁移；真实 provider 未测试。[B6](docs/development/reliability/B6-runtime-docs.md) |
| CFG-02 | 已实施/浏览器验收 | Runtime API、健康身份与 worker/FFmpeg；桌面实际复用未验收。[B6](docs/development/reliability/B6-runtime-docs.md) |
| SEC-01 | 实现并局部验收 | Origin/token 与 Electron 安全开关/IPC；打包端尚未实测。[B6](docs/development/reliability/B6-runtime-docs.md) |
| TEST-01 | 本地完成 | 准确发现测试、隔离入口、离线 CI、Pages 检查前置；5a44ee7 的远程 checks 已核实通过，见本轮记录。[验收](docs/development/reliability/verification.md) |
| EVAL-01 | 边界完成 | 原报告保留，未新增真实调用或听感分数，不以旧报告证明新策略。 |

## 必须保留的未完成清单

1. 完成旧导入/兼容仓储调用的写入与事务审计；缩减 LineService 同步供应商门面和 main 初始化职责。不能把 hot path 修复等同于所有历史代码都符合目标依赖方向。
2. 将 ProjectWorkspace 确认/发送调度及 ProductionScriptPanel 播放/版本交互进一步形成生命周期明确的独立用例；为所有子面板补真实 A→B 乱序和卸载测试。
3. 扩展进程强杀/重启、并发确认/提交、事件落库失败及 trace 异常等故障矩阵；将剩余历史“业务提交后另记事件”路径逐步合并。
4. 补只读孤儿产物检查工具与归档恢复流程。当前失败 attempt 的独立文件、task 路径、删除快照和历史音频都保留，不自动清理。
5. 实测打包 Electron 的安全模式、媒体/IPC、同端口实例 token 复用及 Windows 锁；当前不能声称桌面分发已验收。
6. 真实历史数据库与真实供应商/听感验证未执行，受本次“不触碰真实库/不调用模型”边界限制；5a44ee7 的远程 CI 已通过；Pages 未重新发布。它们不是本地假模型测试可替代的证据。

## 交付资料

[实际模块图与调用链](docs/project-map.md) · [验证结果及 T01–T35 覆盖](docs/development/reliability/verification.md)

批次：[B0](docs/development/reliability/B0-baseline.md) → [B1](docs/development/reliability/B1-data-protection.md) → [B2](docs/development/reliability/B2-generation-consistency.md) → [B3](docs/development/reliability/B3-recovery-actions.md) → [B4](docs/development/reliability/B4-modules.md) → [B5](docs/development/reliability/B5-frontend.md) → [B6](docs/development/reliability/B6-runtime-docs.md)
