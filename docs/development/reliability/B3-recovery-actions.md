# B3 恢复、lease 与助手动作

问题 ID：FLOW-01、FLOW-02、TASK-01、TASK-02、AGENT-01。

改动：初审/返修/复审 checkpoint；条件 lease 与返回时 token 检查；同幂等键先于阶段校验；配置目录单实例锁；启动遗留任务显式中断；有限队列确认入队。Agent 工具严格 schema、每工具已完成结果/pending 标记、部分成功回复、显式只读要求保护。事件序号改为 SQL 原子增长；阶段/事件同事务，网络通知在提交后。

红灯：workflow recovery 初始 3 项中 1 failure、2 error；实施后 3 项通过。runtime recovery 的部分成功测试先 failure，修复后 3 项通过。后补返修/复审恢复测试通过，两个独立 Session 的陈旧事件计数测试先失败，原子序号后通过。并发入队测试使用文件 SQLite、独立 Session/线程，确认只有一个活动任务和一次入队。

命令：`SonicVale/.venv/bin/python scripts/test_backend.py test_workflow_recovery test_runtime_recovery test_worker_boundaries test_generation_consistency`。最终随完整入口全过。错误注入测试有预期异常日志，不能只看日志 ERROR 判断 suite 失败。

兼容：恢复不自动发请求。Agent 保存了 pending 但未确认结果的工具按不确定状态返回，不自动重放。旧任务 summary 仍保留 counts/tasks，并分离执行进度。

剩余：进程级强杀/重启、确认与提交的真正同时竞争，尚未覆盖全部组合；部分历史事件发布点仍在业务提交之后单独持久化。

本批全部模型调用使用固定 fake/mock；音频处理使用临时文件与真实本机 FFmpeg。未调用真实 LLM/TTS，未读取或迁移用户生产库，未推送/部署。最终汇总见 [验收结果](verification.md)。
