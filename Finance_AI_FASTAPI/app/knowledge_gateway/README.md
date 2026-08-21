# knowledge_gateway — 知识库端接口

**负责人：人员C**

## 职责

文件物理存储 + 多格式文本提取。不碰 Agent、不碰业务数据库。

## 文件

| 文件 | 职责 |
|------|------|
| `extraction.py` | 多格式文本提取（文件类:PDF/DOCX/XLSX/TXT/CSV/JSON/MD，图片类:png,jpg,jpeg,gif,webp） |
| `ocr.py` | 图片 OCR 识别（EasyOCR 单例封装 + 图片预处理 + 置信度过滤 + OCR_PROVIDER 引擎开关） |

## 支持的文件格式

| 扩展名 | 解析方式 |
|--------|---------|
| `.txt` `.md` `.csv` `.json` | 直接解码（UTF-8-SIG → UTF-8 → GB18030 → UTF-8 fallback） |
| `.pdf` | PyMuPDF (fitz) |
| `.docx` | python-docx |
| `.xlsx` | openpyxl（遍历所有工作表，制表符分隔） |
| `.png` `.jpg` `.jpeg` `.gif` `.webp` | EasyOCR（中文+英文，CPU 模式）；OCR_PROVIDER=none 时禁用（返回空串） |

## 对外接口（供 api/ 层调用）

### `extract_text(path: str, extension: str, max_chars: int) -> tuple[str, bool]`

从已存储文件中提取纯文本。

**输入：**
```
path:      "/data/uploads/file_abc123.pdf"   ← 物理文件路径
extension: ".pdf"                             ← 小写扩展名
max_chars: 200000                             ← 最大字符数
```

**输出（契约 §5.1 降级语义）：**
```
("这是一份需求文档的完整内容...", False)     ← 普通文件 / OCR 成功
("", True)                                    ← 图片 OCR 失败/未识别出文字（不阻塞聊天）
```

**异常：**

| 场景 | 异常 |
|------|------|
| 不支持的文件类型 | `FileTextError("不支持的文件类型: .exe")` |
| 解析依赖未安装 | `FileTextError("服务端未安装 PDF 解析依赖 PyMuPDF")` |
| 文件损坏无法解析 | `FileTextError("PDF 文件解析失败")` |
| 文件中无文本 | `FileTextError("文件中没有可提取的文本")` |

> 图片相关场景（OCR 依赖未安装 / 图片损坏无法识别 / 未识别出文字）
> **不再抛异常**：返回 `("", True)`，由 api/ 层标记 `metadata.ocr_failed=true` 后继续聊天。

### `extract_text_from_image(raw: bytes, max_side: int = 2048, min_confidence: float = 0.5) -> str`

从图片字节流中提取文字（OCR）。

**输入：**
```
raw:            b'\x89PNG...'      ← 图片原始字节
max_side:       2048                 ← 长边最大像素数，超限自动等比缩放
min_confidence: 0.5                  ← 最低置信度阈值，低于此值的识别结果被丢弃
```

**输出：**
```
"识别出的文字\n按行分隔"
```

**实现要点：**

- EasyOCR 单例懒加载（双重检查锁），首次调用加载模型约 2-3 秒，后续复用
- 图片统一转 RGB（处理 RGBA/灰度/CMYK），大图等比缩放防 OOM
- 识别语言：中文简体 + 英文；CPU 模式（Windows 兼容）

### `SUPPORTED_EXTENSIONS: set[str]`

```python
{".pdf", ".docx", ".xlsx", ".md", ".txt", ".csv", ".json", ".png", ".jpg", ".jpeg", ".gif", ".webp"}
```

### `TEXT_EXTENSIONS: set[str]`

```python
{".txt", ".md", ".csv", ".json"}
```

### `IMAGE_EXTENSIONS: set[str]`

```python
{".png", ".jpg", ".jpeg", ".gif", ".webp"}
```

## 文本长度控制

- 单个文件截断到 `EXTRACTED_TEXT_MAX_CHARS`（默认 200,000）
- 单次请求所有附件总长度限制 `REQUEST_ATTACHMENTS_MAX_CHARS`（默认 400,000）
- 由 api/ 层调用方控制，extraction.py 只负责提取和 max_chars 截断

## 不负责

- 不操作数据库（由 data_gateway 处理文件记录）
- 不调用 Agent（由 agent_gateway 处理）
- 不管理文件上传的 HTTP 接收（由 api/files.py 处理）
- 不管理文件 TTL 过期清理（运维任务）

## 测试

不需要数据库或 Agent。每个格式准备一个 fixture 文件：

```bash
uv run pytest app/knowledge_gateway/tests/
```
