"""步骤2: 关键词解析节点（Code）"""
import json
import re
from typing import Dict, Any

from ..graph.state import ReviewState


def parse_keywords(state: ReviewState) -> Dict[str, Any]:
    """
    对应 Dify: 提取变量 Code 节点
    输入: keyword_raw
    输出: keywords (固定三个字段)
    """
    keyword_raw = state.get("keyword_raw", "")

    keywords = {
        "standard_cases_query": "",
        "history_defects_query": "",
        "test_spec_query": "",
    }

    if not keyword_raw:
        return {"keywords": keywords}

    try:
        # 清理 Markdown
        text = re.sub(r"```json|```", "", keyword_raw).strip()
        # 提取 JSON
        match = re.search(r"\{.*\}", text, re.S)
        if not match:
            return {"keywords": keywords}

        data = json.loads(match.group())
        # 字段过滤，防止 LLM 返回多余字段
        for key in keywords:
            value = data.get(key)
            if isinstance(value, str):
                keywords[key] = value
    except Exception:
        pass

    return {"keywords": keywords}
