import json
from langchain_core.prompts import ChatPromptTemplate
from modules.state.state_def import WorkflowState
from modules.llm.llm_client import llm

# 节点3：LLM生成结构化JSON
def llm_gen_json_node(state: WorkflowState) -> WorkflowState:
    state["progress_msg"] = "LLM调用中..."
    rag_context = "\n\n".join(state["rag_docs"])
    # 用户问题/用例输入：test_case 为空时用 query 兜底，避免模型零输入返回空数组
    user_input = state.get("query", "") or ""
    test_case_raw = state.get("test_case")
    test_case_text = json.dumps(test_case_raw, ensure_ascii=False) if test_case_raw else (user_input or "")
    prompt = ChatPromptTemplate.from_messages([
        ("system", """# 任务描述
测试步骤生成专家，依据测试用例、历史用例输出手工测试步骤

# 重要参数
--参考知识检索召回内容{rag_context}
--结构化测试用例原文{test_case}
--用户上传文档参考内容{doc_content}
--用户问题/用例标题{query}

# 忽略输入内容多余换行、空格，直接解析完整 JSON 结构

# 强制输出约束（必须严格遵守）
1.禁止输出开场白、解释文字、思考过程、多余说明；
2.最终返回内容只能是被 ```json 和 ```包裹的JSON数组；
3.数组里每个对象仅允许包含3个字段：
step_no：1开始的自增整数序号；
operate_content：25字精细操作；
expect_result：操作之后正确的15字预期结果；
4.只输出最多6步的核心步骤
# 示例输出格式（严格照搬格式，内容可更改）
```json
[
    {{"step_no":1,"operate_content":"...","expect_result":"..."}}
]"""),
        ("user", "请根据参考知识与用户问题生成测试步骤")
    ])
    chain = prompt | llm
    resp = chain.invoke({
        "rag_context": rag_context,
        "test_case": test_case_text,
        "doc_content": state.get("doc_content", ""),
        "query": user_input,
    })
    raw = resp.content.strip()
    # 存入原始字符串，后续节点统一清洗解析
    return {"llm_json_raw": raw, "progress_msg": state["progress_msg"]}