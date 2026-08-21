"""
六大要点评估节点 (Six Points Evaluation)

流水线第4步: 基于需求解析结果，自动生成六大要点评估。

功能:
    1. 读取需求解析结果
    2. 调用 LLM 自动生成六大要点评估
    3. 标记信息缺失项并给出风险提示
    4. 计算各要点完整度

六大要点:
    1. 需求背景 (background)
    2. 业务目标 (business_objective)
    3. 用户范围 (user_scope)
    4. 功能需求 (functional_requirements)
    5. 非功能需求 (non_functional_requirements)
    6. 实施影响分析 (implementation_impact)

结构化输出 Schema:
    {
      "background": str,
      "business_objective": str,
      "user_scope": str,
      "functional_requirements": str,
      "non_functional_requirements": str,
      "implementation_impact": str,
      "completeness_score": float,
      "missing_items": [{"point": str, "issue": str, "risk": str, "suggestion": str}]
    }
"""

from typing import Optional
from pydantic import BaseModel, Field
from ..state import RequirementState
from .llm_config import llm
from ..prompts import SIX_POINTS_EVAL_SYSTEM_PROMPT


# ================================================================
# Pydantic 模型: 六大要点评估的结构化输出 Schema
# ================================================================

class MissingItem(BaseModel):
    """缺失项标记"""
    point: str = Field(description="缺失涉及的六大要点名称")
    issue: str = Field(description="具体缺失的信息")
    risk: str = Field(description="该缺失可能带来的风险")
    suggestion: str = Field(description="建议补充的内容")


class SixPointsResult(BaseModel):
    """六大要点评估的完整输出"""
    background: str = Field(description="需求背景描述")
    business_objective: str = Field(description="业务目标描述")
    user_scope: str = Field(description="用户范围描述")
    functional_requirements: str = Field(description="功能需求描述")
    non_functional_requirements: str = Field(description="非功能需求描述")
    implementation_impact: str = Field(description="实施影响分析")
    completeness_score: float = Field(description="六大要点综合完整度 0-100")
    missing_items: list[MissingItem] = Field(
        default_factory=list,
        description="缺失信息项列表"
    )


# ================================================================
# 六大要点评估节点
# ================================================================

def six_points_eval(state: RequirementState) -> dict:
    """
    六大要点评估节点: 自动生成需求预评审的六大要点。

    这是流水线的核心评估节点，负责:
        1. 基于需求解析结果生成六大要点
        2. 对每个要点进行详细阐述
        3. 标记信息缺失项
        4. 给出各要点的风险提示

    Args:
        state: 包含 requirement_input, requirement_analysis 等

    Returns:
        dict: 包含 six_points
    """
    requirement_input = state.get("requirement_input", "")
    requirement_analysis = state.get("requirement_analysis", {})

    # ---- 文件内容 ----
    file_content = state.get("file_content", "")
    file_name = state.get("file_name", "")
    if file_content:
        file_context = (
            f"\n\n### 用户上传文件内容 ({file_name}):\n"
            f"{file_content[:3000]}"
        )
    else:
        file_context = ""

    # 格式化需求解析结果为可读文本
    import json
    analysis_str = json.dumps(requirement_analysis, ensure_ascii=False, indent=2)

    # 构造 System Prompt
    system_prompt = SIX_POINTS_EVAL_SYSTEM_PROMPT.format(
        requirement_input=requirement_input,
        requirement_analysis=analysis_str,
        file_context=file_context,
    )

    from langchain_core.messages import SystemMessage, HumanMessage

    messages = [
        SystemMessage(content=system_prompt),
        HumanMessage(content=f"请基于以下需求解析结果生成六大要点评估:\n{analysis_str}"),
    ]

    print(f"[六大要点评估] 开始评估 (需求解析完整度: {requirement_analysis.get('completeness_score', 'N/A')}%)")

    # 使用结构化输出
    structured_llm = llm.with_structured_output(SixPointsResult, method="json_mode")
    try:
        result: Optional[SixPointsResult] = structured_llm.invoke(messages)
    except Exception as exc:
        # json_mode 解析失败/限流/超时等 → 走降级（不打断流水线）
        print(f"[六大要点评估] [警告] 结构化输出异常 ({exc})，使用降级策略")
        result = None

    # ---- 降级处理 ----
    if result is None:
        print("[六大要点评估] [警告] 结构化输出解析失败，使用降级策略")
        raw_llm = llm.invoke(messages)
        raw_text = raw_llm.content if hasattr(raw_llm, "content") else str(raw_llm)
        print(f"[六大要点评估] LLM 原始输出 (前500字符): {raw_text[:500]}")

        # 使用需求解析结果作为降级内容
        analysis = requirement_analysis or {}
        return {
            "six_points": {
                "background": analysis.get("business_context", "【信息缺失】无法生成"),
                "business_objective": "【信息缺失】无法生成",
                "user_scope": "【信息缺失】无法生成",
                "functional_requirements": analysis.get("functional_scope", "【信息缺失】"),
                "non_functional_requirements": "【信息缺失】无法生成",
                "implementation_impact": "【信息缺失】无法生成",
                "completeness_score": 20.0,
                "missing_items": [
                    {
                        "point": "全部要点",
                        "issue": "LLM解析失败，六大要点评估无法完成",
                        "risk": "需求预评审无法正常进行",
                        "suggestion": "请重新提供更清晰的需求描述"
                    }
                ],
            }
        }

    # 转换为 dict
    six_points_dict = {
        "background": result.background,
        "business_objective": result.business_objective,
        "user_scope": result.user_scope,
        "functional_requirements": result.functional_requirements,
        "non_functional_requirements": result.non_functional_requirements,
        "implementation_impact": result.implementation_impact,
        "completeness_score": result.completeness_score,
        "missing_items": [m.model_dump() for m in result.missing_items],
    }

    filled_count = sum(
        1 for k in ["background", "business_objective", "user_scope",
                    "functional_requirements", "non_functional_requirements",
                    "implementation_impact"]
        if six_points_dict.get(k) and "信息缺失" not in six_points_dict[k]
    )
    print(f"[六大要点评估] 完成: {filled_count}/6 要点有实质内容")
    print(f"[六大要点评估] 综合完整度: {result.completeness_score}%")
    print(f"[六大要点评估] 缺失项: {len(result.missing_items)} 项")

    return {"six_points": six_points_dict}
