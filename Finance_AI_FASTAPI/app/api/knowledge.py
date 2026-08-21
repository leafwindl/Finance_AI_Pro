from __future__ import annotations

import logging
from typing import Annotated

import asyncpg
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse

from app.api.auth import get_current_user
from app.data_gateway.kb_pool import get_kb_pool
from app.data_gateway.repositories.knowledge_docs import (
    get_document_content,
    list_documents_by_kb,
    list_kbs,
)
from app.graph_gateway.neo4j import fetch_document_subgraph, fetch_graph, get_driver

logger = logging.getLogger("uvicorn.error")

router = APIRouter(prefix="/api/v1/knowledge", tags=["knowledge"])


def _upstream_unavailable(code: str, message: str) -> JSONResponse:
    """按 gateway-api.md 结构化错误契约返回 503（顶层 `{"error": ...}`）。"""
    return JSONResponse(
        status_code=503,
        content={"error": {"code": code, "message": message, "retryable": True}},
    )


@router.get("/graph")
async def knowledge_graph(
    user: Annotated[dict, Depends(get_current_user)],
) -> dict:
    """读取知识库→文件两级全图（Neo4j）。"""
    try:
        driver = await get_driver()
        return await fetch_graph(driver)
    except Exception as exc:
        logger.exception("[request] knowledge graph unavailable: %s", exc)
        return _upstream_unavailable(
            "knowledge_graph_unavailable", "知识图谱服务暂不可用，请确认 Neo4j 已启动"
        )


@router.get("/kbs")
async def kb_list(
    user: Annotated[dict, Depends(get_current_user)],
    kb_pool=Depends(get_kb_pool),
) -> dict:
    """知识库清单（PG knowledge_base）。"""
    try:
        kbs = await list_kbs(kb_pool)
    except Exception as exc:
        logger.exception("[request] knowledge docs unavailable: %s", exc)
        return _upstream_unavailable("knowledge_docs_unavailable", "知识库服务暂不可用")
    return {"kbs": kbs}


@router.get("/kbs/{kb_code}/documents")
async def kb_documents(
    kb_code: str,
    user: Annotated[dict, Depends(get_current_user)],
    kb_pool=Depends(get_kb_pool),
) -> dict:
    """某知识库下的文件列表（PG knowledge_base）。"""
    try:
        result = await list_documents_by_kb(kb_pool, kb_code)
    except Exception as exc:
        logger.exception("[request] knowledge docs unavailable: %s", exc)
        return _upstream_unavailable("knowledge_docs_unavailable", "知识库服务暂不可用")
    if result is None:
        raise HTTPException(status_code=404, detail="知识库不存在")
    return result


@router.get("/documents/{doc_id}/subgraph")
async def document_subgraph(
    doc_id: str,
    user: Annotated[dict, Depends(get_current_user)],
) -> dict:
    """某文档的「分块 → 实体」子图（Neo4j），前端点击文件时按需展开。"""
    try:
        driver = await get_driver()
        result = await fetch_document_subgraph(driver, doc_id)
    except Exception as exc:
        logger.exception("[request] knowledge graph unavailable: %s", exc)
        return _upstream_unavailable(
            "knowledge_graph_unavailable", "知识图谱服务暂不可用，请确认 Neo4j 已启动"
        )
    if result is None:
        raise HTTPException(status_code=404, detail="文档不存在")
    return result


@router.get("/documents/{doc_id}/content")
async def document_content(
    doc_id: str,
    user: Annotated[dict, Depends(get_current_user)],
    kb_pool=Depends(get_kb_pool),
) -> dict:
    """按 doc_id 聚合 chunk 还原文档 markdown 内容（PG knowledge_base）。"""
    try:
        result = await get_document_content(kb_pool, doc_id)
    except asyncpg.PostgresError as exc:
        logger.exception("[request] knowledge docs postgres error: %s", exc)
        return _upstream_unavailable("knowledge_docs_unavailable", "知识库服务暂不可用")
    except Exception as exc:
        logger.exception("[request] knowledge docs unavailable: %s", exc)
        return _upstream_unavailable("knowledge_docs_unavailable", "知识库服务暂不可用")
    if result is None:
        raise HTTPException(status_code=404, detail="文档不存在")
    return result