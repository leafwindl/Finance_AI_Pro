"""
需求预评审智能体 - 状态定义 (流水线版本)

重构说明:
    从"多轮对话式需求澄清"改为"自动化需求预评审报告生成"。
    删除了所有对话相关字段 (messages, conversation_history, chat_state,
    waiting_confirmation, recognized_intent 等)，
    改为纯流水线 State：输入 → 解析 → 六大要点 → 知识检索 → 风险评估 → 报告。

LangGraph 的 State 是图中所有节点共享的"黑板",
每个节点返回 dict 即可部分更新 State。
"""

from typing import TypedDict, Optional


class RequirementState(TypedDict, total=False):
    """
    需求预评审智能体的全局状态 (流水线版本)

    ========== 输入字段 ==========
    requirement_input:
        用户一次性输入的完整需求描述文本
    file_content:
        用户上传文件提取的文本内容
    file_name:
        用户上传文件的原始文件名

    ========== 需求解析字段 ==========
    requirement_analysis:
        需求结构化分析结果 (dict), 包含:
        {
            "summary": str,              # 需求概要
            "business_context": str,     # 业务上下文
            "functional_scope": str,     # 功能范围
            "affected_systems": list,    # 涉及系统
            "constraints": list,         # 约束条件
            "completeness_score": float, # 信息完整度 0-100
            "missing_info": list,        # 缺失信息列表
        }

    ========== 六大要点评估字段 ==========
    six_points:
        自动生成的六大要点评估结果 (dict):
        {
            "background": str,           # 1. 需求背景
            "business_objective": str,   # 2. 业务目标
            "user_scope": str,           # 3. 用户范围
            "functional_requirements": str, # 4. 功能需求
            "non_functional_requirements": str, # 5. 非功能需求
            "implementation_impact": str,    # 6. 实施影响分析
            "completeness_score": float,     # 六大要点综合完整度 0-100
            "missing_items": list,           # 缺失项标记
        }

    ========== 知识检索字段 (保留原有架构) ==========
    # 关键词提取
    biz_keywords: str
    test_keywords: str
    regulatory_keywords: str
    history_keywords: str
    kb_code_list: list

    # 知识库路由查询
    business_query: str
    test_query: str
    regulatory_query: str
    history_query: str
    all_query: str

    # 知识检索结果
    knowledge_context: str

    ========== 风险评估字段 ==========
    risk_analysis:
        风险评估结果 (dict):
        {
            "tech_risks": list,          # 技术风险
            "business_risks": list,      # 业务风险
            "compliance_risks": list,    # 合规风险
            "data_risks": list,          # 数据风险
            "overall_risk_level": str,   # 综合风险等级: 高/中/低
            "risk_details": str,         # 风险详细描述
            "mitigation_suggestions": list, # 缓解建议
        }

    ========== 输出字段 ==========
    final_report:
        最终生成的完整预评审报告 (Markdown 格式)
    final_output:
        最终返回给调用方的消息内容 (与 final_report 一致)
    """

    # ---- 输入 ----
    requirement_input: str
    file_content: str
    file_name: str

    # ---- 需求解析 ----
    requirement_analysis: dict

    # ---- 六大要点 ----
    six_points: dict

    # ---- 知识检索 ----
    biz_keywords: str
    test_keywords: str
    regulatory_keywords: str
    history_keywords: str
    kb_code_list: list
    business_query: str
    test_query: str
    regulatory_query: str
    history_query: str
    all_query: str
    knowledge_context: str

    # ---- 风险评估 ----
    risk_analysis: dict

    # ---- 输出 ----
    final_report: str
    final_output: str


# ============================================================
# 工具函数: 信息完整度辅助
# ============================================================

def calculate_completeness(six_points: dict) -> tuple[float, list[str]]:
    """
    计算六大要点的完整度评分。

    规则:
        - 每个要点有内容、非 empty → +16.67 分 (100/6)
        - 内容明显是推断/猜测 → 标记为"信息缺失"
        - 完全无内容 → 标记为"严重缺失"

    Args:
        six_points: 六大要点 dict

    Returns:
        (completeness_score, missing_items): 完整度评分及缺失项列表
    """
    keys = [
        "background",
        "business_objective",
        "user_scope",
        "functional_requirements",
        "non_functional_requirements",
        "implementation_impact",
    ]
    labels = {
        "background": "需求背景",
        "business_objective": "业务目标",
        "user_scope": "用户范围",
        "functional_requirements": "功能需求",
        "non_functional_requirements": "非功能需求",
        "implementation_impact": "实施影响分析",
    }

    missing = []
    filled = 0

    for key in keys:
        value = (six_points or {}).get(key, "")
        if value and len(str(value).strip()) > 10:
            filled += 1
        else:
            missing.append(labels.get(key, key))

    score = round((filled / len(keys)) * 100, 1)
    return score, missing
