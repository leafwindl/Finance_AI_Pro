"""步骤3-5: 三路并行检索 — 远程KB + 本地混合检索降级"""
import os
import asyncio
from ..state import AgentState
from src.knowledge.remote_kb import search_knowledge_base


async def _remote_search(query: str | None, kb_codes: list[str]) -> list:
    if not query:
        return []
    try:
        results = await search_knowledge_base(query, kb_codes)
    except Exception as exc:
        print(f"  [KB检索降级] {kb_codes}: {exc}")
        return []  # 默认降级：返回空，不抛异常
    return results


async def retrieve_all(state: AgentState) -> dict:
    biz_query = state.get("biz_query")
    test_query = state.get("test_query")
    stock_query = state.get("stock_query")

    # 三路并行
    biz_result, test_practice_result, test_standard_result, regulatory_result = \
        await asyncio.gather(
            _remote_search(biz_query, ["KB01", "KB03"]),
            _remote_search(test_query, ["KB05", "KB04"]),
            _remote_search(test_query, ["KB06"]),
            _remote_search(stock_query, ["KB02"]),
        )

    # 聚合
    parts = []
    for label, docs in [
        ("业务库", biz_result),
        ("创业板法规", regulatory_result),
        ("测试实操库", test_practice_result),
        ("测试制度库", test_standard_result),
    ]:
        if docs:
            parts.append(f"## {label}\n" + "\n\n".join(
                f"[{d.get('metadata', {}).get('title', '?')}]\n{d.get('content', '')}"
                for d in docs
            ))

    aggregated = "\n\n---\n\n".join(parts)
    print(f"[检索] 聚合上下文: {len(aggregated)} 字符")

    return {
        "biz_result": biz_result,
        "test_practice_result": test_practice_result,
        "test_standard_result": test_standard_result,
        "regulatory_result": regulatory_result,
        "aggregated_context": aggregated,
    }
