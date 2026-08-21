"""
共享状态 — LangGraph AgentState
"""

from typing import Annotated, Sequence, TypedDict
from langchain_core.documents import Document
from langchain_core.messages import AnyMessage
from langgraph.graph import add_messages


class InputState(TypedDict):
    messages: Annotated[Sequence[AnyMessage], add_messages]


class AgentState(InputState, total=False):
    # ---- 步骤2: LLM 关键词提取 ----
    biz_keywords: str             # 业务类关键词，如开户、转账
    test_keywords: str            # 测试类关键词，如Bug、边界值
    regulatory_keywords: str      # 法规类关键词，如创业板、风控

    # ---- 步骤3: 关键词转换 ----
    biz_query: str | None         # 业务检索查询词
    test_query: str | None        # 测试检索查询词
    stock_query: str | None       # 法规检索查询词
    all_query: str | None         # 兜底查询词（无关键词时 = 原问题）

    # ---- 步骤6: 三路并行检索结果 ----
    biz_result: list[Document]           # 业务库（KB01 + KB03）
    test_practice_result: list[Document] # 测试实操库（KB04 + KB05）
    test_standard_result: list[Document] # 测试制度库（KB06）
    regulatory_result: list[Document]    # 创业板法规库（KB02）

    # ---- 聚合后统一上下文 ----
    aggregated_context: str       # 四个库的检索结果拼接文本
