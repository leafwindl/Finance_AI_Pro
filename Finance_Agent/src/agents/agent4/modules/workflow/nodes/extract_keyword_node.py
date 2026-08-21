import json
from langchain_core.prompts import ChatPromptTemplate
from modules.state.state_def import WorkflowState
from modules.llm.llm_client import get_deepseek_llm

# 提取关键词用低温度，保证结果稳定
llm = get_deepseek_llm(temperature=0.1)

# 知识库概览（供 LLM 识别用户意图归属）—— 固定不变，模块加载时初始化一次
KB_CATALOG = {
    "KB01": {
        "name": "系统业务知识库",
        "desc": "收录模拟证券系统业务流程、功能模块与各类交易校验规则。",
        "examples": ["交易委托", "权限校验", "资金校验", "异常场景", "批量操作", "创业板交易"]
    },
    "KB04": {
        "name": "标准测试用例知识库",
        "desc": "存储标准化业务与接口测试范本。",
        "examples": ["功能用例", "接口用例", "边界场景", "异常校验", "执行步骤", "预期输出"]
    },
    "KB05": {
        "name": "历史缺陷与测试经验知识库",
        "desc": "收录历史缺陷案例与测试避坑经验。",
        "examples": ["故障复现", "根因分析", "接口异常", "幂等失效", "数据不一致", "边界缺陷"]
    },
    "KB06": {
        "name": "测试规范与模板知识库",
        "desc": "统一全套测试流程书写标准模板。",
        "examples": ["需求评审", "测试分析", "用例设计", "等价类", "验收标准", "测试模板"]
    }
}

# 预编译固定文本（仅初始化一次）
_KB_CATALOG_LINES = []
for _code, _info in KB_CATALOG.items():
    _examples_str = "、".join(_info["examples"])
    _KB_CATALOG_LINES.append(
        f"【{_code}】{_info['name']}\n  描述：{_info['desc']}\n  典型关键词：{_examples_str}"
    )
_CATALOG_TEXT = "\n\n".join(_KB_CATALOG_LINES)

# 预编译 Prompt 和 Chain（仅初始化一次）
_KB_PROMPT = ChatPromptTemplate.from_messages([
    ("system", f"""# 任务
根据用户输入，提取出与每个知识库相关的检索关键词。

# 知识库清单
{_CATALOG_TEXT}

# 输出规则
1. 针对每个知识库，提取与用户输入相关的关键词（可以是典型关键词列表中的词，也可以是语义近似的其他词）
2. 无关的知识库返回空数组 []
3. 如果所有知识库均无关，将用户完整输入填入 KB01
4. 禁止增加用户输入中不存在的虚构词汇

# 输出格式
只输出纯JSON，不要markdown、解释文字、换行。
{{{{"KB01":["关键词1","关键词2"],"KB04":[],"KB05":[],"KB06":[]}}}}"""),
    ("user", "用户输入：{search_text}")
])
_KB_CHAIN = _KB_PROMPT | llm

# 节点1：提取关键词（按知识库分组）
def extract_keyword_node(state: WorkflowState) -> WorkflowState:
    state["progress_msg"] = "提取关键词中..."

    # 从 test_case 中提取已知字段拼接搜索文本
    test_case = state.get("test_case") or {}
    parts = []
    if test_case.get("title"):
        parts.append(test_case["title"])
    if test_case.get("module"):
        parts.append(test_case["module"])
    if test_case.get("preconditions"):
        parts.append(test_case["preconditions"])
    # query 兜底：Gateway 链路只传 query（test_case 为空 dict 时），
    # 否则 search_text 为空 → LLM 提不出关键词 → KB 检索恒为空。
    search_text = (
        "、".join(p for p in parts if p)
        or str(state.get("query") or "").strip()
        or json.dumps(test_case, ensure_ascii=False)
    )

    # 使用预编译的 Prompt 和 Chain（模块加载时已初始化）
    resp = _KB_CHAIN.invoke({"search_text": search_text})
    raw_text = resp.content.strip()

    try:
        kb_keywords = json.loads(raw_text)
        if not isinstance(kb_keywords, dict):
            raise ValueError("返回不是字典")
    except Exception:
        kb_keywords = {"KB01": [search_text], "KB04": [], "KB05": [], "KB06": []}

    return {
        "kb_keywords": kb_keywords,
        "progress_msg": state["progress_msg"]
    }