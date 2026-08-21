"""步骤11: 修改提取 — 从用户修改指令中提取修改项"""
import json
from ..state import RequirementState, merge_collected_info
from ..prompts import MODIFICATION_EXTRACTION_SYSTEM_PROMPT
from src.models import get_llm


def extract_modifications(state: RequirementState) -> dict:
    user_input = state.get("user_input", "")
    collected_info = state.get("collected_info", [])
    merged = merge_collected_info(collected_info)

    llm = get_llm()
    prompt = MODIFICATION_EXTRACTION_SYSTEM_PROMPT.format(
        user_input=user_input,
        collected_info=merged,
        extracted_context="",
    )
    response = llm.invoke(prompt)

    try:
        data = json.loads(response.content)
    except Exception:
        data = {"modifications": [], "summary": "无法解析修改内容"}

    modifications = data.get("modifications", [])
    print(f"[修改提取] {len(modifications)} 项修改")

    # 应用修改到 collected_info
    if modifications and collected_info:
        latest = dict(collected_info[-1]) if collected_info else {}
        for mod in modifications:
            dim = mod.get("dimension", "")
            if dim in latest:
                latest[dim] = mod.get("new_content", "")
        collected_info[-1] = latest

    return {
        "modifications": modifications,
        "collected_info": collected_info,
    }
