"""
测试步骤生成智能体 — LangGraph 图编排 (v2: 8 节点 × 1 条件分支)

拓扑:
  START → extract_keyword → kb_route → knowledge_retrieve
    → llm_gen_json → json_parse → [成功?]
        ├─ Yes → gen_markdown → END
        └─ No  → gen_error → END
"""
from langgraph.graph import StateGraph, START, END
from .state import WorkflowState
from .nodes.keyword import extract_keyword_node
from .nodes.kb_route import kb_route_node
from .nodes.retrieval import knowledge_retrieve_node
from .nodes.json_gen import llm_gen_json_node
from .nodes.json_parse import json_to_python_node
from .nodes.reply import gen_markdown_node, gen_error_node


def route_after_parse(state: WorkflowState) -> str:
    return "gen_markdown_node" if state.get("is_success") == 1 else "gen_error_node"


def build_workflow_graph():
    graph_builder = StateGraph(WorkflowState)

    graph_builder.add_node("extract_keyword_node", extract_keyword_node)
    graph_builder.add_node("kb_route_node", kb_route_node)
    graph_builder.add_node("knowledge_retrieve_node", knowledge_retrieve_node)
    graph_builder.add_node("llm_gen_json_node", llm_gen_json_node)
    graph_builder.add_node("json_to_python_node", json_to_python_node)
    graph_builder.add_node("gen_markdown_node", gen_markdown_node)
    graph_builder.add_node("gen_error_node", gen_error_node)

    graph_builder.add_edge(START, "extract_keyword_node")
    graph_builder.add_edge("extract_keyword_node", "kb_route_node")
    graph_builder.add_edge("kb_route_node", "knowledge_retrieve_node")
    graph_builder.add_edge("knowledge_retrieve_node", "llm_gen_json_node")
    graph_builder.add_edge("llm_gen_json_node", "json_to_python_node")

    graph_builder.add_conditional_edges(
        "json_to_python_node", route_after_parse,
        {"gen_markdown_node": "gen_markdown_node",
         "gen_error_node": "gen_error_node"},
    )
    graph_builder.add_edge("gen_markdown_node", END)
    graph_builder.add_edge("gen_error_node", END)

    return graph_builder.compile()
