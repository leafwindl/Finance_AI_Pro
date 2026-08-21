"""步骤6-7: 成功=Markdown表格 / 失败=错误信息（v2 新版）"""
from ..state import WorkflowState


def gen_markdown_node(state: WorkflowState) -> dict:
    """成功分支：步骤数组 → Markdown 表格"""
    step_list = state.get("parse_data") or []
    if not step_list:
        return {"output_text": "", "progress_msg": "步骤生成完成!"}

    lines = [
        "| 步骤 | 操作内容 | 预期结果 |",
        "|------|----------|----------|",
    ]
    for item in step_list:
        no = item.get("step_no", "")
        op = item.get("operate_content", "")
        exp = item.get("expect_result", "")
        lines.append(f"| {no} | {op} | {exp} |")

    output = "\n".join(lines)
    state["progress_msg"] = "步骤生成完成!"
    return {"output_text": output, "progress_msg": state["progress_msg"]}


def gen_error_node(state: WorkflowState) -> dict:
    """失败分支：返回错误信息"""
    err_msg = state.get("error_msg") or "测试步骤生成失败，请调整提问或补充相关知识库资料"
    state["progress_msg"] = "步骤生成失败"
    return {"output_text": err_msg, "error_msg": err_msg, "progress_msg": state["progress_msg"]}
