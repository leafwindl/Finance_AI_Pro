"""步骤7: LLM评审 — 18项检查清单"""
import json
import re
from ..graph.state import ReviewState
from ..models import get_llm
from ..prompts.review_prompt import REVIEW_PROMPT

CHECK_ITEMS = [
    "覆盖完整性-功能场景覆盖", "覆盖完整性-正常流程覆盖",
    "覆盖完整性-异常流程覆盖", "覆盖完整性-边界条件覆盖",
    "规则正确性-业务规则正确", "规则正确性-输入限制完整",
    "规则正确性-权限和状态校验覆盖",
    "可执行性-前置条件明确", "可执行性-测试意图明确",
    "可执行性-测试数据明确",
    "预期结果可观察性-预期结果具体", "预期结果可观察性-可验证成功或失败",
    "用例一致性-测试点和预期结果匹配", "用例一致性-输入输出一致",
    "用例唯一性-是否存在重复测试点", "用例唯一性-是否和已有用例重复",
    "历史缺陷风险-是否覆盖历史高风险问题", "历史缺陷风险-是否存在类似缺陷遗漏",
]


def normalize_checklist(checklist: list) -> list:
    """固定18项结构，LLM少返回的补默认值。

    兼容 LLM 返回 item 名称的多种变体：
      ① 精确匹配标准名        e.g. "是否存在重复测试点"
      ② 去前缀名              e.g. "功能场景覆盖"（标准名 "覆盖完整性-功能场景覆盖"）
      ③ 带描述后缀            e.g. "功能场景覆盖 — 是否覆盖所有功能点"
    """
    mapping = {}
    for item in checklist:
        name = item.get("item", "")
        if name:
            mapping[name] = item

    result = []
    for name in CHECK_ITEMS:
        matched = None
        # 1) 精确匹配
        if name in mapping:
            matched = mapping[name]
        else:
            keyword = name.split("-", 1)[1] if "-" in name else name
            # 2) 关键词（去前缀）精确匹配
            if keyword in mapping:
                matched = mapping[keyword]
            else:
                # 3) 包含匹配：LLM 名包含关键词（如 "功能场景覆盖 — 是否覆盖所有功能点"）
                for llm_name, item in mapping.items():
                    if keyword in llm_name:
                        matched = item
                        break
        if matched:
            out = dict(matched)
            out["item"] = name  # 统一为标准名
            # 输出长度兜底（与 prompt 约束一致：截断显示不丢数据本质）
            if out.get("kb_evidence"):
                out["kb_evidence"] = str(out["kb_evidence"])[:100]
            if out.get("issue"):
                out["issue"] = str(out["issue"])[:30]
            if out.get("suggestion"):
                out["suggestion"] = str(out["suggestion"])[:30]
            result.append(out)
        else:
            result.append({
                "item": name, "passed": False,
                "kb_evidence": "", "issue": "模型未返回该检查项",
                "suggestion": "请补充该测试点",
            })
    return result


def generate_review(state: ReviewState) -> dict:
    print("开始 ISTQB 18 项检查清单评审...")

    llm = get_llm()
    query = state.get("query", "")
    retrieval_context = state.get("retrieval_context", {})

    prompt = REVIEW_PROMPT.format(query=query, knowledge=retrieval_context)
    response = llm.invoke(prompt)

    def _parse_json(text: str):
        """增强容错解析：支持 直接JSON / ```json 代码块 / 首尾大括号截取。"""
        text = text.strip()
        # 1) 直接 JSON
        try:
            return json.loads(text)
        except Exception:
            pass
        # 2) ```json 代码块
        m = re.search(r"```(?:json)?\s*\n([\s\S]*?)```", text)
        if m:
            try:
                return json.loads(m.group(1).strip())
            except Exception:
                pass
        # 3) 截取首尾大括号（容忍前后多余说明文字）
        start, end = text.find("{"), text.rfind("}")
        if start != -1 and end > start:
            try:
                return json.loads(text[start:end + 1])
            except Exception:
                pass
        raise ValueError("无法解析 JSON")

    try:
        result = _parse_json(response.content)
    except Exception:
        result = {"checklist": [], "summary": response.content}

    result["checklist"] = normalize_checklist(result.get("checklist", []))
    print("  LLM 评审完成\n")
    return {"review_report": result}
