"""步骤6: 核心信息提取 — 风险预评估 + 6维度提取"""
import json
from ..state import RequirementState, merge_collected_info
from ..prompts import EXTRACTION_SYSTEM_PROMPT
from src.models import get_llm


def extract_info(state: RequirementState) -> dict:
    user_input = state.get("user_input", "")
    knowledge_context = state.get("knowledge_context", "")
    collected_info = state.get("collected_info", [])
    merged_info = merge_collected_info(collected_info)

    llm = get_llm()
    prompt = EXTRACTION_SYSTEM_PROMPT.format(
        user_input=user_input,
        knowledge_context=knowledge_context,
        merged_info=merged_info,
    )
    response = llm.invoke(prompt)

    try:
        data = json.loads(response.content)
    except Exception:
        data = {}

    extracted = data.get("extracted", {})
    risk_detected = data.get("risk_detected", False)

    print(f"[信息提取] 完成, risk_detected={risk_detected}, is_complete={data.get('is_complete', False)}")
    return {
        "extracted_dimensions": extracted,
        "is_complete": data.get("is_complete", False),
        "clarification_question": data.get("clarification_question", ""),
        "risk_detected": risk_detected,
        "risk_details": data.get("risk_details", ""),
    }
