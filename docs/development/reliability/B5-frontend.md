# B5 前端作用域、草稿与 Demo

问题 ID：UI-01、UI-02、UI-03、TEST-01；T25–T28、T34。

改动：useProductionData 拥有读取/轮询/dirty 草稿，requestScope 管理章节与查询代次；ProjectWorkspace 历史与会话加载防止迟到回写；生产动作有独立上下文检查，卸载清理播放器/定时器。SelectedTakeInfo 展示来源文本/指导与适用性；历史音频可播放但不计为当前完成。transport 统一 HTTP/旧业务错误，默认 30 秒，FFmpeg render 单独上限。未知 mock 和 Demo 实时生成明确失败。

红灯：缺少请求作用域 helper 时前端新增集合失败；实现后前端 27 项通过，后加操作 scope/health/Demo 边界至最终 31 项通过。Demo 批量生成测试先失败（旧 handler 返回 created=0），随后改为明确不支持。

命令：`npm test --prefix sonicvale-front`；两种 build；`tabbit-cli nodejs --task auralis-reliability --request-id final-full-browser --timeout-ms 120000 < scripts/browser_smoke.js`。

浏览器：使用临时 fake 后端，脚本 9.557 秒通过：固定原文、确认人物/台本、两句配音、第二 take、切回旧 take、素材加入、真实 WAV、刷新恢复；页面异常列表为空。静态 Demo 试听只读取预置音频，预生成声明可见，截图布局检查通过。

兼容/剩余：ProjectWorkspace 的确认/发送状态仍在页面内；历史 ChatProductionPanel 等文件未全量重构。A→B/dirty 生命周期有确定性 Node 回归，尚未将全部子面板纳入浏览器乱序注入测试。浏览器 WAV 接口 200 audio/wav；自动化 download 事件超时，未据此声称用户下载目录落盘已核对。

本批全部模型调用使用固定 fake/mock；音频处理使用临时文件与真实本机 FFmpeg。未调用真实 LLM/TTS，未读取或迁移用户生产库，未推送/部署。最终汇总见 [验收结果](verification.md)。
