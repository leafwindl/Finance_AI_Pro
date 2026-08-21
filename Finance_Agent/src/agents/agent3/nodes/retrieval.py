"""步骤3-5：通过统一 KnowledgeBase API 并行检索三类知识。"""

import os
from typing import Any, Dict

import httpx

from ..graph.state import ReviewState


async def _search(query: str, kb_code: str) -> str:
    if not query or not query.strip():
        return "（未提供检索关键词）"
    base_url = os.getenv("KB_BASE_URL", "").rstrip("/")
    if not base_url:
        return "（知识库未配置）"
    try:
        async with httpx.AsyncClient(
            base_url=base_url,
            timeout=float(os.getenv("KB_TIMEOUT_SECONDS", "30")),
        ) as client:
            response = await client.post(
                "/api/v1/search",
                json={"query": query, "kb_codes": [kb_code], "top_k": 6, "expand_k": 0},
            )
            response.raise_for_status()
        hits = response.json().get("results") or []
        if not hits:
            return "（知识库未检索到相关内容）"
        return "\n\n".join(str(hit.get("content") or "") for hit in hits if hit.get("content"))
    except (httpx.HTTPError, ValueError) as exc:
        return f"（检索失败: {exc}）"


async def retrieve_standard(state: ReviewState) -> Dict[str, Any]:
    query = state.get("keywords", {}).get("standard_cases_query", "")
    return {"standard_context": await _search(query, "KB04")}  # KB04 标准测试用例库


async def retrieve_spec(state: ReviewState) -> Dict[str, Any]:
    query = state.get("keywords", {}).get("test_spec_query", "")
    return {"spec_context": await _search(query, "KB06")}  # KB06 测试规范与模板库


async def retrieve_history(state: ReviewState) -> Dict[str, Any]:
    query = state.get("keywords", {}).get("history_defects_query", "")
    return {"history_context": await _search(query, "KB05")}  # KB05 历史缺陷与测试经验库
