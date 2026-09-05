# 悬疑 / 都市广播剧提示词实验 v2

这是实际调用已配置阿里云 Qwen 模型的小样本提示词实验。评测对象是写稿阶段，不是整个解析、确认角色、独立审查和返修工作流，也不代表真实听众试听。用户澄清后仅允许 `qwen3.8-27b` / `kimi-k3`；脚本默认并严格请求 `qwen3.8-27b`，其他型号被本地拒绝，禁止自动降级。历史 `qwen-plus` 数据保留并明确标注，不再调用。

## 设计

- 同一模型、相同采样参数、相同原文、确认角色和 JSON Schema，比较现行声音优先规则 A、事实约束与导演分轨 B、在 B 上增加局部示例 C。
- 三个素材均为原创虚构文本：都市关系《末班车前的旧伞》、空间反转《冷库里的第三扇门》、本次 Demo《雨夜来件》。前两个来自 v1 的 CC0 原创合成数据；Demo 由本次任务新写。
- 每个样本和策略一次生成，随机顺序，最多两请求并发。生成前不向模型泄漏评分表、required_facts 或 prohibited_inventions。
- 另外单独调用同一模型盲评，不告知策略名称。保存未经修改的评语和分数；它是辅助信号，不能代替逐句事实核对。
- 在 Pydantic 修复前计算原始结构指标，再记录修复后指标。括号被程序移走不算提示词成功。没有对失败结构进行自动返修。
- provider 凭据仅从本地 SQLite 只读连接进入内存。记录中没有 API key、用户配置或认证请求头；错误仅保存异常类型及 HTTP 状态码。

## 重现

在项目根目录运行：

```bash
SonicVale/.venv/bin/python evals/audio_drama_v2/run_evaluation.py \
  --model qwen3.8-27b --workers 2 --skip-judge \
  --output evals/audio_drama_v2/runs/new-run
SonicVale/.venv/bin/python -m unittest discover -s evals/audio_drama_v2 -p 'test_*.py'
```

`--config-dir` 默认 `.local-data`，`--provider-id` 默认 1。真实调用会按服务商计费。需要本地已配置且可访问的官方兼容 API。

`--skip-judge` 只保留写稿输出与客观指标，不再发模型自评请求；新一轮按此方式运行。单次写稿最多5000输出tokens。可用 `probe_model.py --model qwen3.8-27b` 做一次16-token上限的小探测；失败只报错，不换模型。

每次运行保留 `run_config.json`、完整数据快照、完整系统提示词、每次原始响应、token 使用量、schema 验证结果、盲评、结构指标和分数 CSV。已完成的相同配置记录可续跑；相同输出目录不允许更换样本或提示词。

## 判读边界

旁白比例低、结构合法、音效多，均不能推出故事忠实或对白自然。必须核对每个关键事实是否真正出现在可朗读台词或可实现的声音里；角色表、场景标题、导演备注和评审自己补全的情节不算听众收到的信息。保留原文未解身份，不为提升戏剧性增加答案。实验结论与逐项复核另见 `REPORT.md`。
