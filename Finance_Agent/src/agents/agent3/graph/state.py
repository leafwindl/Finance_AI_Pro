"""测试用例评审 Agent 全局状态定义"""
from typing import TypedDict, Dict, Any


class ReviewState(TypedDict, total=False):
    """
    评审工作流全局状态，对应 Dify 11 节点工作流。

    流水线：
      keyword ─┬→ standard_retrieval ─┬→ retrieval_merge
                                ├→ spec_retrieval ──────┤       ↓
                                └→ history_retrieval ────┘  review_generate
                                                                    ↓
                                                                  score → END
    """

    # ===== 用户输入 =====
    query: str

    # ===== 关键词提取 =====
    keywords: Dict[str, Any]         # 解析后的关键词（3 字段）

    # ===== 知识库检索结果 =====
    standard_context: str            # 标准测试用例库检索结果
    spec_context: str                # 测试规范库检索结果
    history_context: str             # 历史缺陷库检索结果

    # ===== 知识库汇总 =====
    retrieval_context: Dict[str, Any]  # 合并后的知识库结果

    # ===== LLM 评审结果 =====
    review_report: Dict[str, Any]    # 18 项检查清单 + summary

    # ===== 最终输出 =====
    report_text: str                 # Markdown 评审报告
    pass_flag: bool                  # 是否合格（≥80%）
    checklist: list                  # 18 项检查表明细（供 API 返回）
