# KB01-05 业务流程04 PriceFormation_Process

> **整合审核状态：approved。** 本文已完成人工核验（核验日期、核验人、来源证据见《00_来源核验台账.md》）。

## 文档登记信息（供人工管理）

> 本表供人工理解和核对；括号内中文是字段说明。在Dify中只创建括号前的英文字段名（如`record_id`），并按《00_统一元数据字典》设置。

| 元数据字段 | 当前文档分配值 |
|---|---|
| kb_code（知识库大类） | KB01（系统业务知识库） |
| doc_type（知识类型） | business_process（业务流程） |
| record_id（知识文档唯一编号） | AIZ-GEM-036 |
| dataset_version（数据集版本） | P2 |
| system（系统编码） | ZJQ_TRADE |
| module（主要模块） | MARKET_DATA |
| source_type（来源类型） | mixed_simulated |
| status（审核状态） | approved |
| business_version（业务版本） | 不适用（Dify中留空） |

## 流程名称和目的
价格生成流程（Price Formation Process）：依据HOSE规则及本项目简化约定，动态计算并维护股票的开盘价（Open）、收盘价（Close）、参考价（Reference）、涨停价（Ceiling）、跌停价（Floor）五类关键价格，为订单匹配提供价格约束。

## 参与角色和模块
|角色/模块|职责|
|---|---|
|Market Data Service|定时读取前一日收盘价；维护当日首/末笔成交记录|
|Pricing Engine|核心计算模块：执行各价格的公式运算与状态更新|
|Order Validation Module|在订单接收时，校验limit price是否 ∈ [Floor, Ceiling]|

## 前置条件
- 系统已加载证券基础信息（含股票代码、前一日Close Price）  
- 连续竞价时段已开始（开盘价计算启动）或已结束（收盘价计算启动）  
- **关键约束**：所有价格计算均基于HOSE规则，且涨跌幅统一设为7%（原文p2：“tính giá trần và giá sàn theo biên độ cố định 7%”）

## 正常流程
|步骤|操作方/模块|操作或请求|系统处理|输出/状态变化|
|---|---|---|---|---|
|1|Market Data Service|检测到首笔成交发生|触发Open Price计算|—|
|2|Pricing Engine|计算开盘价|Open Price = 首笔成交的price（原文p3：“Giá mở cửa = giá của lệnh đầu tiên được khớp”）|Open Price字段更新|
|3|Market Data Service|检测到末笔成交发生|触发Close Price计算|—|
|4|Pricing Engine|计算收盘价|Close Price = 末笔成交的price（原文p3：“Giá đóng cửa = giá của lệnh cuối cùng được khớp”）|Close Price字段更新|
|5|Pricing Engine|每日开盘前|Reference Price = 前一日Close Price（原文p2：“Giá tham chiếu... là giá đóng cửa đã khớp lệnh trong ngày giao dịch liền trước”）|Reference Price字段初始化|
|6|Pricing Engine|每次Reference Price更新后|Ceiling = Reference Price × (1 + 7%)<br>Floor = Reference Price × (1 - 7%)（原文p2：“tính giá trần và giá sàn theo biên độ cố định 7%”）|Ceiling/Floor字段更新|

## 异常分支
|分支|触发条件|处理方式|最终结果|
|---|---|---|---|
|A. 首笔成交缺失|当日无任何成交（p3：“nếu trong ngày đó không có giao dịch nào được khớp thì giá mở cửa giữ nguyên từ ngày giao dịch trước”）|Open Price = 前一日Close Price|Open Price与Close Price相同|
|B. 末笔成交缺失|当日无任何成交（p3：“nếu trong ngày đó không có giao dịch nào được khớp thì giá đóng cửa giữ nguyên từ ngày giao dịch trước”）|Close Price = 前一日Close Price|Close Price维持不变|
|C. Reference Price异常|前一日Close Price为空（如新股首日）|采用特殊规则（原文p2提及“trừ những trường hợp đặc biệt”，但本项目未实现，故视为不可达状态）|系统报错，阻止开盘|

## 流程结束条件
- Open/Close Price在首/末笔成交后即时确定  
- Reference Price在每个交易日开盘前1次初始化  
- Ceiling/Floor在Reference Price变更后即时重算  

## 上下游依赖
- 上游：OrderMatching_Process（提供首/末笔成交事件）  
- 下游：Order Validation Module（校验limit price）、Bidding Board（显示价格带）  

## 测试检查点
- ✅ 新股首日：Reference Price需按特殊规则（本文未定义，应标记为TODO）  
- ✅ 涨停价必须 = Reference × 1.07（四舍五入至最小变动单位）  
- ✅ 当日无成交时，Open/Close Price必须严格等于前一日Close Price  
- ✅ Reference Price变更后，Ceiling/Floor必须在100ms内同步更新  

## 参考来源与模拟声明
- 来源：`stockFundamentalTheory.md` p2–p3（“Giá trần, giá sàn”, “Giá tham chiếu”, “Giá mở cửa/Giá đóng cửa”）  
- 模拟声明：**放弃HNX/UpCOM规则，统一采用HOSE Reference Price定义 + 固定7%涨跌幅**；**不处理分红送转等特殊调整情形**
