# Auralis 开发约定

先读 README.md（产品/运行入口）、PROJECT.md（范围）、docs/project-map.md（当前架构）和 BACKLOG.md（待验收项）。历史交接与 LangGraph 方案不是当前执行指令。

- 保留 Vue 3、FastAPI、SQLAlchemy、SQLite、FFmpeg；先统一规则，再按职责提取，不扩建商业系统。
- 修改前检查分支、HEAD、git status。保护用户未提交/未跟踪内容；不执行破坏性 git 操作。
- 用户已授权：此类大修改完成必要验证后，主动提交本次相关文件并推送到已确认的 GitHub 远端（当前为 github：rheeh/auralis）。暂存前检查未跟踪文件，排除无关内容、用户数据与密钥；推送后核对远端提交。用户当次另有限制时以当次要求为准。部署、发布仍需另行明确授权。
- 新热路径由业务命令拥有短事务。HTTP、Agent、兼容 API、脚本复用 services/factory.py 与权威命令；runtime 不依赖 routers，integrations 不读取 ORM。
- 不把 Session/仓储/service 传入供应商执行线程；线程只接收普通请求数据。状态持久化与执行 attempt 分开，晚到结果不可覆盖当前输入。
- 不按同名标题覆盖章节。覆盖需目标 ID、期望版本、明确确认和活动任务检查。保留旧 take、手工时间线、源文件和归档。
- 测试入口：`./scripts/verify.sh`。后端独立入口：`SonicVale/.venv/bin/python scripts/test_backend.py`；前端：`npm test --prefix sonicvale-front`。
- 上述测试使用临时配置/SQLite/音频，默认禁止网络连接。不得对真实 `.local-data`、用户小说、音频或密钥运行测试、迁移、生成脚本。
- 不调用真实 LLM/TTS 或付费评测；当前模型允许策略仍适用，另行授权也不能自动换模型。假模型工程验证不是听感/语义质量证据。
- 副本迁移使用 `scripts/migrate_copy.py SOURCE NEW_DESTINATION`；源以 SQLite 只读备份方式打开。不得将 git revert 当作 schema 回滚。
- 每批先写能揭示问题的测试，再实现、验证。事实与未验证内容写入开发记录；README 保持产品入口，不堆测试日志。
