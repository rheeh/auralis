# B1 数据保护与权威写入

问题 ID：DATA-01、DATA-02、API-01、CONS-01、ARCH-03、UI 错误语义（T27）。

改动：LineUpdateDTO/LinePublicCreateDTO 白名单；显式 null；LineCommands 统一页面/Agent 编辑、排序和角色解除绑定，角色删除也与解绑一起提交。版本/素材写入加入同一失效事务。同名创建独立章节；已有目标要求 ID、期望版本、确认。legacy commit_run 转同一个 DramaCommitService。章节/项目/单句删除保留历史元数据和文件，并拒绝活动任务。

红灯：`scripts/test_backend.py test_reliability_commands` 初始 6 项中 5 failure、1 error，覆盖同名、显式覆盖、null、Agent 备注、DTO、事务回滚。实施后同一集合 6 项全过。后补角色删除回滚测试先失败，归并事务后 7 项全过。

兼容性：旧 UI 写 status/path/chapter_id 现在会被拒绝；仓库内调用方已调整。路径重命名入口明确返回冲突；转向选用版本/素材导入。删除项目后保留 `.archived-*` 文件夹及 project_history 快照，不再物理清理。

剩余：旧批量导入/仓储兼容调用尚未逐一改成无自行 commit 模式；没有自动恢复归档的产品 UI。覆盖 API 已有显式安全条件，当前主工作台的新建流程不提供覆盖按钮。

本批全部模型调用使用固定 fake/mock；音频处理使用临时文件与真实本机 FFmpeg。未调用真实 LLM/TTS，未读取或迁移用户生产库，未推送/部署。最终汇总见 [验收结果](verification.md)。
