# KB01-05 业务流程02 OrderMatching_Process

> **整合审核状态：approved。** 本文已完成人工核验（核验日期、核验人、来源证据见《00_来源核验台账.md》）。

## 文档登记信息（供人工管理）

> 本表供人工理解和核对；括号内中文是字段说明。在Dify中只创建括号前的英文字段名（如`record_id`），并按《00_统一元数据字典》设置。

| 元数据字段 | 当前文档分配值 |
|---|---|
| kb_code（知识库大类） | KB01（系统业务知识库） |
| doc_type（知识类型） | business_process（业务流程） |
| record_id（知识文档唯一编号） | AIZ-GEM-034 |
| dataset_version（数据集版本） | P2 |
| system（系统编码） | ZJQ_TRADE |
| module（主要模块） | MATCHING |
| source_type（来源类型） | mixed_simulated |
| status（审核状态） | approved |
| business_version（业务版本） | 不适用（Dify中留空） |

## 流程名称和目的
订单匹配流程（Order Matching Process）：接收用户提交的买卖订单，依据价格-时间优先原则，在订单簿（Order Book）中寻找对手方，执行成交、更新订单簿状态，并生成交易记录。

## 参与角色和模块
|角色/模块|职责|
|---|---|
|用户（Investor）|提交 Market Order 或 Limit Order（含股票代码、方向、价格、数量）|
|前端系统（Frontend）|校验订单格式，转发至后端|
|Matching Engine|核心处理模块：解析订单、检索Book、执行匹配逻辑、更新状态、生成Transaction|
|Order Book（Per Stock）|内存数据结构：维护当前股票所有未成交Limit Order（Bid/Ask双向队列）|
|Transaction Log|持久化模块：记录每笔成交的price, quantity, timestamp, order IDs|

## 前置条件
- 系统处于HOSE连续竞价时段（09:15–11:30, 13:00–13:30），且非节假日  
- 目标股票代码（Stock Symbol）已存在于系统证券池中  
- 用户账户资金/持仓满足订单预冻结要求（隐含于“资金返还”异常分支）  
- **关键约束**：本项目不模拟ATO/ATC，故开盘价/收盘价由首/末笔成交决定（见KB03）

## 正常流程
|步骤|操作方/模块|操作或请求|系统处理|输出/状态变化|
|---|---|---|---|---|
|1|用户|提交Market Buy Order（无指定价格）或Limit Buy/Sell Order（含price）|前端校验格式后，发送至Matching Engine|订单进入处理队列|
|2|Matching Engine|解析订单类型与参数|若为Market Order：<br>• Buy：按Ask队列价格升序（最低卖价优先），取最早时间者匹配<br>• Sell：按Bid队列价格降序（最高买价优先），取最早时间者匹配<br>若为Limit Order：<br>• Buy：检查Ask队列中是否存在price ≤ order.price的订单；<br>• Sell：检查Bid队列中是否存在price ≥ order.price的订单|匹配判定完成|
|3|Matching Engine|执行匹配|对满足条件的对手方订单，按min(本方quantity, 对手quantity)成交：<br>• 更新双方订单剩余量（若部分成交）<br>• 若对手方订单完全成交，则从Book中移除<br>• 生成Transaction记录（含price, quantity, timestamp）|订单簿状态变更；Transaction Log新增条目|
|4|Matching Engine|更新Order Book|将新Market Order直接匹配成交（不入Book）；<br>将未匹配的Limit Order按price-time插入对应Bid/Ask队列（Buy→Bid, Sell→Ask）|Book Order结构更新（仅显示Top2 Bid/Ask，但全量维护）|
|5|Matching Engine|返回结果|向用户返回成交确认（含price, quantity）或部分成交/未成交状态|用户端显示实时成交反馈|

## 异常分支
|分支|触发条件|处理方式|最终结果|
|---|---|---|---|
|A. 无对手方（No Counterparty）|Limit Order提交时，Book中无满足价格条件的对手单；且至收盘仍未出现|Matching Engine在收盘时自动解挂该订单|订单失效；冻结资金/股份释放回用户账户|
|B. 首笔成交缺失（No Opening Trade）|当日连续竞价时段内无任何成交发生|开盘价（Open Price）沿用前一交易日收盘价（Close Price）|开盘价状态维持，不影响后续流程|
|C. 末笔成交缺失（No Closing Trade）|当日连续竞价时段内无任何成交发生|收盘价（Close Price）沿用前一交易日收盘价（Close Price）|收盘价状态维持，不影响后续流程|
|D. 资金/持仓不足（Insufficient Balance）|Market Order匹配时，用户可用资金（Buy）或可卖股数（Sell）不足|拒绝成交，订单立即失效|返回错误提示；不产生Transaction|

## 流程结束条件
- 订单被完全成交，或部分成交后剩余量为0  
- Limit Order被解挂（收盘自动触发）  
- Market Order因无对手方而无法执行（立即失败）  

## 上下游依赖
- 上游：用户订单提交接口（Frontend → Backend API）  
- 下游：Transaction Log写入（持久化）、行情推送（Bidding Board更新）、账户余额/持仓实时扣减  

## 测试检查点
- ✅ Market Buy Order必须匹配Ask队列最低价（且最早时间）  
- ✅ Limit Sell Order仅当Bid队列存在≥其price的订单时才成交  
- ✅ 同价订单严格按时间戳排序（FIFO）  
- ✅ 收盘时所有未成交Limit Order必须被清除并释放资源  
- ✅ 无成交日的Open/Close Price必须继承前一日值  

## 参考来源与模拟声明
- 来源：`stockFundamentalTheory.md` p4–p5 (“Matching Engine”, “Cách giá hình thành”)  
- 模拟声明：本流程**仅模拟HOSE连续竞价机制**，**不支持ATO/ATC、午休、涨跌幅动态调整（固定7%）**，**Book仅维护Top2 Bid/Ask用于显示**（但匹配逻辑覆盖全量队列）

