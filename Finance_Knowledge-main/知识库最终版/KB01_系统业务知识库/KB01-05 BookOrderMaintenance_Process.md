# KB01-05 业务流程01 BookOrderMaintenance_Process

> **整合审核状态：approved。** 本文已完成人工核验（核验日期、核验人、来源证据见《00_来源核验台账.md》）。

## 文档登记信息（供人工管理）

> 本表供人工理解和核对；括号内中文是字段说明。在Dify中只创建括号前的英文字段名（如`record_id`），并按《00_统一元数据字典》设置。

| 元数据字段 | 当前文档分配值 |
|---|---|
| kb_code（知识库大类） | KB01（系统业务知识库） |
| doc_type（知识类型） | business_process（业务流程） |
| record_id（知识文档唯一编号） | AIZ-GEM-033 |
| dataset_version（数据集版本） | P2 |
| system（系统编码） | ZJQ_TRADE |
| module（主要模块） | MATCHING |
| source_type（来源类型） | mixed_simulated |
| status（审核状态） | approved |
| business_version（业务版本） | 不适用（Dify中留空） |

## 流程名称和目的
订单簿维护流程（Book Order Maintenance Process）：为每只股票构建并实时维护双向订单队列（Bid/Ask），支持价格-时间优先检索，是Matching Engine的底层数据基础设施。

## 参与角色和模块
|角色/模块|职责|
|---|---|
|Book Manager|内存管理模块：为每只股票实例化独立Book；执行插入/删除/查询操作|
|Matching Engine|调用Book Manager的API进行对手方检索与状态更新|
|Bidding Board|定时拉取Book的Top2 Bid/Ask用于前端显示（原文p6：“chỉ hiện thị 2 giá mua và 2 giá bán tốt nhất”）|

## 前置条件
- 股票代码已注册，Book Manager为其分配专属内存空间  
- 系统处于TRADING状态  
- **关键约束**：Book物理上存储全量Limit Order，但对外仅暴露Top2（原文p6：“chỉ hiện thị 2 giá... thay vì 3 giá như trên bảng giá thực tế”）  

## 正常流程
|步骤|操作方/模块|操作或请求|系统处理|输出/状态变化|
|---|---|---|---|---|
|1|Book Manager|股票首次交易|初始化空Bid队列（max-heap by price）和Ask队列（min-heap by price）|Book结构创建完成|
|2|Matching Engine|执行成交|从Bid/Ask中移除完全成交的订单；更新部分成交订单的quantity|Book队列长度/内容变更|
|3|Matching Engine|插入新Limit Order|按price插入Bid（Buy）或Ask（Sell）队列；同price时按timestamp排序（FIFO）|Book队列增长|
|4|Book Manager|响应Bidding Board查询|返回Bid队列中price最高的2个元素（含quantity）；Ask队列中price最低的2个元素|Top2数据快照生成|

## 异常分支
|分支|触发条件|处理方式|最终结果|
|---|---|---|---|
|A. 内存溢出（Memory Overflow）|单只股票Book累积订单超阈值（如1M条）|触发LRU淘汰策略：移除最旧的N条未成交订单（本文未定义，应标记为TODO）|Book大小受控，但可能丢失历史流动性信息|
|B. 队列损坏（Heap Corruption）|价格/时间索引异常导致排序失效|Book Manager重启该股票Book，从Transaction Log重建状态|短暂服务中断，数据一致性保障|
|C. Top2查询超时|Bidding Board请求响应>500ms|返回缓存Last Known Good Top2，并告警|前端显示延迟，但不阻塞交易|

## 流程结束条件
- Book Manager持续运行，响应所有CRUD请求  
- Top2数据每秒至少刷新1次（满足行情显示要求）  

## 上下游依赖
- 上游：OrderValidation_Process（提供合法Limit Order）  
- 下游：OrderMatching_Process（依赖Book检索）、Bidding Board（依赖Top2查询）  

## 测试检查点
- ✅ Bid队列必须按price降序，同price按time升序（最高买价+最早时间优先）  
- ✅ Ask队列必须按price升序，同price按time升序（最低卖价+最早时间优先）  
- ✅ 插入10万条随机订单后，Top2查询响应时间 ≤ 10ms  
- ✅ 完全成交订单必须从Book中物理删除（非标记删除）  

## 参考来源与模拟声明
- 来源：`stockFundamentalTheory.md` p4–p5（“duy trì một sổ lệnh (Book Order) cho mỗi mã cổ phiếu”, “Hiển thị 3 giá... nhưng thực tế Book Order vẫn phải xử lý với tất cả các lệnh”）  
- 模拟声明：**Book是纯内存结构，不持久化；其正确性直接决定Matching Engine结果的准确性**

