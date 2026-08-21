# KB01-05 业务流程05 SessionManagement_Process

> **整合审核状态：approved。** 本文已完成人工核验（核验日期、核验人、来源证据见《00_来源核验台账.md》）。

## 文档登记信息（供人工管理）

> 本表供人工理解和核对；括号内中文是字段说明。在Dify中只创建括号前的英文字段名（如`record_id`），并按《00_统一元数据字典》设置。

| 元数据字段 | 当前文档分配值 |
|---|---|
| kb_code（知识库大类） | KB01（系统业务知识库） |
| doc_type（知识类型） | business_process（业务流程） |
| record_id（知识文档唯一编号） | AIZ-GEM-037 |
| dataset_version（数据集版本） | P2 |
| system（系统编码） | ZJQ_TRADE |
| module（主要模块） | TRADE_SESSION |
| source_type（来源类型） | mixed_simulated |
| status（审核状态） | approved |
| business_version（业务版本） | 不适用（Dify中留空） |

## 流程名称和目的
交易时段管理流程（Session Management Process）：精确控制模拟交易所的运行周期，包括开盘准备、连续竞价执行、收盘结算三个阶段的状态流转，并作为所有业务流程（订单匹配、价格生成）的时间锚点。

## 参与角色和模块
|角色/模块|职责|
|---|---|
|Session Scheduler|全局时钟服务：按HOSE时间表（09:15–11:30, 13:00–13:30）触发状态变更|
|System State Manager|维护当前Session状态（PRE_OPEN / TRADING / POST_CLOSE）<br>**冲突待核验：** 与 KB01-04 交易时段控制规则的 `OPEN/CLOSED` 两态枚举并存，待代码核验后统一|
|All Business Processes|监听状态事件（如TRADING_START）以激活自身逻辑|

## 前置条件
- 系统日期为周一至周五（非节假日）  
- HOSE交易日历已加载（原文p1：“các ngày từ thứ 2 đến thứ 6 (trừ ngày nghỉ lễ)”）  
- **关键约束**：本项目**仅模拟连续竞价时段，完全忽略ATO/ATC及午休**（原文p3：“chỉ giả lập một phiên khớp lệnh liên tục... không có ATO, ATC hay nghỉ trưa”）

## 正常流程
|步骤|操作方/模块|操作或请求|系统处理|输出/状态变化|
|---|---|---|---|---|
|1|Session Scheduler|到达09:15|发布TRADING_START事件|System State → TRADING|
|2|System State Manager|接收TRADING_START|初始化当日Reference Price（=前日Close）；清空Order Book；重置首/末笔成交标记|Session进入活跃交易态|
|3|Session Scheduler|到达11:30|发布TRADING_PAUSE事件|System State → PAUSED（但本项目无午休，故立即触发下一步）|
|4|Session Scheduler|到达13:00|发布TRADING_RESUME事件|System State → TRADING（继续）|
|5|Session Scheduler|到达13:30|发布TRADING_END事件|System State → POST_CLOSE；触发收盘价计算、Limit Order解挂、日终报表生成|Session终止|

## 异常分支
|分支|触发条件|处理方式|最终结果|
|---|---|---|---|
|A. 节假日误开|Scheduler检测到当日为法定假日（如越南国庆日）|跳过所有TRADING事件，State保持PRE_OPEN|系统静默，无订单接收|
|B. 时段配置错误|HOSE时间表被篡改（如13:30改为14:00）|Scheduler按错误时间触发，导致交易窗口偏移|所有依赖时间的流程（如收盘价）失效 → 必须熔断|
|C. 状态同步失败|System State Manager未收到TRADING_END事件|启动超时监控（13:35未收到则强制POST_CLOSE）|避免Order Book滞留未解挂|

## 流程结束条件
- TRADING_END事件成功发布且POST_CLOSE状态稳定  
- 所有当日Limit Order已完成解挂  
- 日终报表（含Open/Close/Reference/Ceiling/Floor）已生成  

## 上下游依赖
- 上游：HOSE交易日历（外部数据源）  
- 下游：OrderMatching_Process（依赖TRADING状态接收订单）、PriceFormation_Process（依赖TRADING_END计算Close）  

## 测试检查点
- ✅ 09:15必须精确触发TRADING_START（误差≤100ms）  
- ✅ 11:30与13:00之间无状态停留（即PAUSED态持续时间为0）  
- ✅ 13:30触发TRADING_END后，10秒内必须完成所有解挂操作  
- ✅ 节假日全天State必须为PRE_OPEN，且无任何订单处理日志  

## 参考来源与模拟声明
- 来源：`stockFundamentalTheory.md` p1（“thời gian giao dịch... 9:15 - 11:30 và 13:00 - 13:30”）、p3（“chỉ giả lập một phiên khớp lệnh liên tục... không có ATO, ATC hay nghỉ trưa”）  
- 模拟声明：**本流程是所有时间敏感型业务的总开关，其正确性是系统可信度基石**
