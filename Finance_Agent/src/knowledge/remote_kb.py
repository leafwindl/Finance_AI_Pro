"""
远程 Finance_KnowledgeBase REST API 客户端。

使用方: ② requirement_review / ⑦ requirement_analysis / ⑬ test_step_generator
"""
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
    """调用远程知识库检索 API

    Args:
        query: 检索查询词
        kb_codes: 目标知识库代码列表，如 ["KB01", "KB03"]
        top_k: 返回结果数量

    Returns:
        [{"content": "...", "metadata": {...}}, ...]
    """
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
            print(f"  [KB远程检索降级为空] {kb_codes}: {exc}")
            return []
        raise RuntimeError(
            "knowledge_base_unavailable: 知识库检索失败"
        ) from exc
