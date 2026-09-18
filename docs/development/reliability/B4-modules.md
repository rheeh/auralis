# B4 职责提取与依赖

问题 ID：ARCH-01、ARCH-02、ARCH-03、CFG-01。

提取生产命令、章节生命周期、状态判断、纯声音路由、配音请求 builder、普通数据 provider adapter、FFmpeg transforms、队列确认和启动恢复。routers/main 的常用构造统一到 services/factory。保留已有类路径和框架，没有全量搬目录。

红灯：`test_architecture_boundaries` 原先 3 项中 main 从 router 导入服务构造的 1 项失败；修正后通过。提取阶段一次全量运行曾因 import/声明顺序导致 test_project_deletion 无法导入，已修正，未忽略该模块。最终 3 项依赖约束与完整 suite 全过。

命令：`SonicVale/.venv/bin/python scripts/test_backend.py test_architecture_boundaries`；`./scripts/verify.sh`。

兼容：LineService 保留旧方法门面，worker 正式生产不再向线程传 ORM service。没有更换框架/表名/默认保存目录。

剩余：LineService 的同步旧供应商调用方法、main 默认数据初始化、助手主循环和若干旧导入服务仍较集中，未声称全部拆分完成。权威业务边界优先于目录整齐。

本批全部模型调用使用固定 fake/mock；音频处理使用临时文件与真实本机 FFmpeg。未调用真实 LLM/TTS，未读取或迁移用户生产库，未推送/部署。最终汇总见 [验收结果](verification.md)。
