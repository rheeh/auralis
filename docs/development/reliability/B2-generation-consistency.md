# B2 配音、版本与渲染一致性

问题 ID：CONS-02、CONS-03、TASK-02、CFG-01；T07–T11、T18、T24、T29。

改动：speech/request 冻结完整有效输入与脱敏指纹；唯一 attempt 文件；条件 claim/complete；旧输入只留历史 take。generation_state 分开文件/适用性/选择；生产进度与执行历史分离。TimelineRenderService 冻结数据并产生唯一 WAV/manifest，期间编辑不使旧渲染变新。LineService 旧 process_audio 改为独立版本创建。

红灯与结果：

- 初始生成一致性集合 4 个新场景失败（当时继承 fixture 还重复发现 12 个基线用例；已修正发现方式，不计为新增覆盖）。
- `test_render_snapshot` 先 1 failure，冻结后通过。
- 后补长输入指纹、素材保留历史、版本切换回滚三个测试先全部失败；修复后与恢复测试合计 12 项通过。
- `test_worker_boundaries` 先 malformed item 导致超时，修复后 2 项通过，含原生线程晚到隔离。
- 生产进度测试先 failure，随后按 generation_state 计算通过。
- 旧 process_audio 的源文件 SHA-256 不变测试先 failure，改为后期版本后通过。原有测试/烟测中“删除版本会删文件”和“原地改路径”的旧断言按用户保留历史要求改为更严格的源文件保留与选中独立 WAV 检查，未删除用例。

命令：`SonicVale/.venv/bin/python scripts/test_backend.py test_generation_consistency test_render_snapshot test_worker_boundaries`；最终随完整 verify.sh 全过。

兼容：新状态 stale、completing；输出路径与混音名改为唯一名，读取走 API/manifest。历史无指纹 take 保留兼容，显示输入来源未知。

剩余：未提供自动孤儿文件清理/恢复 UI；超时线程不能强杀，槽位要等待底层请求退出。没有真实供应商晚到/断网试验。

本批全部模型调用使用固定 fake/mock；音频处理使用临时文件与真实本机 FFmpeg。未调用真实 LLM/TTS，未读取或迁移用户生产库，未推送/部署。最终汇总见 [验收结果](verification.md)。
