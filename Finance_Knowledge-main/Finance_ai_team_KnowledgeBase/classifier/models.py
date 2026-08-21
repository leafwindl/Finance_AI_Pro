"""编排模块数据类。"""

from dataclasses import dataclass, field


@dataclass
class H2Block:
    """从 DOM 提取的 H2 块。"""

    index: int
    h1: str
    h2_title: str
    h3_children: list[str] = field(default_factory=list)  # H3 标题列表
    h3_contents: list[str] = field(default_factory=list)  # H3 对应的正文（按序对应）
    content_preview: str = ""  # 正文前 300 字
    source_file: str = ""
    confidence: str = ""       # original | inferred | unparsed
    identified_refs: list[str] = field(default_factory=list)


@dataclass
class ClassifyResult:
    """一个 H2 块的分类结果。"""

    index: int
    primary_kb: str           # "KB01" ~ "KB06"
    sub_category: str = ""    # KB01-04 等子类编号
    secondary_kb: list[str] = field(default_factory=list)
    confidence: float = 0.0   # 0-1
    keywords: list[str] = field(default_factory=list)
    needs_review: bool = False
    method: str = "llm"       # llm | rule_fallback
    legal_ref: str = ""       # KB02 法规条款号
    raw_response: str = ""    # LLM 原始输出（调试用）


@dataclass
class Chunk:
    """一个输出 chunk。"""

    kb_id: str
    chunk_id: str
    method: str
    confidence: float
    source_file: str
    source_h1: str
    source_h2: str
    h3_title: str = ""
    sub_category: str = ""          # KB01-04 等子类编号
    content: str = ""
    refs: dict[str, list[str]] = field(default_factory=dict)
    needs_review: bool = False
    legal_ref: str = ""


@dataclass
class KBIndex:
    """全量 chunk 索引。"""

    chunks: list[dict] = field(default_factory=list)
    stats: dict[str, int] = field(default_factory=dict)
    review_count: int = 0
    generated_at: str = ""
    run_id: str = ""
    files_processed: list[str] = field(default_factory=list)
