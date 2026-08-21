"""LangGraph 工作流构建器 — 真并行三维检索"""
from langgraph.graph import StateGraph, END

from .state import ReviewState

from ..nodes.keyword import extract_keywords
from ..nodes.retrieval import retrieve_standard, retrieve_spec, retrieve_history
from ..nodes.retrieval_merge import merge_retrieval
from ..nodes.review import generate_review
from ..nodes.score import calculate_coverage


def build_graph():
    """
    构建并编译 LangGraph 工作流。

    拓扑（真并行检索）：
      keyword ─┬→ standard_retrieval ─┬→ retrieval_merge
               ├→ spec_retrieval ──────┤       ↓
               └→ history_retrieval ────┘  review_generate
                                                  ↓
                                                score → END
    """
    workflow = StateGraph(ReviewState)

    # ---- 注册 7 个节点（keyword_parse 已合并进 keyword，确定性函数无需二次解析）----
    workflow.add_node("keyword", extract_keywords)
    workflow.add_node("standard_retrieval", retrieve_standard)
    workflow.add_node("spec_retrieval", retrieve_spec)
    workflow.add_node("history_retrieval", retrieve_history)
    workflow.add_node("retrieval_merge", merge_retrieval)
    workflow.add_node("review_generate", generate_review)
    workflow.add_node("score", calculate_coverage)

    # ---- 连线 ----
    workflow.set_entry_point("keyword")

    # 三路知识库并行检索
    workflow.add_edge("keyword", "standard_retrieval")
    workflow.add_edge("keyword", "spec_retrieval")
    workflow.add_edge("keyword", "history_retrieval")

    # 汇聚
    workflow.add_edge("standard_retrieval", "retrieval_merge")
    workflow.add_edge("spec_retrieval", "retrieval_merge")
    workflow.add_edge("history_retrieval", "retrieval_merge")

    # 评审
    workflow.add_edge("retrieval_merge", "review_generate")

    # 评分
    workflow.add_edge("review_generate", "score")
    workflow.add_edge("score", END)

    return workflow.compile()
