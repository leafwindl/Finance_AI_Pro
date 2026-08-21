"""统一知识库检索节点。

把业务路由转换为 KB01～KB06，并调用 Finance_KnowledgeBase 的
``POST /api/v1/search``。生产环境不再返回硬编码占位知识。
"""

from __future__ import annotations

import asyncio
import os
from typing import Any

import httpx

from ..state import RequirementState


KB_ROUTES: dict[str, tuple[str, list[str]]] = {
    "business_query": ("系统业务与历史需求", ["KB01", "KB03"]),
    "test_query": ("测试用例与测试规范", ["KB04", "KB06"]),
    "regulatory_query": ("法规与合规规则", ["KB02"]),
    "history_query": ("历史需求与缺陷经验", ["KB03", "KB05"]),
}


def _kb_base_url() -> str:
    return os.environ.get("KB_BASE_URL", "").rstrip("/")


def _format_results(label: str, results: list[dict[str, Any]]) -> str:
    parts = []
    for index, item in enumerate(results, 1):
        if not isinstance(item, dict):
            continue  # 非 dict 项跳过，避免 AttributeError
        metadata = item.get("metadata") or {}
        source = metadata.get("title") or metadata.get("heading") or "未知来源"
        content = str(item.get("content") or "").strip()
        if content:
            parts.append(f"【{label} - 来源 {index}：{source}】\n{content}")
    return "\n\n".join(parts)


async def _search(
    client: httpx.AsyncClient,
    *,
    query: str,
    kb_codes: list[str],
    label: str,
    top_k: int = 4,
) -> str:
    response = await client.post(
        "/api/v1/search",
        json={"query": query, "kb_codes": kb_codes, "top_k": top_k},
    )
    response.raise_for_status()
    payload = response.json()
    return _format_results(label, payload.get("results") or [])


async def knowledge_retrieval(state: RequirementState) -> dict:
    """
    多知识库并行检索节点。

    当 KB_BASE_URL 未配置或知识库不可用时，降级返回空上下文，
    不阻塞流水线继续执行。后续节点会在报告中标注"知识库不可用"。
    """
    import logging
    logger = logging.getLogger(__name__)

    base_url = _kb_base_url()
    if not base_url:
        logger.warning("[知识检索] KB_BASE_URL 未配置, 跳过知识库检索")
        return {
            "knowledge_context": "（知识库未配置，跳过检索。请配置 KB_BASE_URL 环境变量以启用知识库检索。）"
        }

    tasks: list[tuple[str, list[str], str]] = []
    for state_key, (label, kb_codes) in KB_ROUTES.items():
        query = str(state.get(state_key) or "").strip()
        if query:
            tasks.append((query, kb_codes, label))

    all_query = str(state.get("all_query") or "").strip()
    if all_query:
        tasks.append((all_query, [], "全库综合搜索"))

    if not tasks:
        return {"knowledge_context": "（本轮未触发知识库检索）"}

    timeout = float(os.environ.get("KB_TIMEOUT_SECONDS", "30"))
    try:
        async with httpx.AsyncClient(base_url=base_url, timeout=timeout) as client:
            results = await asyncio.gather(
                *(
                    _search(
                        client,
                        query=query,
                        kb_codes=kb_codes,
                        label=label,
                    )
                    for query, kb_codes, label in tasks
                ),
                return_exceptions=True,  # 单个任务异常不影响其他并行任务
            )
    except Exception as exc:
        logger.warning("[知识检索] 知识库检索失败, 降级继续: %s", exc)
        return {
            "knowledge_context": "（知识库检索暂时不可用，本次评审未包含知识库关联案例。请检查知识库服务状态。）"
        }

    # 过滤异常结果（return_exceptions=True 时异常会作为结果返回）
    valid = [
        result for result in results
        if isinstance(result, str) and result
    ]
    context = "\n\n---\n\n".join(valid)
    return {"knowledge_context": context or "（知识库无相关命中）"}
