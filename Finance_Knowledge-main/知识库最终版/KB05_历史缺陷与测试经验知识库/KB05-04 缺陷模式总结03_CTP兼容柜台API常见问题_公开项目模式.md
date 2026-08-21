# KB05-04 缺陷模式总结03 CTP兼容柜台API常见问题（公开项目模式）

> **整合审核状态：approved。** 本文已完成人工核验（核验日期、核验人、来源证据见《00_来源核验台账.md》）。

## 文档登记信息（供人工管理）

| 元数据字段 | 当前文档分配值 |
|---|---|
| kb_code（知识库大类） | KB05（历史缺陷与测试经验知识库） |
| doc_type（知识类型） | defect_pattern_summary（缺陷模式与经验总结） |
| record_id（知识文档唯一编号） | AEF-GEM-004 |
| dataset_version（数据集版本） | P2 |
| system（系统编码） | ZJQ_TRADE |
| module（主要模块） | TRADE_SESSION |
| source_type（来源类型） | mixed_simulated |
| status（审核状态） | approved |
| business_version（业务版本） | 不适用（Dify中留空） |

## 缺陷模式摘要

| 模式 | 现象 | 共性根因 | 防漏测建议 |
|---|---|---|---|
| 连接/登录失败 | 客户端无法建立会话或登录被拒 | 地址、证书、会话参数配置不一致 | 覆盖主备通道、配置错误、网络中断 |
| 接口超时 | 请求无响应或超时 | 未设置调用超时、无重试策略 | 覆盖超时阈值、部分成功、重试 |
| 断线重连 | 重连后状态不同步或重复提交 | 无幂等标识、未重发未确认消息 | 覆盖重连、消息确认、幂等键 |
| 参数异常 | 字段为空、越界或格式错误 | 入参校验不完整 | 覆盖空值、边界值、非法格式 |

## 来源

- 项目：openctp-master（CTP 兼容柜台 API 生态），来源链接：https://github.com/openctp/openctp
- 主要参考：docs/综合交易平台API开发常见问题列表.pdf、readme.md
- 许可证：BSD-3-Clause；commit/永久链接待核验补充。