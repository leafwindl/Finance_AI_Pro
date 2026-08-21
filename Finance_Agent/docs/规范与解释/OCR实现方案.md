# OCR 图片识别实现方案（给 Gateway 对接方）

> 版本：v1.0（2026-08-10）
> 状态：**契约已冻结**（见《接口契约总表.md》§5.1），本文件是给 Gateway（8000）的**实现指引**。
> 目标场景：用户在对话助手中上传截图（如"不知道点哪里"），Gateway 识别图片内容 → 转成文本 → 走现有附件通道，Agent 侧零改动。

---

## 1. 背景与目标

对话助手（agent5）支持文档问答，但**只接收文本附件**（契约：Agent 不接收本地文件路径/图片，只收 Gateway 提取后的文本）。用户希望上传**截图**寻求操作指导——因此需要 Gateway 在文件提取阶段加入 OCR：图片 → 文本 → 进入 `attachments[].text`，agent5 的 `doc_qa` 意图自动生效。

**一句话**：OCR 是 Gateway 的实现职责，Agent 无感。

## 2. 契约约束（来自接口契约总表 §5.1，冻结）

| 项 | 规则 |
|---|---|
| 新增支持的 MIME | `image/png` `image/jpeg` `image/gif` `image/webp` |
| 提取流程 | Gateway 收到图片 → OCR 识别 → 文本进入 `attachments[].text`（与普通文件同通道） |
| 失败降级 | OCR 失败 → `attachments[].text` 为空字符串 + `metadata.ocr_failed: true`，**不阻塞聊天** |
| 上传响应 | `content_type` 保留原始图片 MIME；`status` 仍为 `ready` |
| 大小限制 | 图片单张 ≤ 5 MB（小于普通文件 10MB，控制 OCR 成本） |
| 前端 | 上传组件 accept 增加图片类型；其余逻辑复用现有 file_ids 通道 |

## 3. 实现方案

### 3.1 文件改动（Gateway 侧，约 3 处）

| 文件 | 改动 |
|---|---|
| `app/knowledge_gateway/extraction.py` | 增加 `image/*` 分支：调用 OCR 客户端；失败返回空文本 + 标记 |
| `app/core/config.py`（或 .env） | 新增 OCR 配置项（见 §3.3） |
| `tests/` | 契约测试：上传截图 → 聊天时 `attachments[].text` 含 OCR 文本；OCR 失败 → 空文本不阻塞 |

### 3.2 OCR 引擎选型（三选一，实现方自定）

| 方案 | 优点 | 缺点 | 适用 |
|---|---|---|---|
| **MinerU 在线 API** | 精度高（表格/公式强）、调用简单 | 需 API Key、数据出域（图片内容上传云端） | 有合规审批、追求精度 |
| **PaddleOCR 本地** | 数据不出域、免费 | 需装依赖（paddlepaddle ~1GB）、首次加载慢 | 金融合规要求高、无出域条件 |
| **其他（腾讯云/百度 OCR 等）** | 接入快 | 同上数据出域 | 公司已有云服务账号 |

> ⚠️ **合规提醒**：证券项目截图可能含敏感信息。**优先本地 PaddleOCR**（数据不出域）；若用云端 API 需确认公司合规允许。

### 3.3 配置项（.env 新增）

```dotenv
# OCR 开关与引擎：none=关闭 / mineru=在线 / paddle=本地
OCR_PROVIDER=none
# MinerU 在线（OCR_PROVIDER=mineru 时必填）
OCR_API_KEY=
OCR_API_BASE_URL=
# 超时（秒）
OCR_TIMEOUT_SECONDS=30
```

### 3.4 提取流程（伪代码）

```python
# app/knowledge_gateway/extraction.py
async def extract_text(file) -> ExtractedText:
    if file.content_type.startswith("image/"):
        if file.size > 5MB:  # 图片大小限制（契约）
            return ExtractedText(text="", ocr_failed=True, reason="image_too_large")
        if not ocr_enabled():  # OCR_PROVIDER=none
            return ExtractedText(text="", ocr_failed=True, reason="ocr_disabled")
        try:
            text = await ocr_recognize(file)   # 按 provider 分发
            return ExtractedText(text=text, ocr_failed=(not text.strip()))
        except Exception as e:
            return ExtractedText(text="", ocr_failed=True, reason=str(e))
    # ... 原有 pdf/docx/txt 分支不变
```

### 3.5 对 Agent 的影响（零改动，说明）

- `attachments[].text` 已是现有契约字段（≤200_000 字符）——OCR 文本走同一通道
- agent5 `doc_qa` 意图：用户上传截图 + 追问"我该点哪里" → 基于 OCR 文本回答
- `InternalChatRequest` 不新增字段（契约冻结）

## 4. 验收标准

- [ ] 上传 PNG/JPG 截图 → 上传响应 `content_type` 为图片 MIME、`status=ready`
- [ ] 聊天带图片 file_id → Agent 收到 `attachments[].text` 为 OCR 识别文本
- [ ] OCR 服务不可用 → 聊天正常（降级空文本 + `metadata.ocr_failed: true`）
- [ ] 普通文档（pdf/docx）提取不受影响
- [ ] 图片 >5MB 被拒或降级，不阻塞

## 5. 时序

```
用户上传截图 → Gateway 存文件(ready) → 聊天带 file_id
  → Gateway extract_text(image) → OCR → attachments[].text
  → Agent agent5 doc_qa 基于文本回答（无感）
```

## 6. 一句话总结

**OCR = Gateway 在文件提取阶段加一层图片→文本**；引擎选型优先本地（合规），失败降级不阻塞；Agent 侧零改动（复用现有附件文本通道）。契约已冻结于《接口契约总表.md》§5.1。
