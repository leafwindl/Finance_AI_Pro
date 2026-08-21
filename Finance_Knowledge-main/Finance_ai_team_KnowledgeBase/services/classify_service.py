"""分类服务 — FastAPI

接收清洗后的文本，进行结构识别 + LLM 分类，返回 KB chunk。

不写文件，不依赖 storage——纯计算服务。

API:
    POST /classify       — 单篇文档分类
    POST /classify/batch — 批量分类
    GET  /health         — 健康检查（含 LLM 连通性）
"""

import logging
import os
import re
import time
import traceback

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from parser.cleaner import clean_text
from classifier.segmenter import LLMSegmenter

from shared.models import CleanedText, ChunkItem, ClassifyResponse


# ── 日志 ──
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("classify-service")

app = FastAPI(
    title="知识库分类服务",
    description="文本结构识别 + LLM 六库分类 → 结构化 chunk",
    version="1.0.0",
)

_classifier: LLMSegmenter | None = None


def _get_classifier() -> LLMSegmenter:
    """延迟初始化 LLM 分类器（从环境变量读取配置）。"""
    global _classifier
    if _classifier is not None:
        return _classifier

    api_key = os.getenv("LLM_API_KEY", "")
    model = os.getenv("LLM_MODEL", "deepseek-chat")
    endpoint = os.getenv("LLM_ENDPOINT", "https://api.deepseek.com/v1/chat/completions")

    _classifier = LLMSegmenter(
        api_key=api_key,
        model=model,
        endpoint=endpoint,
        max_retries=2,
        enable_fallback=True,
    )

    if api_key and _classifier.ping():
        logger.info("LLM 连通性检查通过 (%s)", model)
    else:
        logger.warning("LLM 不可用，将使用规则兜底")

    return _classifier


# ── 请求模型 ──

class ClassifyRequest(BaseModel):
    content: str
    source_filename: str = "document.txt"
    source_type: str = "txt"
    encoding: str = "utf-8"
    content_hash: str = ""
    metadata: dict = {}

    @classmethod
    def from_cleaned_text(cls, ct: CleanedText) -> "ClassifyRequest":
        return cls(
            content=ct.content,
            source_filename=ct.source_filename,
            source_type=ct.source_type,
            encoding=ct.encoding,
            content_hash=ct.content_hash,
            metadata=ct.metadata,
        )


class ClassifyBatchRequest(BaseModel):
    documents: list[ClassifyRequest]


# ── 路由 ──

@app.get("/health")
async def health():
    classifier = _get_classifier()
    llm_ok = bool(os.getenv("LLM_API_KEY", ""))
    return {
        "status": "ok",
        "llm_available": llm_ok,
        "model": os.getenv("LLM_MODEL", "deepseek-chat"),
    }


@app.post("/classify", response_model=dict)
async def classify(req: ClassifyRequest):
    """对单篇文档进行结构识别 + KB 分类。

    Args:
        req: ClassifyRequest — 包含清洗后文本和来源信息

    Returns:
        ClassifyResponse JSON
    """
    t0 = time.time()
    try:
        chunks, stats, review_count = _run_pipeline(
            content=req.content,
            source_filename=req.source_filename,
            source_type=req.source_type,
        )
        elapsed_ms = int((time.time() - t0) * 1000)

        return {
            "success": True,
            "elapsed_ms": elapsed_ms,
            "data": {
                "chunks": [c.__dict__ for c in chunks],
                "stats": stats,
                "review_count": review_count,
            },
        }

    except Exception as e:
        traceback.print_exc()
        raise HTTPException(500, f"分类失败: {str(e)}")


@app.post("/classify/batch", response_model=dict)
async def classify_batch(req: ClassifyBatchRequest):
    """批量分类多篇文档。"""
    results = []
    errors = []
    for doc in req.documents:
        try:
            chunks, stats, review_count = _run_pipeline(
                content=doc.content,
                source_filename=doc.source_filename,
                source_type=doc.source_type,
            )
            results.append({
                "source": doc.source_filename,
                "chunks": [c.__dict__ for c in chunks],
                "stats": stats,
                "review_count": review_count,
            })
        except Exception as e:
            errors.append({"source": doc.source_filename, "error": str(e)})

    return {
        "total": len(req.documents),
        "success": len(results),
        "errors": len(errors),
        "results": results,
        "error_details": errors,
    }


# ── 核心流水线 ──

def _run_pipeline(
    content: str,
    source_filename: str,
    source_type: str = "txt",
) -> tuple[list[ChunkItem], dict[str, int], int]:
    """执行清洗→分段/分类→ChunkItem 转换流水线。

    Returns:
        (chunks, stats, review_count)
    """
    # 1. 冗余清洗（上游已经清洗过，这里做兜底）
    cleaned = clean_text(content, remove_page_numbers=False)

    # 分段器优先调用 LLM，失败时使用项目内置规则 fallback。
    segments = _get_classifier().segment(cleaned, source_name=source_filename)
    h1_title = source_filename

    # 将现有 SegmentResult 转换为服务间约定的 ChunkItem。
    chunks: list[ChunkItem] = []
    for segment in segments:
        chunks.append(ChunkItem(
            kb_id=segment.primary_kb,
            chunk_id="",
            method="llm" if segment.confidence > 0.3 else "rule_fallback",
            confidence=segment.confidence,
            source_file=source_filename,
            source_h1=h1_title,
            source_h2=segment.title,
            source_h3=segment.title,
            content=segment.content,
            refs={"secondary_kb": segment.secondary_kb} if segment.secondary_kb else {},
            needs_review=segment.needs_review,
            legal_ref=segment.legal_ref,
        ))

    # 7. 统计
    stats: dict[str, int] = {}
    for c in chunks:
        stats[c.kb_id] = stats.get(c.kb_id, 0) + 1
    review_count = sum(1 for c in chunks if c.needs_review)

    return chunks, stats, review_count
