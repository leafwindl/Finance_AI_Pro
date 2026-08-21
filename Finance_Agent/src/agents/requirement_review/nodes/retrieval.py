"""步骤5: 多知识库并行检索 — 调用远程 KB REST API"""
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


def _format_results(label: str, results: list[dict[str, Any]]) -> str:
    parts = []
    for i, item in enumerate(results, 1):
        metadata = item.get("metadata") or {}
        source = metadata.get("title") or "未知来源"
        content = str(item.get("content") or "").strip()
        if content:
            parts.append(f"【{label} - {i}：{source}】\n{content}")
    return "\n\n".join(parts)


async def knowledge_retrieval(state: RequirementState) -> dict:
    base_url = os.environ.get("KB_BASE_URL", "").rstrip("/")
    if not base_url or "your-knowledge-base-host" in base_url:
        print("[警告] 未配置有效 KB_BASE_URL，使用空知识库上下文")
        return {"knowledge_context": "（知识库未配置，将基于通用知识评审）"}

    tasks: list[tuple[str, list[str], str]] = []
    for state_key, (label, kb_codes) in KB_ROUTES.items():
        query = str(state.get(state_key) or "").strip()
        if query:
            tasks.append((query, kb_codes, label))

    all_query = str(state.get("all_query") or "").strip()
    if all_query and not tasks:
        tasks.append((all_query, [], "全库综合搜索"))

    if not tasks:
        return {"knowledge_context": "（本轮未触发知识库检索）"}

    timeout = float(os.environ.get("KB_TIMEOUT_SECONDS", "30"))

    async def _search(query, kb_codes, label):
        try:
            async with httpx.AsyncClient(base_url=base_url, timeout=timeout) as client:
                resp = await client.post(
                    "/api/v1/search",
                    json={"query": query, "kb_codes": kb_codes or [], "top_k": 4},
                )
                resp.raise_for_status()
                return _format_results(label, resp.json().get("results") or [])
        except Exception as e:
            print(f"  [KB检索降级] {label}: {e}")
            return f"（知识库 {label} 暂不可用，将基于通用知识评审）"

    results = await asyncio.gather(*(
        _search(q, codes, label) for q, codes, label in tasks
    ), return_exceptions=True)
    results = [r if isinstance(r, str) else "（检索异常）" for r in results]

    context = "\n\n---\n\n".join(r for r in results if r)
    print(f"[知识检索] 完成，上下文长度: {len(context)} 字符")
    return {"knowledge_context": context or "（知识库无命中）"}
