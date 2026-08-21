"""
报告生成节点 (Report Generator)

流水线第6步(最后一步): 汇总所有分析结果，生成最终《需求预评审报告》。

功能:
    1. 汇总需求解析、六大要点、知识库检索、风险评估结果
    2. 调用 LLM 生成结构化 Markdown 报告
    3. 包含五大章节：需求概述、六大要点评估、知识库关联案例、风险评估、预评审结论
    4. 标记信息缺失项，给出风险提示和建议

输出:
    完整的 Markdown 格式预评审报告，包含:
    - 需求概述
    - 六大要点评估（含信息完整度）
    - 知识库关联案例
    - 风险评估（技术/业务/合规/数据）
    - 预评审结论（风险等级 + 建议）
"""

from datetime import datetime
from ..state import RequirementState
from .llm_config import llm
from ..prompts import REPORT_GENERATOR_SYSTEM_PROMPT


# ================================================================
# 报告生成节点
# ================================================================

def report_generator(state: RequirementState) -> dict:
    """
    报告生成节点: 汇总所有分析结果生成最终预评审报告。

    这是流水线的最终输出节点，负责:
        1. 汇总所有上游节点的分析结果
        2. 计算综合完整度评分
        3. 生成结构化的 Markdown 预评审报告
        4. 设置 final_output 供调用方获取

    Args:
        state: 包含所有分析结果

    Returns:
        dict: 包含 final_report, final_output
    """
    requirement_input = state.get("requirement_input", "")
    requirement_analysis = state.get("requirement_analysis", {})
    six_points = state.get("six_points", {})
    knowledge_context = state.get("knowledge_context", "")
    risk_analysis = state.get("risk_analysis", {})

    import json

    # 计算综合完整度评分: 取需求解析完整度和六大要点完整度的加权平均
    parse_score = requirement_analysis.get("completeness_score", 0) if requirement_analysis else 0
    six_points_score = six_points.get("completeness_score", 0) if six_points else 0
    completeness_score = round((parse_score * 0.4 + six_points_score * 0.6), 1)

    # 格式化分析结果为文本供 LLM 使用
    # 提取六大要点中的纯文本内容，减少嵌套 token
    six_points_compact = {
        "background": six_points.get("background", ""),
        "business_objective": six_points.get("business_objective", ""),
        "user_scope": six_points.get("user_scope", ""),
        "functional_requirements": six_points.get("functional_requirements", ""),
        "non_functional_requirements": six_points.get("non_functional_requirements", ""),
        "implementation_impact": six_points.get("implementation_impact", ""),
        "completeness_score": six_points.get("completeness_score", 0),
        "missing_items": six_points.get("missing_items", []),
    }

    generation_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # 构造 System Prompt
    system_prompt = REPORT_GENERATOR_SYSTEM_PROMPT.format(
        generation_time=generation_time,
        completeness_score=completeness_score,
        background=six_points_compact.get("background", "【信息缺失】"),
        business_objective=six_points_compact.get("business_objective", "【信息缺失】"),
        user_scope=six_points_compact.get("user_scope", "【信息缺失】"),
        functional_requirements=six_points_compact.get("functional_requirements", "【信息缺失】"),
        non_functional_requirements=six_points_compact.get("non_functional_requirements", "【信息缺失】"),
        implementation_impact=six_points_compact.get("implementation_impact", "【信息缺失】"),
        overall_risk_level=risk_analysis.get("overall_risk_level", "中") if risk_analysis else "中",
        requirement_analysis=json.dumps(requirement_analysis, ensure_ascii=False, indent=2),
        six_points=json.dumps(six_points_compact, ensure_ascii=False, indent=2),
        knowledge_context=knowledge_context if knowledge_context else "（知识库未检索到相关内容）",
        risk_analysis=json.dumps(risk_analysis, ensure_ascii=False, indent=2) if risk_analysis else "{}",
        requirement_input=requirement_input,
    )

    from langchain_core.messages import SystemMessage, HumanMessage

    messages = [
        SystemMessage(content=system_prompt),
        HumanMessage(content="请基于以上所有分析数据生成完整的《需求预评审报告》。"),
    ]

    print(f"[报告生成] 开始生成预评审报告")
    print(f"[报告生成] 综合完整度: {completeness_score}%")
    print(f"[报告生成] 风险等级: {risk_analysis.get('overall_risk_level', 'N/A') if risk_analysis else 'N/A'}")

    # 报告生成不需要结构化输出, 直接生成 Markdown 文本
    # 因为报告内容较长且格式灵活, JSON 包装反而会引入转义问题
    response = llm.invoke(messages)
    report_text = response.content if hasattr(response, "content") else str(response)

    # 如果 LLM 返回了 JSON 包裹的内容, 尝试提取纯文本
    # 某些模型可能仍然尝试输出 JSON
    if report_text.strip().startswith("{") and '"report"' in report_text:
        try:
            parsed = json.loads(report_text)
            if isinstance(parsed, dict) and "report" in parsed:
                report_text = parsed["report"]
        except (json.JSONDecodeError, TypeError):
            pass  # 不是有效的 JSON, 保持原样

    print(f"[报告生成] 完成: 报告长度 {len(report_text)} 字符")

    return {
        "final_report": report_text,
        "final_output": report_text,
    }
