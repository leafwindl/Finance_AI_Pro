"""步骤3: 关键词提取 — 从用户需求中提取四维关键词"""
import json
from ..state import RequirementState
from ..prompts import KEYWORD_EXTRACTION_SYSTEM_PROMPT
from src.models import get_llm


def extract_keywords(state: RequirementState) -> dict:
    user_input = state.get("user_input", "")
    file_context = state.get("file_content", "")
    file_context_str = f"\n[文件内容]:\n{file_context}" if file_context else ""

    llm = get_llm()
    prompt = KEYWORD_EXTRACTION_SYSTEM_PROMPT.format(
        user_input=user_input, file_context=file_context_str
    )
    response = llm.invoke(prompt)

    try:
        data = json.loads(response.content)
    except Exception:
        data = {}

    result = {
        "biz_keywords": data.get("business_keywords", ""),
        "test_keywords": data.get("test_keywords", ""),
        "regulatory_keywords": data.get("regulatory_keywords", ""),
        "history_keywords": data.get("history_keywords", ""),
        "kb_code_list": data.get("kb_code_list", []),
    }

    print(f"[关键词提取] 提取到 {len(result['kb_code_list'])} 个知识库映射")
    return result
