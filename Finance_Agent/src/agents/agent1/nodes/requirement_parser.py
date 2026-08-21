"""
需求解析节点 (Requirement Parser)

流水线第1步: 对用户输入的一次性需求描述进行理解和结构化分析。

功能:
    1. 读取用户输入的完整需求文本
    2. 调用 LLM 进行深度理解和结构化分析
    3. 输出需求概要、业务上下文、功能范围、涉及系统、约束条件
    4. 评估信息完整度，标记缺失信息

结构化输出 Schema:
    {
      "summary": str,
      "business_context": str,
      "functional_scope": str,
      "affected_systems": list,
      "constraints": list,
      "completeness_score": float,
      "missing_info": [{"item": str, "impact": str, "suggestion": str}]
    }
"""

from typing import Optional
from pydantic import BaseModel, Field
from ..state import RequirementState
from .llm_config import llm
from ..prompts import REQUIREMENT_PARSER_SYSTEM_PROMPT


# ================================================================
# Pydantic 模型: 需求解析的结构化输出 Schema
# ================================================================

class MissingInfoItem(BaseModel):
    """缺失信息项"""
    item: str = Field(description="缺失的信息项名称")
    impact: str = Field(description="缺失该项对后续工作的影响")
    suggestion: str = Field(description="建议补充的内容方向")


class RequirementAnalysisResult(BaseModel):
    """需求解析的完整输出"""
    summary: str = Field(description="需求概要，1-2句话概括核心内容")
    business_context: str = Field(description="业务上下文分析")
    functional_scope: str = Field(description="功能范围描述")
    affected_systems: list[str] = Field(description="涉及的系统或模块列表")
    constraints: list[str] = Field(description="约束条件列表")
    completeness_score: float = Field(description="信息完整度评分 0-100")
    missing_info: list[MissingInfoItem] = Field(
        default_factory=list,
        description="缺失信息列表"
    )


# ================================================================
# 需求解析节点
# ================================================================

def requirement_parser(state: RequirementState) -> dict:
    """
    需求解析节点: 对用户一次性输入的需求进行结构化分析。

    这是流水线的第一个节点，负责:
        1. 深度理解需求文本
        2. 提取结构化信息
        3. 评估信息完整度
        4. 标记缺失信息

    Args:
        state: RequirementState, 包含 requirement_input

    Returns:
        dict: 包含 requirement_analysis
    """
    requirement_input = state.get("requirement_input", "")

    # ---- 文件内容 (如果有上传) ----
    file_content = state.get("file_content", "")
    file_name = state.get("file_name", "")
    if file_content:
        file_context = (
            f"\n\n### 用户上传文件内容 ({file_name}):\n"
            f"{file_content[:3000]}"
        )
    else:
        file_context = ""

    # 构造 System Prompt
    system_prompt = REQUIREMENT_PARSER_SYSTEM_PROMPT.format(
        requirement_input=requirement_input,
        file_context=file_context,
    )

    from langchain_core.messages import SystemMessage, HumanMessage

    messages = [
        SystemMessage(content=system_prompt),
        HumanMessage(content=requirement_input),
    ]

    print(f"[需求解析] 分析需求输入 ({len(requirement_input)} 字符)")

    # 使用结构化输出
    structured_llm = llm.with_structured_output(RequirementAnalysisResult, method="json_mode")
    try:
        result: Optional[RequirementAnalysisResult] = structured_llm.invoke(messages)
    except Exception as exc:
        # json_mode 解析失败/限流/超时等 → 走降级（不打断流水线）
        print(f"[需求解析] [警告] 结构化输出异常 ({exc})，使用降级策略")
        result = None

    # ---- 结构化输出解析失败时的降级处理 ----
    if result is None:
        print("[需求解析] [警告] 结构化输出解析失败，使用降级策略")
        raw_llm = llm.invoke(messages)
        raw_text = raw_llm.content if hasattr(raw_llm, "content") else str(raw_llm)
        print(f"[需求解析] LLM 原始输出 (前500字符): {raw_text[:500]}")
        return {
            "requirement_analysis": {
                "summary": requirement_input[:200] if requirement_input else "（无法解析）",
                "business_context": "（解析失败，请检查输入）",
                "functional_scope": "（解析失败）",
                "affected_systems": [],
                "constraints": [],
                "completeness_score": 30.0,
                "missing_info": [
                    {
                        "item": "需求解析失败",
                        "impact": "无法进行后续分析",
                        "suggestion": "请重新提供更清晰的需求描述"
                    }
                ],
            }
        }

    # 转换为 dict 用于 state 更新
    analysis_dict = {
        "summary": result.summary,
        "business_context": result.business_context,
        "functional_scope": result.functional_scope,
        "affected_systems": result.affected_systems,
        "constraints": result.constraints,
        "completeness_score": result.completeness_score,
        "missing_info": [m.model_dump() for m in result.missing_info],
    }

    print(f"[需求解析] 完成: 完整度 {result.completeness_score}%")
    print(f"[需求解析] 涉及系统: {result.affected_systems}")
    print(f"[需求解析] 缺失信息 {len(result.missing_info)} 项")

    return {"requirement_analysis": analysis_dict}
