"""步骤4: LLM 生成测试步骤 JSON（v2 — 结构化 test_case 输入）"""
import json
from langchain_core.prompts import ChatPromptTemplate
from ..state import WorkflowState
from src.models import get_llm

llm = get_llm()


def llm_gen_json_node(state: WorkflowState) -> dict:
    state["progress_msg"] = "LLM调用中..."
    rag_context = "\n\n".join(state.get("rag_docs", []))

    prompt = ChatPromptTemplate.from_messages([
        ("system", """# 任务描述
测试步骤生成专家，依据测试用例、历史用例输出手工测试步骤

# 重要参数
--参考知识检索召回内容{rag_context}
--结构化测试用例原文{test_case}
--用户上传文档参考内容{doc_content}

# 强制输出约束
1. 禁止输出开场白、解释文字、思考过程
2. 最终返回内容只能是被 ```json 和 ``` 包裹的 JSON 数组
3. 数组里每个对象仅允许包含 3 个字段：
   step_no: 1 开始的自增整数序号
   operate_content: 25 字精细操作
   expect_result: 操作之后正确的 15 字预期结果
4. 只输出最多 6 步的核心步骤

# 示例输出格式
```json
[
    {{"step_no":1,"operate_content":"...","expect_result":"..."}}
]
```"""),
        ("user", "请根据参考知识与用户问题生成测试步骤")
    ])

    chain = prompt | llm
    resp = chain.invoke({
        "rag_context": rag_context,
        "test_case": json.dumps(state.get("test_case"), ensure_ascii=False) if state.get("test_case") else "",
        "doc_content": state.get("doc_content", ""),
    })

    return {
        "llm_json_raw": resp.content.strip(),
        "progress_msg": state["progress_msg"],
    }
