"""
图编排 — 新流程（基于说明文档 v2）

流程:
    用户输入
        │
        ▼
    extract_keywords   ← LLM: 提取 biz/test/regulatory 关键词
        │
        ▼
    convert_keywords   ← Python: structured_output → biz/test/stock/all_query
        │
        ▼
    route: all_query 不为空?
        │
        ├── YES → chat_response  ← 闲聊（无关键词，直接输出）→ END
        │
        └── NO  → retrieve_all   ← 三路并行检索（按 kb_code 分库）
                      │                 biz → KB01+KB03
                      │                 test → KB04+KB05 | KB06
                      │                 stock → KB02
                      ▼
                  rag_response   ← LLM: 聚合上下文 → 六维分析报告 → END
"""

from langgraph.graph import StateGraph

from ..handlers.keyword_extractor import default_extractor
from ..handlers.keyword_converter import convert_keywords
from ..handlers.retriever import default_retriever
from ..handlers.llm_handler import default_llm
from .state import AgentState, InputState


# ---- 路由函数 ----
def _route_after_convert(state: AgentState) -> str:
    """all_query 不为空 → 闲聊，否则 → 检索。"""
    return "chat" if state.get("all_query") else "retrieve"


# ---- 构建图 ----
_builder = StateGraph(AgentState, input_schema=InputState)

# 注册节点
_builder.add_node("extract_keywords", default_extractor.extract)
_builder.add_node("convert_keywords", convert_keywords)
_builder.add_node("retrieve_all", default_retriever.retrieve_all)
_builder.add_node("rag_response", default_llm.rag_response)
_builder.add_node("chat_response", default_llm.chat_response)

# 连接边
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
agent_graph.name = "HybridRetrievalAgent"
