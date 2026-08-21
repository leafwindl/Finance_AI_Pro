"""
测试用例评审智能体 — 全局状态定义
"""
from typing import TypedDict, Dict, Any


class ReviewState(TypedDict, total=False):
    # ===== 用户输入 =====
    query: str

    # ===== 关键词提取 =====
    keyword_raw: str
    keywords: Dict[str, Any]

    # ===== 知识库检索结果 =====
    standard_context: str
    spec_context: str
    history_context: str

    # ===== 知识库汇总 =====
    retrieval_context: Dict[str, Any]

    # ===== LLM 评审结果 =====
    review_report: Dict[str, Any]

    # ===== 最终输出 =====
    report_text: str
    pass_flag: bool
    checklist: list
