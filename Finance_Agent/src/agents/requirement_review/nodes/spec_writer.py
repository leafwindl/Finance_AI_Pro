"""步骤12: 报告生成 — 用户确认后生成 Markdown 需求说明书"""
import json
from ..state import RequirementState, merge_collected_info
from ..prompts import SPEC_GENERATION_SYSTEM_PROMPT
from src.models import get_llm


def generate_spec(state: RequirementState) -> dict:
    collected_info = state.get("collected_info", [])
    merged = merge_collected_info(collected_info)
    risk_details = state.get("risk_details", "")

    extracted_context = f"已收集信息: {merged}\n风险详情: {risk_details}"

    llm = get_llm()
    prompt = SPEC_GENERATION_SYSTEM_PROMPT.format(extracted_context=extracted_context)
    response = llm.invoke(prompt)

    try:
        data = json.loads(response.content)
        report = data.get("report", response.content)
    except Exception:
        report = response.content

    print(f"[报告生成] 报告长度: {len(report)} 字符")
    return {
        "generated_spec": report,
        "final_output": report,
    }
