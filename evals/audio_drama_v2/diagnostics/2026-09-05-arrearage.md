# Arrearage 只读诊断证据

2026-09-05。此次只查询官方文档、读取本地已有配置，不发模型请求；不改免费模式、Key或计费设置。

## 已确认

- 调用记录保存的是HTTP400 / Arrearage。原始错误消息和Request ID当时未保存，不能补造。
- 用户已登录控制台的只读核查确认：两种许可模型仍有有效免费Token，且免费额度用完即停开启。不在此记录或公开材料写入数量、账户名、UID或密钥。
- 本地 `.local-data/app_test.db` 的provider 1使用 `https://dashscope.aliyuncs.com/compatible-mode/v1`。配置中有Key但不读取到输出；自定义参数只有response_format、temperature、top_p。评测代码直接使用此配置的Key/URL，无其他账号/地域fallback。
- 官方文档将该域名列为华北2（北京）`cn-beijing`，并说明Key、模型列表和接入点不能跨地域混用。[北京接入信息](https://help.aliyun.com/zh/model-studio/beijing-access-information)

## 官方错误区分

- `400-Arrearage`：官方定义为API Key所属阿里云账号的欠费拒绝。若该账号无欠费，应核对Key是否属于当前登录账号，仍异常则进一步排查账户状态。[错误码](https://help.aliyun.com/zh/model-studio/error-code#overdue-payment)
- `403-AllocationQuota.FreeTierOnly`：官方用于免费额度用完且启用了用完即停。本次保存的代码不是它。[错误码](https://help.aliyun.com/zh/model-studio/error-code)
- 免费Token、资源包等用于抵扣按量费用；账户欠费时，即使这些额度还有剩余也可能停止模型调用。因此“仍有免费Token”和“Arrearage”可以同时发生。[费用与成本说明](https://help.aliyun.com/zh/model-studio/bill-query-and-cost-management)

## 尚不能确认

本地数据库没有Key归属账号UID或创建地域元数据，无法证明当前Key属于当前登录控制台账号，也不能据现有材料认定哪个账号欠费。此前相同endpoint与Key曾成功返回27b输出，固定地域错配的可能性较低，但这仅是推断。

下一步仅需在已登录控制台只读核对：当前区域是否为北京；费用与成本页面的账户可用额度/欠费状态是否正常；Key归属是否与当前登录账号一致。如果都一致且正常，使用既有推理日志中的Request ID与时间向服务商排查账户/服务异常，不为补Request ID发新请求。免费Token页不等于账户计费状态页。

公开口径：控制台仍有免费额度，但API返回Arrearage，原因待诊断。没有依据称免费额度耗尽。
