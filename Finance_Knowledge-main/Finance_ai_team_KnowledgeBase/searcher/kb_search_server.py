#!/usr/bin/env python3
"""
知识库检索 HTTP API 服务 — kb_search_server.py
==================================================
基于 FastAPI 的检索服务，供上层智能体 Agent 调用。

使用 kb_search.py 的检索管线实现，通过 HTTP API 暴露统一的知识检索接口。

启动方式（在项目根目录下运行）：
    python -m src.kb_search_server                      # 默认 0.0.0.0:8002
    python -m src.kb_search_server --port 9000          # 指定端口
    python -m src.kb_search_server --host 127.0.0.1     # 仅本机访问

API 文档：
    启动后浏览器打开 http://<IP>:<PORT>/docs 查看 Swagger 交互文档。

Agent 调用示例：
    # 稳定契约接口（推荐）
    curl -X POST http://localhost:8002/api/v1/search \
         -H "Content-Type: application/json" \
         -d '{"query": "创业板买入权限校验", "top_k": 5}'

    # 指定知识库编码过滤
    curl -X POST http://localhost:8002/api/v1/search \
         -H "Content-Type: application/json" \
         -d '{"query": "权限校验", "kb_codes": ["KB01", "KB03"], "top_k": 10}'
"""

import sys
import os
import logging
from pathlib import Path
from typing import List, Optional

# 将项目根目录加入 sys.path，确保与 sync_pipeline.py 导入方式一致
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field
from contextlib import asynccontextmanager

from searcher.kb_search import (
    run_pipeline,
    search_es_standalone,
    search_pg_standalone,
    search_neo4j_standalone,
)

# ---------- 日志 ----------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("kb_search_server")


# ============================================================
#  Pydantic 请求模型
# ============================================================

class SearchRequest(BaseModel):
    """
    Agent 统一检索请求（稳定契约，不建议随意修改字段名）。

    - query:   必填，用户原始查询文本。
    - kb_codes: 可选，限制检索的知识库编码（如 ["KB01", "KB03"]），空列表表示搜索所有。
    - top_k:   返回的最大 chunk 数量，1~50，默认 10。
    - expand_k: Neo4j 扩展的关键词数量，0~20，默认 3。
    """
    query: str = Field(
        ...,
        min_length=1,
        max_length=5000,
        description="用户原始查询文本",
        examples=["创业板买入权限校验失败 E403"],
    )
    kb_codes: List[str] = Field(
        default_factory=list,
        max_length=10,
        description="限制检索的知识库编码列表，空列表表示搜索全部",
        examples=[["KB01", "KB03"]],
    )
    top_k: int = Field(
        default=10,
        ge=1,
        le=50,
        description="返回的最大热门数",
    )
    expand_k: int = Field(
        default=3,
        ge=0,
        le=20,
        description="Neo4j 扩展关键词数量",
    )


class SearchHit(BaseModel):
    """单条检索结果的稳定结构。"""
    content: str = Field(description="切片正文")
    score: float = Field(description="最终排序分：BM25（含标题/章节加权）与向量排名经 RRF 融合后的分数")
    bm25_score: Optional[float] = Field(default=None, description="原始 BM25 词法分（无上限，越大字面越匹配）")
    vector_score: Optional[float] = Field(default=None, description="原始向量语义分（余弦相似度+1，0~2，越大语义越接近）")
    metadata: dict = Field(
        default_factory=dict,
        description="元数据: kb_code, title, heading, doc_id, chunk_id, source",
    )


class SearchResponse(BaseModel):
    """检索响应。"""
    query: str = Field(description="原始查询文本")
    results: List[SearchHit] = Field(description="检索结果列表")
    trace: dict = Field(
        default_factory=dict,
        description="追踪信息: core_keywords, expanded_keywords, result_count, bm25_count, vector_count；不暴露原始/过滤分词",
    )


# ============================================================
#  FastAPI 应用
# ============================================================

@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期：按配置决定是否预加载向量模型。"""
    if os.getenv("PRELOAD_EMBEDDING_MODEL", "false").lower() == "true":
        from shared.embedding import get_embedding_model
        get_embedding_model()
        logger.info("向量模型已预加载")
    else:
        logger.info("向量模型将在首次向量检索时延迟加载")
    yield


app = FastAPI(
    title="证券交易智能体知识库 — 统一检索 API",
    description=(
        "三段式检索管线：**Neo4j 图谱关键词扩展 → Elasticsearch BM25+向量混合检索 → PostgreSQL 元数据溯源**。\n\n"
        "支持两种调用方式：\n"
        "1. `/api/v1/search` — 稳定契约，面向 Agent\n"
        "2. `/search` — 兼容旧版多模式检索（pipe/es/pg/neo4j）"
    ),
    version="1.0.0",
    lifespan=lifespan,
)


# ============================================================
#  核心 API 路由
# ============================================================

@app.post(
    "/api/v1/search",
    response_model=SearchResponse,
    summary="Agent 统一知识库检索",
    description="接收用户查询，执行 Neo4j 扩展 + ES 混合检索 + PG 溯源，返回带元数据的稳定结果结构。",
)
def agent_search(req: SearchRequest):
    """
    Agent 调用入口。返回结构化的知识检索结果，包含：
    - content: 切片正文
    - score: 相关度评分
    - metadata: kb_code / title / heading / doc_id / chunk_id / source
    """
    try:
        pipeline_result = run_pipeline(
            query_text=req.query,
            top_k=req.top_k,
            expand_k=req.expand_k,
            skip_neo4j=(req.expand_k == 0),
            kb_codes=req.kb_codes,
        )
    except Exception as exc:
        logger.exception("检索管线执行失败")
        raise HTTPException(
            status_code=502,
            detail={
                "code": "knowledge_base_unavailable",
                "message": "知识库检索服务暂不可用",
            },
        ) from exc

    # 转换为稳定输出结构
    items: List[SearchHit] = []
    for hit in pipeline_result["merged_hits"]:
        content = hit.get("content", "").strip()
        if not content:
            continue
        pg_meta = pipeline_result["pg_metadata"].get(hit.get("chunk_id", ""), {})
        items.append(SearchHit(
            content=content,
            score=hit.get("score", 0),
            bm25_score=hit.get("bm25_score"),
            vector_score=hit.get("vector_score"),
            metadata={
                "kb_code": hit.get("kb_code", ""),
                "title": pg_meta.get("title", "") or hit.get("title", ""),
                "heading": hit.get("heading", ""),
                "doc_id": hit.get("doc_id", ""),
                "chunk_id": hit.get("chunk_id", ""),
                "source": hit.get("source", ""),
                "source_file": pg_meta.get("source_file", ""),
                "version": pg_meta.get("version", 0),
            },
        ))

    expansion = pipeline_result.get("neo4j_expansion", {}) or {}
    es_results = pipeline_result.get("es_results", {}) or {}

    return SearchResponse(
        query=pipeline_result["query"],
        results=items,
        trace={
            "core_keywords": expansion.get("core_keywords", []),
            "expanded_keywords": expansion.get("keywords", []),
            "result_count": len(items),
            "bm25_count": es_results.get("bm25_count", 0),
            "vector_count": es_results.get("vector_count", 0),
        },
    )


# ============================================================
#  兼容旧版 /search 接口（支持 pipe/es/pg/neo4j 模式）
# ============================================================

from pydantic import BaseModel as _BaseModel


class LegacySearchRequest(_BaseModel):
    """保留给旧调用方的 /search 契约。"""
    query: str = Field(min_length=1, max_length=5000)
    top_k: int = Field(default=10, ge=1, le=50)
    expand_k: int = Field(default=3, ge=0, le=20)
    mode: str = Field(default="pipe", description="pipe | es | pg | neo4j")


@app.post("/search", summary="兼容旧版多模式检索")
def legacy_search(req: LegacySearchRequest):
    """保留旧版 /search 接口，支持四种检索模式。"""
    try:
        if req.mode == "pipe":
            result = run_pipeline(
                req.query,
                top_k=req.top_k,
                expand_k=req.expand_k,
                skip_neo4j=(req.expand_k == 0),
            )
            return result

        elif req.mode == "es":
            return search_es_standalone(req.query, top_k=req.top_k)

        elif req.mode == "pg":
            return search_pg_standalone(req.query, top_k=req.top_k)

        elif req.mode == "neo4j":
            return search_neo4j_standalone(req.query, top_k=req.top_k)

        else:
            raise HTTPException(status_code=422, detail=f"未知模式: {req.mode}")

    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("检索失败")
        raise HTTPException(
            status_code=502,
            detail={
                "code": "knowledge_base_unavailable",
                "message": "知识库检索服务暂不可用",
            },
        ) from exc


# ============================================================
#  健康检查
# ============================================================

@app.get("/health", summary="进程存活检查")
def health():
    """返回服务健康状态。"""
    return {"status": "ok", "service": "kb_search_server"}


@app.get("/readiness", summary="依赖就绪检查")
def readiness():
    from searcher.db_conn import health_check_all

    checks = health_check_all()
    required_ready = (
        checks["postgres"] == "healthy"
        and checks["elasticsearch"] == "healthy"
    )
    if os.getenv("ENABLE_NEO4J", "false").lower() != "true":
        checks["neo4j"] = "disabled"
    return {
        "status": "ok" if required_ready else "degraded",
        "checks": checks,
    }


@app.get("/", summary="服务信息")
def root():
    return {
        "service": "证券交易智能体知识库 — 统一检索 API",
        "version": "1.0.0",
        "endpoints": {
            "agent_search": "POST /api/v1/search",
            "legacy_search": "POST /search",
            "health": "GET /health",
            "docs": "GET /docs",
        },
    }


# ============================================================
#  直接启动入口
# ============================================================

if __name__ == "__main__":
    import argparse
    import uvicorn

    p = argparse.ArgumentParser(description="知识库检索 HTTP API 服务")
    p.add_argument("--host", default="0.0.0.0", help="监听 IP（默认 0.0.0.0）")
    p.add_argument("--port", type=int, default=8002, help="监听端口（默认 8002）")
    args = p.parse_args()

    logger.info("启动检索 API 服务 → http://%s:%d/docs", args.host, args.port)
    uvicorn.run(
        "src.kb_search_server:app",
        host=args.host,
        port=args.port,
        reload=False,
        log_level="info",
    )
