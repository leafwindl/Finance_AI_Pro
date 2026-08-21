"""
需求评审智能体 — 全局状态定义
"""
from typing import TypedDict, Annotated, Sequence, Optional
from langgraph.graph.message import add_messages
from langchain_core.messages import BaseMessage


class RequirementState(TypedDict, total=False):

    # ... (字段定义省略，见上文) ...

    # ---- 对话系统 ----
    messages: Annotated[Sequence[BaseMessage], add_messages]

    # ---- 用户输入 ----
    user_input: str
    file_content: str
    file_name: str

    # ---- 分类与路由 (步骤1) ----
    is_business: bool
    recognized_intent: str          # CONFIRM / MODIFY / CLARIFY

    # ---- 关键词提取 (步骤2) ----
    biz_keywords: str
    test_keywords: str
    regulatory_keywords: str
    history_keywords: str
    kb_code_list: list

    # ---- 知识库路由查询 (步骤3) ----
    business_query: str
    test_query: str
    regulatory_query: str
    history_query: str
    all_query: str

    # ---- 知识检索 (步骤4) ----
    knowledge_context: str

    # ---- 需求提取 (步骤5) ----
    extracted_dimensions: dict       # {background, objective, system, scenario, acceptance, priority}
    is_complete: bool

    # ---- 风险评估 ----
    risk_detected: bool
    risk_details: str

    # ---- 累积信息 (跨轮次) ----
    collected_info: list
    waiting_confirmation: bool

    # ---- 输出 ----
    clarification_question: str
    confirmation_summary: str
    generated_spec: str
    modifications: list
    final_output: str


# ============================================================
# 工具函数: 多轮收集信息的合并
# ============================================================

def merge_collected_info(collected_info: list) -> dict:
    """
    将多轮收集的需求信息合并为最新完整视图。
    规则: 后面的非 null 值覆盖前面的。
    """
    merged = {
        "background": None,
        "objective": None,
        "system": None,
        "scenario": None,
        "acceptance": None,
        "priority": None,
    }
    for info in (collected_info or []):
        for key in merged:
            if info.get(key) is not None:
                merged[key] = info[key]
    return merged


def get_missing_dimensions(merged_info: dict) -> list[str]:
    """返回当前仍未收集到的维度名称列表。"""
    dimension_labels = {
        "background": "业务背景/痛点",
        "objective": "需求目标",
        "system": "涉及系统/模块",
        "scenario": "业务场景",
        "acceptance": "验收标准",
        "priority": "优先级/时间要求",
    }
    return [
        dimension_labels[k]
        for k, v in merged_info.items()
        if v is None
    ]
