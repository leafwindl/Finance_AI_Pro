"""
知识库路由节点

对应 Dify 节点: 1784776462620 (代码执行)
功能: 将 LLM 输出的关键词拆分到各知识库检索字段,
     如果 kb_code_list 为空则触发兜底全库检索。

这就是 Dify 中 Python 代码节点的 LangGraph 等价实现:

    def main(biz_keywords, test_keywords, regulatory_keywords,
             history_keywords, kb_code_list, origin_query) -> dict:
        has_routing = bool(kb_code_list and len(kb_code_list) > 0)
        if has_routing:
            return {
                "business_query": biz_keywords if "business_kb" in kb_code_list else None,
                "test_query": test_keywords if "test_quality_kb" in kb_code_list else None,
                "regulatory_query": regulatory_keywords if "regulatory_kb" in kb_code_list else None,
                "history_query": history_keywords if "history_kb" in kb_code_list else None,
                "all_query": None
            }
        else:
            return {
                "business_query": None,
                "test_query": None,
                "regulatory_query": None,
                "history_query": None,
                "all_query": origin_query  # 用原问题在所有库里检索
            }
"""

from ..state import RequirementState


def route_keywords_to_kb(state: RequirementState) -> dict:
    """
    根据关键词提取结果, 将查询词路由到对应的知识库。

    路由规则:
        - "business_kb" in kb_code_list        → 设置 business_query
        - "test_quality_kb" in kb_code_list    → 设置 test_query
        - "regulatory_kb" in kb_code_list      → 设置 regulatory_query
        - "history_kb" in kb_code_list         → 设置 history_query
        - kb_code_list 为空                    → 设置 all_query (兜底全库检索)

    Args:
        state: 包含关键词提取结果

    Returns:
        dict: 包含各知识库的查询词 (business_query, test_query, ...)
    """
    biz_keywords = state.get("biz_keywords", "") or ""
    test_keywords = state.get("test_keywords", "") or ""
    regulatory_keywords = state.get("regulatory_keywords", "") or ""
    history_keywords = state.get("history_keywords", "") or ""
    kb_code_list = state.get("kb_code_list", []) or []
    origin_query = state.get("requirement_input", state.get("user_input", ""))

    has_routing = bool(kb_code_list and len(kb_code_list) > 0)

    if has_routing:
        business_query = biz_keywords.strip() if "business_kb" in kb_code_list else None
        test_query = test_keywords.strip() if "test_quality_kb" in kb_code_list else None
        regulatory_query = regulatory_keywords.strip() if "regulatory_kb" in kb_code_list else None
        history_query = history_keywords.strip() if "history_kb" in kb_code_list else None
        all_query = None

        # 防御：kb_code_list 非空但四个 query 全为空（关键词为空 / LLM 返回未知代码值）时，
        # 回退用原始需求做全库检索，避免需求被静默丢弃（审计报告中严重度第 4 项）
        if not (business_query or test_query or regulatory_query or history_query):
            all_query = origin_query.strip() if origin_query else None
            print("[KB路由] [警告] 路由代码存在但四个查询均为空（关键词为空或代码值异常），回退兜底全库检索")

        print(f"[KB路由] 明确路由模式: kb_code_list={kb_code_list}")
    else:
        business_query = None
        test_query = None
        regulatory_query = None
        history_query = None
        all_query = origin_query.strip() if origin_query else None

        print(f"[KB路由] 兜底全库检索模式 (kb_code_list 为空)")

    print(
        "[KB路由] 查询启用状态: "
        f"business={bool(business_query)}, test={bool(test_query)}, "
        f"regulatory={bool(regulatory_query)}, history={bool(history_query)}, "
        f"all={bool(all_query)}"
    )

    return {
        "business_query": business_query,
        "test_query": test_query,
        "regulatory_query": regulatory_query,
        "history_query": history_query,
        "all_query": all_query,
    }
