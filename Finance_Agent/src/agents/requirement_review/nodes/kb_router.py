"""步骤4: 知识库路由 — 将关键词分配到对应知识库生成检索 query"""
from ..state import RequirementState


def route_keywords_to_kb(state: RequirementState) -> dict:
    kb_code_list = state.get("kb_code_list", [])
    biz_keywords = state.get("biz_keywords", "")
    test_keywords = state.get("test_keywords", "")
    regulatory_keywords = state.get("regulatory_keywords", "")
    history_keywords = state.get("history_keywords", "")

    result = {
        "business_query": biz_keywords if "business_kb" in kb_code_list else "",
        "test_query": test_keywords if "test_quality_kb" in kb_code_list else "",
        "regulatory_query": regulatory_keywords if "regulatory_kb" in kb_code_list else "",
        "history_query": history_keywords if "history_kb" in kb_code_list else "",
    }

    has_any = any(v for v in result.values())
    result["all_query"] = "" if has_any else state.get("user_input", "")

    print(f"[知识库路由] business={bool(result['business_query'])}, "
          f"test={bool(result['test_query'])}, "
          f"regulatory={bool(result['regulatory_query'])}, "
          f"history={bool(result['history_query'])}, "
          f"all={bool(result['all_query'])}")
    return result
