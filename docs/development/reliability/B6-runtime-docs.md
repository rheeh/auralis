# B6 配置、迁移、安全与交付资料

问题 ID：CFG-01、CFG-02、SEC-01、TEST-01、EVAL-01；T22–T23、T30–T35。

改动：schema 9–11（请求指纹/token、显式音色字段、活动 attempt 唯一索引）；provider_voice_id 优先，无歧义兼容旧 description；只读源数据库副本迁移脚本。健康身份/实际 schema/worker/FFmpeg；统一桌面运行时 API；恢复 Electron sandbox/webSecurity、限制导航、校验 IPC 来源/目标和数据大小；HTTP/WS Origin 与实例 token。锁定宽版本依赖，独立测试依赖；checks CI 与手动 Pages 的同 SHA 检查前置。补当前架构/产品/约束/任务状态，历史资料加说明。

红灯：音色字段/兼容迁移初始 2 项均 error，新增字段和规则后通过；健康身份 Node 测试先缺模块失败，之后通过。合成旧库复制迁移、源 hash 不变、音频路径/内容保留、外键校验通过；Origin/token 测试通过。全量结果见 verification.md。

复现：`SonicVale/.venv/bin/python scripts/test_backend.py test_runtime_configuration test_migration_copy test_local_boundary`；`./scripts/verify.sh`。副本工具：`SonicVale/.venv/bin/python scripts/migrate_copy.py /path/source.sqlite3 /path/new-copy.sqlite3`，本轮只对临时合成库执行。

本机：Python 3.12.13、Node 22.23.2、FFmpeg 8.1.2、SQLAlchemy 2.0.44、DashScope 1.26.3、edge-tts 7.2.8、httpx 0.28.1。没有升级主框架。

未验证：真实用户库、真实 LLM/TTS、听感/业务效果、打包 Electron/macOS/Windows 运行与同端口后端复用、远程 CI/Pages。构建有原有 >500 kB chunk warning。历史声音说明中未执行 audioEvents 的 UI 标记与能力表已补；不把自然语言备注当成已渲染效果。

本批全部模型调用使用固定 fake/mock；音频处理使用临时文件与真实本机 FFmpeg。未调用真实 LLM/TTS，未读取或迁移用户生产库，未推送/部署。最终汇总见 [验收结果](verification.md)。
