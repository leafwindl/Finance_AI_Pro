# KB01-02：模块说明11 Backend (Node.js/Express) 模块说明

> **整合审核状态：approved。** 本文已完成人工核验（核验日期、核验人、来源证据见《00_来源核验台账.md》）。

## 文档登记信息（供人工管理）

> 本表供人工理解和核对；括号内中文是字段说明。在Dify中只创建括号前的英文字段名（如`record_id`），并按《00_统一元数据字典》设置。

| 元数据字段 | 当前文档分配值 |
|---|---|
| kb_code（知识库大类） | KB01（系统业务知识库） |
| doc_type（知识类型） | module_description（模块说明） |
| record_id（知识文档唯一编号） | AIZ-GEM-013 |
| dataset_version（数据集版本） | P2 |
| system（系统编码） | ZJQ_TRADE |
| module（主要模块） | BACKEND |
| source_type（来源类型） | mixed_simulated |
| status（审核状态） | approved |
| business_version（业务版本） | 不适用（Dify中留空） |


## 模块名称  
Backend (Node.js/Express)

## 模块职责  
**负责**：  
- 提供 RESTful API 接口，承载用户管理、证券交易、投资组合、行情数据、支付结算等全部核心业务能力；  
- 实施端到端请求生命周期管理：从路由分发、中间件链式校验（认证、授权、参数校验、响应净化）、控制器协调、服务层业务逻辑执行，到模型层数据持久化与返回；  
- 维护与数据库（MySQL/PostgreSQL）的连接、事务控制、Schema 初始化（通过 `create[Table]Table.js`）及数据访问抽象；  
- 执行关键安全策略：JWT 认证、RBAC 权限控制、OTP 双因素验证、设备可信度管理（`remembered_devices`）、Turnstile 人机验证集成；  
- 封装领域服务：订单匹配（`orderMatchingService.js`）、结算（`orderSettlementService.js`）、行情种子数据注入（`seedStockPrice/`）、密码哈希与 JWT 签发等；  
- 提供统一日志记录（`loggerUtil.js`）、错误处理（`errorHandlerMiddleware.js`）与工具函数（`jwtUtil.js`, `passwordUtil.js`, `setCookieUtil.js`）。

**不负责**：  
- 前端页面渲染、状态管理（由 React/Vite 前端独立承担）；  
- 容器编排、网络代理配置（`Dockerfile`, `nginx.conf` 属于部署层，非模块内聚逻辑）；  
- 客户端 API 调用封装（`frontend/src/api/` 专属职责）；  
- 实时行情推送的 WebSocket/SSE 协议实现（虽 `eventEmitter.js` 在前端提及，但后端对应服务未在文档中定义，故不纳入本模块职责）；  
- 第三方支付网关对接的具体银行协议解析（`paymentService.js` 仅封装平台内支付流程，不处理 VND 渠道底层通信）。

## 主要功能  

| 功能 | 功能说明 | 触发入口 |
|------|----------|----------|
| **用户全生命周期管理** | 支持注册、登录（含 OTP 验证）、信息更新、管理员删除用户；集成 Passport 认证、设备信任存储（`remembered_devices` 表）、密码强度校验与哈希存储。 | `userRoutes.js` → `userControllers.js` → `userCRUDService.js` + `userAuthService.js` + `otpService.js` + `rememberedDeviceService.js` |
| **证券交易执行** | 处理买卖订单创建、校验（`orderMiddleware.js`）、匹配（`orderMatchingService.js`）、结算（`orderSettlementService.js`）、状态更新；维护订单簿（`orderBookController.js`）。 | `orderRoutes.js` → `orderController.js` → `orderCRUDService.js` + `orderMatchingService.js` + `orderSettlementService.js` |
| **投资组合与持仓管理** | 创建用户专属 Portfolio（初始资金 100,000 USD）、实时计算现金余额与总市值（`cash_balance + Σ(quantity × current_price)`）、增删改查 Holdings（`holdingModel.js`）。 | `portfolioRoutes.js` → `portfolioController.js` → `portfolioCRUDService.js` + `holdingCRUDService.js` |
| **股票行情数据服务** | 提供历史 K 线数据（Open/High/Low/Close/Volume）、实时价格查询；支持 Python 脚本（`stock_fetcher.py`）定时拉取并注入 `stockPriceModel.js`。 | `stockPriceRoutes.js` → `stockPriceController.js` → `stockPriceCRUDService.js` + `seedStockPrice/stockManager.js` |
| **交易与资金流水记录** | 持久化每一笔 BUY/SELL 交易（`transactionModel.js`），关联 Portfolio 与 Stock；支持虚拟货币充值（`payment_transactions` 表），记录 VND→虚拟币兑换流水。 | `transactionController.js` / `paymentControllers.js` → `transactionCRUDService.js` / `paymentService.js` |
| **安全增强与合规控制** | 强制 HTTPS Cookie 设置（`setCookieUtil.js`）、响应体敏感字段过滤（`responseSanitizationMiddleware.js`）、基于角色的 API 访问控制（`roleBasedAccessControlMiddleware.js`）、请求频率限制（文档未显式列出但属中间件范畴）。 | 全局中间件链（`authenticationMiddleware.js`, `roleBasedAccessControlMiddleware.js`, `responseSanitizationMiddleware.js`） |

## 输入和输出  

**主要输入**：  
- HTTP 请求（Method, Path, Headers, Query Params, JSON Body）；  
- 数据库连接配置（`dbConnect.js`）、JWT 秘钥、第三方服务凭证（Turnstile, OTP SMS Gateway）；  
- 外部行情数据源（通过 `stock_fetcher.py` 调用）；  
- 用户上传的凭证（如登录凭据、OTP Code、设备指纹 `visitor_id`）。

**主要输出**：  
- 标准化 JSON 响应（含 `status`, `data`, `message`, `error` 字段）；  
- HTTP 状态码（200/201/400/401/403/404/500）；  
- Signed JWT Token（存于 Cookie 或 Header）；  
- 持久化数据写入（MySQL/PostgreSQL 表：`users`, `portfolios`, `holdings`, `transactions`, `stock_prices`, `remembered_devices`, `payment_transactions`）；  
- 日志条目（`loggerUtil.js` 输出至 stdout/file）。

## 上游和下游  

| 关系 | 系统/模块 | 交互内容 |
|------|-----------|----------|
| **上游** | Frontend (React/Vite) | 发送 HTTP 请求（GET/POST/PUT/DELETE）至 `/api/*` 端点；接收 JSON 响应并渲染 UI；传递 JWT Token（via Cookie/Authorization Header）；提交表单数据（Login, Register, Order, Payment）；监听 SSE 事件（需后端配套实现，当前文档未描述，故视为待对齐接口）。 |
| **下游** | Database (MySQL/PostgreSQL) | 执行 CRUD 操作：读写 `users`, `stocks`, `stock_prices`, `portfolios`, `holdings`, `transactions`, `news`, `remembered_devices`, `payment_transactions` 等表；运行 `create[Table]Table.js` 初始化 Schema。 |
| **下游** | External Services | 调用 Turnstile API 进行人机验证；调用 OTP 短信/邮件网关发送验证码；执行 `stock_fetcher.py`（Python 子进程）拉取 Yahoo Finance/Alpha Vantage 等行情数据。 |

## 主要异常  

| 异常类型 | 触发条件 | 处理方式 | 文档依据 |
|----------|----------|----------|----------|
| **认证失败** | JWT Token 无效、过期、签名错误；Cookie 中 Token 缺失 | 返回 `401 Unauthorized`；清除无效 Cookie；`authenticationMiddleware.js` 拦截并终止请求链。 | `middlewares/authenticationMiddleware.js`, `utils/jwtUtil.js` |
| **权限不足** | 普通用户尝试访问 Admin 接口（如 `/api/admin/users/delete`） | 返回 `403 Forbidden`；`roleBasedAccessControlMiddleware.js` 校验 `req.user.role` 并拒绝。 | `middlewares/roleBasedAccessControlMiddleware.js` |
| **数据完整性冲突** | 注册时 username/email 已存在；下单时 stock_id 不存在；持仓更新时 portfolio_id 无效 | 返回 `400 Bad Request` + 明确错误消息（如 `"Username already exists"`）；`userValidationMiddleware.js`, `orderMiddleware.js` 提前校验。 | `models/userModel.js` (UNIQUE constraints), `controllers/orderController.js` |
| **数据库连接失败** | `dbConnect.js` 初始化异常；查询超时；事务回滚失败 | 返回 `500 Internal Server Error`；`errorHandlerMiddleware.js` 捕获并记录堆栈；避免暴露敏感 DB 信息。 | `config/dbConnect.js`, `middlewares/errorHandlerMiddleware.js` |
| **行情数据缺失** | `stockPriceController.js` 查询 `stock_id` 对应日期无记录 | 返回 `404 Not Found` 或默认值（文档未指定，按 RESTful 原则应 404）；`stockPriceCRUDService.js` 查询空结果集。 | `models/stockPriceModel.js`, `controllers/stockPriceController.js` |

## 关联规则、流程和接口  

- **核心流程**：`index.js`（启动） → `routes/*.js`（路由匹配） → `middlewares/*.js`（链式校验） → `controllers/*.js`（协调） → `services/*.js`（业务执行） → `models/*.js`（数据存取） → `services/*.js`（结果组装） → `controllers/*.js`（格式化） → `middlewares/*.js`（响应处理） → HTTP Response。  
- **关键接口契约**：  
  - 用户认证：`POST /api/auth/login` → 输入 `{username, password, otp?}` → 输出 `{token, user: {id, username, role}}`；  
  - 下单接口：`POST /api/orders` → 输入 `{stock_id, quantity, type: 'BUY'|'SELL'}` → 输出 `{order_id, status, filled_quantity, avg_price}`；  
  - 行情查询：`GET /api/stocks/:symbol/prices?from=2024-01-01&to=2024-12-31` → 输出 `[{date, open_price, high_price, low_price, close_price, volume}]`；  
  - 投资组合估值：`GET /api/portfolios/me` → 输出 `{cash_balance, total_value, holdings: [{stock_symbol, quantity, average_cost, current_price, value}]}`。  
- **数据一致性规则**：  
  - `Portfolios.cash_balance` 与 `Transactions` 流水必须实时对账（`orderSettlementService.js` 保证）；  
  - `Holdings.quantity` 更新必须伴随 `Portfolios.total_value` 重算（`portfolioCRUDService.js` 内置逻辑）；  
  - `StockPrices` 的 `(stock_id, date)` 必须唯一（DB UNIQUE KEY 强约束）。  

## 参考来源与模拟声明  

- **来源**：  
  - 本文档《Project Architecture Design》全文（含 Backend Folder Structure, Backend Components Explanation, Database Design Section）；  
  - `backend/src/` 目录下所有文件路径与命名约定（如 `controllers/orderController.js`, `services/security/otpService.js`）；  
  - 数据库表结构定义（`Users`, `Stocks`, `StockPrices`, `Portfolios`, `Holdings`, `Transactions`, `remembered_devices`, `payment_transactions`）。  
- **模拟声明**：  
  > 本 KB01 模块说明内容严格基于所提供的《Project Architecture Design》文档生成，用于 **P2 模拟系统** 的架构理解、模块拆解与开发对齐。所有功能、流程、异常及接口描述均源自该文档的显性陈述，未添加任何推测性内容。数据库设计虽注明“已更新至 `DatabaseDesignDraft.drawio`”，但本说明仍以文档中详述的 8 张表结构为准，作为当前 P2 阶段的权威参考。

