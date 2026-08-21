"""
需求分析智能体 — 共享状态
"""
from typing import Annotated, Sequence, TypedDict
from langchain_core.documents import Document
from langchain_core.messages import AnyMessage
from langgraph.graph import add_messages


class InputState(TypedDict):
    messages: Annotated[Sequence[AnyMessage], add_messages]


class AgentState(InputState, total=False):
    # ---- 关键词提取 ----
    biz_keywords: str
    test_keywords: str
    regulatory_keywords: str
    kb_code_list: list[str]

    # ---- 关键词转换 ----
    biz_query: str | None
    test_query: str | None
    stock_query: str | None
    all_query: str | None

    # ---- 三路并行检索结果 ----
    biz_result: list[Document]
    test_practice_result: list[Document]
    test_standard_result: list[Document]
    regulatory_result: list[Document]

    # ---- 聚合上下文 ----
    aggregated_context: str
