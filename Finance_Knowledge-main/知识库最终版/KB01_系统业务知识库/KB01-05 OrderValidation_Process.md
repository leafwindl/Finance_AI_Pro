# KB01-05 业务流程03 OrderValidation_Process

> **整合审核状态：approved。** 本文已完成人工核验（核验日期、核验人、来源证据见《00_来源核验台账.md》）。

## 文档登记信息（供人工管理）

> 本表供人工理解和核对；括号内中文是字段说明。在Dify中只创建括号前的英文字段名（如`record_id`），并按《00_统一元数据字典》设置。

| 元数据字段 | 当前文档分配值 |
|---|---|
| kb_code（知识库大类） | KB01（系统业务知识库） |
| doc_type（知识类型） | business_process（业务流程） |
| record_id（知识文档唯一编号） | AIZ-GEM-035 |
| dataset_version（数据集版本） | P2 |
| system（系统编码） | ZJQ_TRADE |
| module（主要模块） | BACKEND |
| source_type（来源类型） | mixed_simulated |
| status（审核状态） | approved |
| business_version（业务版本） | 不适用（Dify中留空） |

## 流程名称和目的
订单校验流程（Order Validation Process）：在订单进入Matching Engine前，执行强制性业务规则检查，拦截无效订单，保障系统数据一致性与风控底线。

## 参与角色和模块
|角色/模块|职责|
|---|---|
|Frontend|收集用户输入，初步格式校验（数字、正整数）|
|Validation Gateway|核心校验模块：执行全部业务规则判断|
|Pricing Engine|提供实时Ceiling/Floor/Reference Price供比对|

## 前置条件
- 用户已通过身份认证，且账户状态为ACTIVE  
- 目标股票处于TRADING状态（非停牌）  
- Pricing Engine已就绪（Reference/Ceiling/Floor已计算）  

## 正常流程
|步骤|操作方/模块|操作或请求|系统处理|输出/状态变化|
|---|---|---|---|---|
|1|Frontend|用户提交订单表单|检查price/quantity是否为数字、quantity > 0|格式有效则转发|
|2|Validation Gateway|接收订单|调用Pricing Engine获取当前Ceiling/Floor|—|
|3|Validation Gateway|校验价格区间|若为Limit Order：<br>• Buy：检查 order.price ≤ Ceiling 且 order.price ≥ Floor<br>• Sell：检查 order.price ≥ Floor 且 order.price ≤ Ceiling<br>若为Market Order：跳过价格检查（原文p3：“Lệnh thị trường... không yêu cầu nhập giá cụ thể”）|校验通过/失败|
|4|Validation Gateway|校验资金/持仓|Buy Order：检查可用资金 ≥ order.price × order.quantity × (1 + fee)<br>Sell Order：检查可卖股数 ≥ order.quantity|校验通过/失败|
|5|Validation Gateway|返回结果|若全部通过 → 转发至Matching Engine<br>若任一失败 → 返回具体错误码（如PRICE_OUT_OF_RANGE, INSUFFICIENT_BALANCE）|订单被接受或拒绝|

## 异常分支
|分支|触发条件|处理方式|最终结果|
|---|---|---|---|
|A. 价格越界（Price Out of Range）|Limit Order.price < Floor 或 > Ceiling（原文p2：“nhà đầu tư có thể đặt bất cứ giá nào miễn là giá sàn <= giá đặt <= giá trần”）|拒绝订单，返回错误码PRICE_OUT_OF_RANGE|用户必须修改价格后重试|
|B. 资金不足（Insufficient Funds）|Buy Order所需资金 > 账户可用现金（含冻结）|拒绝订单，返回错误码INSUFFICIENT_BALANCE|用户需充值或降低quantity|
|C. 持仓不足（Insufficient Shares）|Sell Order quantity > 可卖股数（含T+2未交割）|拒绝订单，返回错误码INSUFFICIENT_SHARES|用户需等待交割或减少quantity|
|D. 停牌股票（Suspended Stock）|目标股票State = SUSPENDED（原文未明说，但属交易所通用规则）|拒绝订单，返回错误码STOCK_SUSPENDED|用户无法交易该股票|

## 流程结束条件
- 订单被转发至Matching Engine（成功）  
- 或返回明确错误码并终止（失败）  

## 上下游依赖
- 上游：Frontend订单提交接口  
- 下游：OrderMatching_Process（仅接收校验通过的订单）  

## 测试检查点
- ✅ Buy Limit Order.price = Floor时必须允许提交（边界包含）  
- ✅ Market Order必须绕过价格校验（即使price字段为空）  
- ✅ 校验失败时，错误码必须精准定位问题（而非笼统“Invalid Order”）  
- ✅ 资金校验必须包含手续费（本文未定义费率，应标记为TODO）  

## 参考来源与模拟声明
- 来源：`stockFundamentalTheory.md` p2（“giá sàn <= giá đặt <= giá trần”）、p3（Market Order定义）、p4（资金返还暗示资金校验存在）  
- 模拟声明：**本流程是风控第一道闸门，所有订单必须100%经过此处，无旁路**

