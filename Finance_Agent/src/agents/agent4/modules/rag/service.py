"""Finance KnowledgeBase 检索客户端。"""

from __future__ import annotations

import os
from typing import Any

import httpx
from dotenv import load_dotenv

load_dotenv()


async def search_knowledge_base(
    query: str,
    kb_codes: list[str],
    top_k: int = 6,
) -> list[dict[str, Any]]:
    base_url = os.environ.get("KB_BASE_URL", "").rstrip("/")
    if not base_url:
        raise RuntimeError("knowledge_base_unavailable: 未配置 KB_BASE_URL")

    timeout = float(os.environ.get("KB_TIMEOUT_SECONDS", "30"))
    try:
        async with httpx.AsyncClient(base_url=base_url, timeout=timeout) as client:
            response = await client.post(
                "/api/v1/search",
                json={"query": query, "kb_codes": kb_codes, "top_k": top_k},
            )
            response.raise_for_status()
            return response.json().get("results") or []
    except (httpx.HTTPError, ValueError) as exc:
        if os.environ.get("ALLOW_LOCAL_KB_FALLBACK", "false").lower() == "true":
            return []
        raise RuntimeError("knowledge_base_unavailable: 知识库检索失败") from exc
