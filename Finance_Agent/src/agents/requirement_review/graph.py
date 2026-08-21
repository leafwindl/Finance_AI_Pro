"""
需求评审智能体 — LangGraph 图编排 (12 节点 × 3 条件路由)

拓扑:
  START → classify → [业务?]
    ├─ Yes → keyword → kb_router → retrieval → extract → append
    │         ├─ 不完整 → clarification → END
    │         ├─ 完整未确认 → confirmation → END
    │         └─ 完整已确认 → intent → [CONFIRM/MODIFY/CLARIFY]
    │              ├─ MODIFY → modification → reconfirmation → END
    │              ├─ CLARIFY → set_confirmation → END
    │              └─ CONFIRM → generate_spec → END
    └─ No → boundary → END
"""
from langgraph.graph import StateGraph, START, END
from .state import RequirementState, merge_collected_info
from .nodes import (
    classify_question,
    boundary_reply,
    extract_keywords,
    route_keywords_to_kb,
    knowledge_retrieval,
    extract_info,
    append_to_collected_info,
    generate_confirmation,
    generate_reconfirmation,
    recognize_intent,
    extract_modifications,
    generate_spec,
    set_clarification_output,
    set_confirmation_output,
)


# ============================================================
# 路由函数
# ============================================================
def route_after_classify(state: RequirementState) -> str:
    return "keyword_extractor" if state.get("is_business", True) else "boundary_reply"


def route_after_extraction(state: RequirementState) -> str:
    is_complete = state.get("is_complete", False)
    waiting = state.get("waiting_confirmation", False)
    if not is_complete:
        return "end__incomplete"
    elif not waiting:
        return "generate_confirmation"
    else:
        return "recognize_intent"


def route_after_intent(state: RequirementState) -> str:
    intent = state.get("recognized_intent", "CLARIFY")
    if intent == "MODIFY":
        return "extract_modifications"
    elif intent == "CONFIRM":
        return "generate_spec"
    return "set_confirmation_output"


# ============================================================
# 构建图
# ============================================================
def build_graph(checkpointer=None):
    graph = StateGraph(RequirementState)

    # 注册 12 个节点
    graph.add_node("classify_question", classify_question)
    graph.add_node("boundary_reply", boundary_reply)
    graph.add_node("keyword_extractor", extract_keywords)
    graph.add_node("kb_router", route_keywords_to_kb)
    graph.add_node("knowledge_retrieval", knowledge_retrieval)
    graph.add_node("extract_info", extract_info)
    graph.add_node("append_collected", append_to_collected_info)
    graph.add_node("set_clarification_output", set_clarification_output)
    graph.add_node("generate_confirmation", generate_confirmation)
    graph.add_node("recognize_intent", recognize_intent)
    graph.add_node("extract_modifications", extract_modifications)
    graph.add_node("generate_reconfirmation", generate_reconfirmation)
    graph.add_node("generate_spec", generate_spec)
    graph.add_node("set_confirmation_output", set_confirmation_output)

    # 连线
    graph.add_edge(START, "classify_question")
    graph.add_conditional_edges(
        "classify_question", route_after_classify,
        {"keyword_extractor": "keyword_extractor", "boundary_reply": "boundary_reply"},
    )
    graph.add_edge("boundary_reply", END)

    graph.add_edge("keyword_extractor", "kb_router")
    graph.add_edge("kb_router", "knowledge_retrieval")
    graph.add_edge("knowledge_retrieval", "extract_info")
    graph.add_edge("extract_info", "append_collected")

    graph.add_conditional_edges(
        "append_collected", route_after_extraction,
        {
            "end__incomplete": "set_clarification_output",
            "generate_confirmation": "generate_confirmation",
            "recognize_intent": "recognize_intent",
        },
    )
    graph.add_edge("set_clarification_output", END)
    graph.add_edge("generate_confirmation", END)

    graph.add_conditional_edges(
        "recognize_intent", route_after_intent,
        {
            "extract_modifications": "extract_modifications",
            "generate_spec": "generate_spec",
            "set_confirmation_output": "set_confirmation_output",
        },
    )
    graph.add_edge("set_confirmation_output", END)
    graph.add_edge("extract_modifications", "generate_reconfirmation")
    graph.add_edge("generate_reconfirmation", END)
    graph.add_edge("generate_spec", END)

    return graph.compile(checkpointer=checkpointer)


app = build_graph()
