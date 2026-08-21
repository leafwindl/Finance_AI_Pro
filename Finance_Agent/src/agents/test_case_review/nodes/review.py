"""步骤7: LLM评审 — 18项检查清单"""
import json
import os
import re
from ..state import ReviewState
from langchain_deepseek import ChatDeepSeek
from ..prompts import REVIEW_PROMPT

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
    """将 LLM 返回的清单对齐到固定 18 项结构。
    LLM 返回的 item 名称可能不与 CHECK_ITEMS 完全一致，
    因此优先按名称匹配，失败时按位置对应。
    """
    if not checklist:
        checklist = []
    # 构建名称→条目的映射
    name_map = {item.get("item", ""): item for item in checklist}
    # 构建位置映射（LLM 返回顺序通常与 CHECK_ITEMS 一致）
    pos_map = {i: item for i, item in enumerate(checklist)}

    result = []
    for i, name in enumerate(CHECK_ITEMS):
        # 先用名称匹配
        if name in name_map:
            result.append(name_map[name])
        # 再尝试模糊匹配（从 LLM 返回的名称里查关键词）
        elif found := next((item for item in checklist
                            if name.split("-")[-1][:4] in item.get("item", "")), None):
            result.append(found)
        # 失败时按位置对应
        elif i in pos_map:
            item = pos_map[i]
            item["item"] = name  # 统一名称
            result.append(item)
        else:
            result.append({
                "item": name, "passed": False,
                "kb_evidence": "", "issue": "模型未返回该检查项",
                "suggestion": "请补充该测试点",
            })
    return result


def generate_review(state: ReviewState) -> dict:
    print("开始 ISTQB 18 项检查清单评审（deepseek-chat）...")

    llm = ChatDeepSeek(
        model="deepseek-chat",
        api_key=os.getenv("DEEPSEEK_API_KEY"),
        api_base=os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com"),
        temperature=float(os.getenv("DEEPSEEK_TEMPERATURE", "0.7")),
    )
    query = state.get("query", "")
    retrieval_context = state.get("retrieval_context", {})

    prompt = REVIEW_PROMPT.format(query=query, knowledge=retrieval_context)
    response = llm.invoke(prompt)

    raw_content = response.content
    print(f"  [DEBUG] LLM 返回 ({len(raw_content)} 字符): {raw_content[:300]}...")

    try:
        text = raw_content.strip()
        # 去掉可能的 markdown 代码块标记
        text = re.sub(r"```(?:json)?\s*", "", text)
        text = re.sub(r"```\s*", "", text)
        # 找到 JSON 对象的起止位置进行精确提取
        start = text.find("{")
        end = text.rfind("}")
        if start != -1 and end > start:
            text = text[start:end + 1]
        print(f"  [DEBUG] 提取后 JSON ({len(text)} 字符): {text[:200]}...")
        result = json.loads(text)
        print(f"  [DEBUG] JSON 解析成功, checklist 数量: {len(result.get('checklist', []))}")
    except Exception as e:
        print(f"  [DEBUG] JSON 解析失败: {e}")
        print(f"  [DEBUG] 全文: {raw_content}")
        result = {"checklist": [], "summary": raw_content}

    result["checklist"] = normalize_checklist(result.get("checklist", []))
    print("  LLM 评审完成\n")
    return {"review_report": result}
