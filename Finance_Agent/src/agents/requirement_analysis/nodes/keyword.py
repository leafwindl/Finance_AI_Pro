"""步骤1: 关键词提取"""
import json
from ..state import AgentState
from ..prompts import KEYWORD_EXTRACTION_PROMPT
from src.models import get_llm


def extract_keywords(state: AgentState) -> dict:
    messages = state.get("messages", [])
    input_text = messages[-1].content if messages else ""

    llm = get_llm()
    prompt = KEYWORD_EXTRACTION_PROMPT.format(input_text=input_text)
    response = llm.invoke(prompt)

    try:
        data = json.loads(response.content)
    except Exception:
        data = {}

    print(f"[关键词提取] kb_code_list={data.get('kb_code_list', [])}")
    return {
        "biz_keywords": data.get("biz_keywords", ""),
        "test_keywords": data.get("test_keywords", ""),
        "regulatory_keywords": data.get("regulatory_keywords", ""),
        "kb_code_list": data.get("kb_code_list", []),
    }
