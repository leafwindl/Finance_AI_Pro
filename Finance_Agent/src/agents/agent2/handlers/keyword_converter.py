"""
关键词转换 — 把 LLM 结构化输出拆成四个检索查询变量

步骤3，纯 Python 函数，不涉及 LLM。
"""

from langchain_core.runnables import RunnableConfig

from ..core.state import AgentState


async def convert_keywords(
    state: AgentState, *, config: RunnableConfig
) -> dict:
    """解析结构化输出，拆分关键词以驱动不同知识库的检索。

    含兜底策略：只有当所有特定领域都未命中时，才启用全库检索（all_query）。
    """
    # 安全提取并清洗关键词
    biz_kw = (state.get("biz_keywords") or "").strip()
    test_kw = (state.get("test_keywords") or "").strip()
    stock_kw = (state.get("regulatory_keywords") or "").strip()

    # 判断是否有明确意图
    has_specific_intent = bool(biz_kw or test_kw or stock_kw)

    # 提取原始 query
    from langchain_core.messages import HumanMessage

    msgs = state.get("messages", [])
    user_msgs = [m for m in msgs if isinstance(m, HumanMessage)]
    origin_query = ""
    if user_msgs:
        content = user_msgs[-1].content
        origin_query = content if isinstance(content, str) else str(content)

    # 兜底：无明确意图 → 用原问题走闲聊
    all_query = origin_query.strip() if not has_specific_intent else None

    return {
        "biz_query": biz_kw or None,
        "test_query": test_kw or None,
        "stock_query": stock_kw or None,
        "all_query": all_query,
    }
