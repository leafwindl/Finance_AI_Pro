"""步骤2: 关键词转换 — 将关键词映射为检索 query"""
from ..state import AgentState


def convert_keywords(state: AgentState) -> dict:
    biz = str(state.get("biz_keywords", "") or "").strip()
    test = str(state.get("test_keywords", "") or "").strip()
    regulatory = str(state.get("regulatory_keywords", "") or "").strip()

    has_any = bool(biz or test or regulatory)

    result = {
        "biz_query": biz if biz else None,
        "test_query": test if test else None,
        "stock_query": regulatory if regulatory else None,
        "all_query": None if has_any else (
            state.get("messages", [None])[-1].content if state.get("messages") else ""
        ),
    }

    print(f"[关键词转换] biz={bool(biz)}, test={bool(test)}, "
          f"stock={bool(regulatory)}, all={not has_any}")
    return result
