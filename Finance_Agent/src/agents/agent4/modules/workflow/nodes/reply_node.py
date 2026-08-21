from modules.state.state_def import WorkflowState

# 成功分支：Python转Markdown表格
def gen_markdown_node(state: WorkflowState) -> WorkflowState:
    step_list = state["parse_data"]
    if not step_list:
        return {"output_text": ""}

    markdown = "| 步骤 | 操作内容 | 预期结果 |\n"
    markdown += "|------|----------|----------|\n"
    for item in step_list:
        no = item.get("step_no", "")
        op = item.get("operate_content", "")
        exp = item.get("expect_result", "")
        markdown += f"| {no} | {op} | {exp} |\n"
    return {"output_text": markdown}


# 失败分支报错节点
def gen_error_node(state: WorkflowState) -> WorkflowState:
    # 优先使用解析阶段捕获的精准错误信息
    err_msg = state.get("error_msg")
    if not err_msg:
        err_msg = "测试步骤生成失败，请调整提问或补充相关知识库资料"
    return {"output_text": err_msg}