"""
测试用例评审智能体 — LangGraph 8 节点线性流水线

拓扑:
  keyword → keyword_parse ─┬→ standard_retrieval ─┬→ retrieval_merge
                            ├→ spec_retrieval ──────┤        ↓
                            └→ history_retrieval ───┘  review_generate
                                                                  ↓
                                                                score → END
"""
from langgraph.graph import StateGraph, END
from .state import ReviewState
from .nodes.keyword import extract_keywords
from .nodes.keyword_parse import parse_keywords
from .nodes.retrieval import retrieve_standard, retrieve_spec, retrieve_history
from .nodes.merge import merge_retrieval
from .nodes.review import generate_review
from .nodes.score import calculate_coverage


def build_graph():
    workflow = StateGraph(ReviewState)

    # 注册 8 个节点
    workflow.add_node("keyword", extract_keywords)
    workflow.add_node("keyword_parse", parse_keywords)
    workflow.add_node("standard_retrieval", retrieve_standard)
    workflow.add_node("spec_retrieval", retrieve_spec)
    workflow.add_node("history_retrieval", retrieve_history)
    workflow.add_node("retrieval_merge", merge_retrieval)
    workflow.add_node("review_generate", generate_review)
    workflow.add_node("score", calculate_coverage)

    # 连线
    workflow.set_entry_point("keyword")
    workflow.add_edge("keyword", "keyword_parse")

    # 三路并行
    workflow.add_edge("keyword_parse", "standard_retrieval")
    workflow.add_edge("keyword_parse", "spec_retrieval")
    workflow.add_edge("keyword_parse", "history_retrieval")

    # 汇聚
    workflow.add_edge("standard_retrieval", "retrieval_merge")
    workflow.add_edge("spec_retrieval", "retrieval_merge")
    workflow.add_edge("history_retrieval", "retrieval_merge")

    # 评审 + 打分
    workflow.add_edge("retrieval_merge", "review_generate")
    workflow.add_edge("review_generate", "score")
    workflow.add_edge("score", END)

    return workflow.compile()
