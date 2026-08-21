"""
风险评估节点 (Risk Assessment)

流水线第5步: 基于需求分析结果和知识库检索结果，进行全面的风险评估。

功能:
    1. 读取六大要点评估 + 知识库检索结果
    2. 进行四维度风险评估 (技术/业务/合规/数据)
    3. 引用知识库来源佐证
    4. 输出综合风险等级和缓解建议

四维度:
    1. 技术风险 (tech_risks)
    2. 业务风险 (business_risks)
    3. 合规风险 (compliance_risks)
    4. 数据风险 (data_risks)

结构化输出 Schema:
    {
      "tech_risks": [{"risk": str, "severity": str, "source": str, "mitigation": str}],
      "business_risks": [...],
      "compliance_risks": [...],
      "data_risks": [...],
      "overall_risk_level": "高/中/低",
      "risk_summary": str,
      "key_concerns": [str]
    }
"""

from typing import Optional
from pydantic import BaseModel, Field
from ..state import RequirementState
from .llm_config import llm
from ..prompts import RISK_ASSESSMENT_SYSTEM_PROMPT


# ================================================================
# Pydantic 模型: 风险评估的结构化输出 Schema
# ================================================================

class RiskItem(BaseModel):
    """单个风险项"""
    risk: str = Field(description="风险描述")
    severity: str = Field(description="风险严重程度: 高/中/低")
    source: str = Field(description="风险判断依据来源（引用知识库或推断）")
    mitigation: str = Field(description="风险缓解建议")


class RiskAssessmentResult(BaseModel):
    """风险评估的完整输出"""
    tech_risks: list[RiskItem] = Field(
        default_factory=list,
        description="技术风险列表"
    )
    business_risks: list[RiskItem] = Field(
        default_factory=list,
        description="业务风险列表"
    )
    compliance_risks: list[RiskItem] = Field(
        default_factory=list,
        description="合规风险列表"
    )
    data_risks: list[RiskItem] = Field(
        default_factory=list,
        description="数据风险列表"
    )
    overall_risk_level: str = Field(
        description="综合风险等级: 高/中/低"
    )
    risk_summary: str = Field(
        description="综合风险评估总结，概述主要发现"
    )
    key_concerns: list[str] = Field(
        default_factory=list,
        description="需要重点关注的事项列表"
    )


# ================================================================
# 风险评估节点
# ================================================================

def risk_assessment(state: RequirementState) -> dict:
    """
    风险评估节点: 基于需求分析和知识库检索结果进行全面风险评估。

    这是流水线的核心风险分析节点，负责:
        1. 分析技术实现风险
        2. 分析业务影响风险
        3. 分析合规监管风险
        4. 分析数据安全风险
        5. 引用知识库来源佐证
        6. 给出综合风险等级和缓解建议

    Args:
        state: 包含 requirement_analysis, six_points, knowledge_context

    Returns:
        dict: 包含 risk_analysis
    """
    requirement_analysis = state.get("requirement_analysis", {})
    six_points = state.get("six_points", {})
    knowledge_context = state.get("knowledge_context", "")

    # 格式化输入数据
    import json

    analysis_str = json.dumps(requirement_analysis, ensure_ascii=False, indent=2)
    six_points_str = json.dumps(six_points, ensure_ascii=False, indent=2)

    # 构造 System Prompt
    system_prompt = RISK_ASSESSMENT_SYSTEM_PROMPT.format(
        requirement_analysis=analysis_str,
        six_points=six_points_str,
        knowledge_context=knowledge_context if knowledge_context else "（知识库未检索到相关内容）",
    )

    from langchain_core.messages import SystemMessage, HumanMessage

    messages = [
        SystemMessage(content=system_prompt),
        HumanMessage(content="请基于以上分析数据和知识库检索结果进行全面的风险评估。"),
    ]

    print(f"[风险评估] 开始四维度风险评估")
    print(f"[风险评估] 知识库上下文: {'有内容' if knowledge_context else '无'}")
    print(f"[风险评估] 需求分析完整度: {requirement_analysis.get('completeness_score', 'N/A')}%")

    # 使用结构化输出
    structured_llm = llm.with_structured_output(RiskAssessmentResult, method="json_mode")
    try:
        result: Optional[RiskAssessmentResult] = structured_llm.invoke(messages)
    except Exception as exc:
        # json_mode 解析失败/限流/超时等 → 走降级（不打断流水线）
        print(f"[风险评估] [警告] 结构化输出异常 ({exc})，使用降级策略")
        result = None

    # ---- 降级处理 ----
    if result is None:
        print("[风险评估] [警告] 结构化输出解析失败，使用降级策略")
        raw_llm = llm.invoke(messages)
        raw_text = raw_llm.content if hasattr(raw_llm, "content") else str(raw_llm)
        print(f"[风险评估] LLM 原始输出 (前500字符): {raw_text[:500]}")
        return {
            "risk_analysis": {
                "tech_risks": [],
                "business_risks": [],
                "compliance_risks": [],
                "data_risks": [],
                "overall_risk_level": "中",
                "risk_summary": "风险评估解析失败，建议人工评估。原始输出: " + raw_text[:200],
                "key_concerns": ["自动化风险评估失败，需要人工介入"],
            }
        }

    # 转换为 dict
    risk_analysis_dict = {
        "tech_risks": [r.model_dump() for r in result.tech_risks],
        "business_risks": [r.model_dump() for r in result.business_risks],
        "compliance_risks": [r.model_dump() for r in result.compliance_risks],
        "data_risks": [r.model_dump() for r in result.data_risks],
        "overall_risk_level": result.overall_risk_level,
        "risk_summary": result.risk_summary,
        "key_concerns": result.key_concerns,
    }

    total_risks = (
        len(result.tech_risks)
        + len(result.business_risks)
        + len(result.compliance_risks)
        + len(result.data_risks)
    )
    high_risks = sum(
        1 for r in (
            list(result.tech_risks)
            + list(result.business_risks)
            + list(result.compliance_risks)
            + list(result.data_risks)
        )
        if r.severity == "高"
    )

    print(f"[风险评估] 完成: 共识别 {total_risks} 个风险点 ({high_risks} 个高风险)")
    print(f"[风险评估] 综合风险等级: {result.overall_risk_level}")

    return {"risk_analysis": risk_analysis_dict}
