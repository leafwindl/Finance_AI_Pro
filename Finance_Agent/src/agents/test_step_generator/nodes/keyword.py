"""步骤1: 关键词提取（按知识库分组 — v2 新版）"""
import json
from langchain_core.prompts import ChatPromptTemplate
from ..state import WorkflowState
from ..prompts import KB_CATALOG
from src.models import get_llm

llm = get_llm()


def extract_keyword_node(state: WorkflowState) -> dict:
    state["progress_msg"] = "提取关键词中..."

    # ---- 从 test_case 中构造搜索文本 ----
    test_case = state.get("test_case") or {}
    parts = []
    if test_case.get("title"):
        parts.append(test_case["title"])
    if test_case.get("module"):
        parts.append(test_case["module"])
    if test_case.get("tags"):
        tags = test_case["tags"] if isinstance(test_case["tags"], list) else [test_case["tags"]]
        parts.extend(tags)
    if test_case.get("precondition"):
        parts.append(test_case["precondition"])
    if test_case.get("steps"):
        for step in test_case["steps"][:3]:
            parts.append(step.get("action", ""))
            parts.append(step.get("expected", ""))
    search_text = "，".join(p for p in parts if p) or state.get("query", "")

    # ---- 构造知识库目录提示 ----
    catalog_lines = []
    for code, info in KB_CATALOG.items():
        examples_str = "、".join(info["examples"])
        catalog_lines.append(
            f"【{code}】{info['name']}\n  描述：{info['desc']}\n  典型关键词：{examples_str}"
        )
    catalog_text = "\n\n".join(catalog_lines)

    prompt = ChatPromptTemplate.from_messages([
        ("system", f"""# 任务
根据用户输入，从每个知识库中提取出与之相关的检索关键词。

# 知识库清单
{catalog_text}

# 输出规则
1. 针对每个知识库，提取与用户输入相关的关键词
2. 无关的知识库返回空数组 []
3. 如果所有知识库均无关，将用户完整输入填入 KB01
4. 禁止增加用户输入中不存在的虚构词汇

# 输出格式
只输出纯JSON：{{{{"KB01":["关键词1"],"KB04":[],"KB05":[],"KB06":[]}}}}"""),
        ("user", "用户输入：{search_text}")
    ])

    chain = prompt | llm
    resp = chain.invoke({"search_text": search_text})
    raw_text = resp.content.strip()

    try:
        kb_keywords = json.loads(raw_text)
        if not isinstance(kb_keywords, dict):
            raise ValueError("返回不是字典")
    except Exception:
        kb_keywords = {"KB01": [search_text], "KB04": [], "KB05": [], "KB06": []}

    # 扁平化关键词列表
    all_keywords = []
    for kw_list in kb_keywords.values():
        all_keywords.extend(kw_list)
    if not all_keywords:
        all_keywords = [search_text]

    return {
        "keywords": all_keywords,
        "kb_keywords": kb_keywords,
        "progress_msg": state["progress_msg"],
    }
