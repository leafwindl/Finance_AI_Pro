"""步骤2: 关键词解析节点（Code）— 正则清洗 + 白名单过滤"""
import json
import re
from ..state import ReviewState


def parse_keywords(state: ReviewState) -> dict:
    keyword_raw = state.get("keyword_raw", "")
    keywords = {
        "standard_cases_query": "",
        "history_defects_query": "",
        "test_spec_query": "",
    }

    if not keyword_raw:
        return {"keywords": keywords}

    try:
        text = re.sub(r"```json|```", "", keyword_raw).strip()
        match = re.search(r"\{.*\}", text, re.S)
        if not match:
            return {"keywords": keywords}

        data = json.loads(match.group())
        for key in keywords:
            value = data.get(key)
            if isinstance(value, str):
                keywords[key] = value
    except Exception:
        pass

    return {"keywords": keywords}
