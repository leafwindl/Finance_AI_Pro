"""服务间数据契约。

parse-service → classify-service → ingest-service
三个服务之间通过以下数据结构交换数据，与具体传输协议无关。
"""

from dataclasses import dataclass, field


# ═══════════════════════════════════════════════════════════════
# 解析服务 → 分类服务
# ═══════════════════════════════════════════════════════════════


@dataclass
class CleanedText:
    """解析服务输出 = 分类服务输入。

    所有格式（txt/pdf/docx/html/md）的解析器统一输出此结构，
    分类服务只认 CleanedText，不关心原始文件格式。
    """

    content: str
    """清洗后的纯文本内容"""

    source_filename: str
    """原始文件名（如 report.pdf）"""

    source_type: str
    """原始文件类型：txt | pdf | docx | html | md"""

    encoding: str = "utf-8"
    """文本编码（PDF/图片 OCR 无此概念，填空字符串）"""

    content_hash: str = ""
    """内容 SHA256 哈希，用于去重判断"""

    metadata: dict = field(default_factory=dict)
    """格式特有的附加信息，如 {"pages": 12, "author": "xxx"}"""


# ═══════════════════════════════════════════════════════════════
# 分类服务 → 接入服务
# ═══════════════════════════════════════════════════════════════


@dataclass
class ChunkItem:
    """单个知识 chunk。"""

    kb_id: str
    """KB01 ~ KB06"""

    chunk_id: str
    """全局唯一编号，如 KB01-003"""

    method: str
    """分类方式：llm | rule_fallback"""

    confidence: float
    """分类置信度 0.0 ~ 1.0"""

    source_file: str
    """来源文件名"""

    source_h1: str
    """来源 H1 标题"""

    source_h2: str
    """来源 H2 标题"""

    source_h3: str = ""
    """来源 H3 标题（可选）"""

    content: str = ""
    """chunk 正文（Markdown）"""

    refs: dict = field(default_factory=dict)
    """关联的其他 KB，如 {"secondary_kb": ["KB05"]}"""

    needs_review: bool = False
    """是否需要人工复核"""

    legal_ref: str = ""
    """法规引用（仅 KB02）"""


@dataclass
class ClassifyResponse:
    """分类服务的完整响应。"""

    chunks: list[ChunkItem] = field(default_factory=list)
    """本次分类产出的所有 chunk"""

    stats: dict[str, int] = field(default_factory=dict)
    """各 KB 的 chunk 数量，如 {"KB01": 3, "KB02": 1}"""

    review_count: int = 0
    """需要人工复核的 chunk 数量"""

    method: str = "llm"
    """使用的分类方法"""

    error: str = ""
    """分类失败时的错误信息"""


# ═══════════════════════════════════════════════════════════════
# 接入服务 → 调用方
# ═══════════════════════════════════════════════════════════════


@dataclass
class IngestResponse:
    """接入服务的完整响应（从上传文件到 chunk 产出）。"""

    success: bool = True
    """整体是否成功"""

    parse_time_ms: int = 0
    """解析耗时（毫秒）"""

    classify_time_ms: int = 0
    """分类耗时（毫秒）"""

    chunks: list[ChunkItem] = field(default_factory=list)
    """产出的所有 chunk"""

    stats: dict[str, int] = field(default_factory=dict)
    """各 KB chunk 数量"""

    review_count: int = 0
    """待复核数量"""

    source_filename: str = ""
    """原始文件名"""

    error: str = ""
    """失败时的错误信息"""
