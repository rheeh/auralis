# B0 基线与隔离

核对：master，HEAD `5aed5b8391d848e7e7e1191c551caa882d5de82f`，与任务书一致。最初不存在仓库 AGENTS.md；阅读了 README、AI-HANDOFF 和相关开发说明，用户本次禁止推送等规则优先于历史交接。

原有未跟踪内容保持原位：docs/ai-pm-product-research-report.html、docs/assets/、evals/audio_drama_v1 的 README/dataset/rubric/scorecard/validate_dataset、personal-site/、reports/。没有暂存、提交或清理这些内容。

问题 ID：TEST-01、EVAL-01。加入 scripts/test_backend.py、scripts/offline/sitecustomize.py；verify.sh 使用临时配置并将 API smoke 拆到独立脚本。前端统一递归发现 src 与 tests 内的既有测试。

基线实测：后端 `unittest discover -s tests -p 'test_*.py'` 在隔离目录中 165 项通过（6.082s）；前端原测试集合 23 项通过。新入口的复现命令是 `SonicVale/.venv/bin/python scripts/test_backend.py` 和 `npm test --prefix sonicvale-front`。

基线已有、没有重造的能力：schema 1–8 的增量迁移、selected_audio_path 选音规则、手工时间线保留/裁剪边界、局部返修范围校验、场景表演引用检查、trace 基础脱敏、静态 Demo 预生成声明。后续只补对应边界。旧评测报告保留，未作为新功能质量证据。

兼容：总入口 verify.sh 保留；它验证完退出，不承担启动。未验证：远程 CI、真实模型与真实历史库。

本批全部模型调用使用固定 fake/mock；音频处理使用临时文件与真实本机 FFmpeg。未调用真实 LLM/TTS，未读取或迁移用户生产库，未推送/部署。最终汇总见 [验收结果](verification.md)。
