"""
需求分析智能体 — LangGraph 图编排 (5 节点 × 1 条件路由)

拓扑:
  START → extract_keywords → convert_keywords
    ├─ 无关键词 → chat_response → END
    └─ 有关键词 → retrieve_all → rag_response → END
"""
from langgraph.graph import StateGraph
from .state import AgentState, InputState
from .nodes.keyword import extract_keywords
from .nodes.converter import convert_keywords
from .nodes.retriever import retrieve_all
from .nodes.llm_handler import rag_response, chat_response


def _route_after_convert(state: AgentState) -> str:
    """all_query 不为 None 表示无关键词 → 闲聊"""
    return "chat" if state.get("all_query") is not None else "retrieve"


_builder = StateGraph(AgentState, input_schema=InputState)

_builder.add_node("extract_keywords", extract_keywords)
_builder.add_node("convert_keywords", convert_keywords)
_builder.add_node("retrieve_all", retrieve_all)
_builder.add_node("rag_response", rag_response)
_builder.add_node("chat_response", chat_response)

_builder.add_edge("__start__", "extract_keywords")
_builder.add_edge("extract_keywords", "convert_keywords")
_builder.add_conditional_edges(
    "convert_keywords", _route_after_convert,
    {"chat": "chat_response", "retrieve": "retrieve_all"},
)
_builder.add_edge("retrieve_all", "rag_response")
_builder.add_edge("rag_response", "__end__")
_builder.add_edge("chat_response", "__end__")

agent_graph = _builder.compile()
agent_graph.name = "RequirementAnalysisAgent"
