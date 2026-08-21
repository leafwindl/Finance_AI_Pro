import re
import json
from modules.state.state_def import WorkflowState

def json_to_python_node(state: WorkflowState) -> WorkflowState:
    raw_text = state["llm_json_raw"]

    # 初始化结果
    is_success = 0
    step_array = []
    error_msg = ""

    # 1. 提取 ```json 代码块
    pattern = r'```\s*json\s*\n([\s\S]*?)\s*```'
    match_res = re.search(pattern, raw_text)
    if not match_res:
        error_msg = "未找到 ```json 代码块"
        return {
            "parse_data": None,
            "is_success": is_success,
            "error_msg": error_msg
        }

    json_str = match_res.group(1).strip()

    # 2. JSON语法校验
    try:
        step_list = json.loads(json_str)
    except json.JSONDecodeError as e:
        error_msg = f"JSON格式错误：{str(e)}"
        return {
            "parse_data": None,
            "is_success": is_success,
            "error_msg": error_msg
        }

    # 3. 顶层必须是非空数组（容错：对象内嵌数组如 {"steps": [...]}）
    if not isinstance(step_list, list) or len(step_list) == 0:
        if isinstance(step_list, dict):
            for key in ("steps", "step_list", "data", "result", "results"):
                v = step_list.get(key)
                if isinstance(v, list) and len(v) > 0:
                    step_list = v
                    break
    if not isinstance(step_list, list) or len(step_list) == 0:
        error_msg = "JSON内容必须是不为空的步骤数组"
        return {
            "parse_data": None,
            "is_success": is_success,
            "error_msg": error_msg
        }

    # 3.5 容错：step_no 统一规整为 int（字符串数字 / 整数值 float → int；
    # 规整不了的保持原值，由步骤 4 的类型校验明确报错，不再静默漏进 markdown）
    for item in step_list:
        if not isinstance(item, dict):
            continue
        step_no = item.get("step_no")
        if isinstance(step_no, str):
            try:
                item["step_no"] = int(step_no.strip())
            except ValueError:
                pass
        elif isinstance(step_no, float) and step_no.is_integer():
            item["step_no"] = int(step_no)

    # 4. 校验每条顶层必填字段 step_no, operate_content, expect_result
    required_fields = {"step_no", "operate_content", "expect_result"}
    for idx, item in enumerate(step_list):
        if not isinstance(item, dict):
            error_msg = f"第{idx+1}条步骤不是对象"
            return {
                "parse_data": None,
                "is_success": is_success,
                "error_msg": error_msg
            }
        if not required_fields.issubset(item.keys()):
            error_msg = f"第{idx+1}条步骤缺失必填字段(step_no/operate_content/expect_result)"
            return {
                "parse_data": None,
                "is_success": is_success,
                "error_msg": error_msg
            }
        step_no = item.get("step_no")
        if type(step_no) is not int:
            error_msg = (
                f"第{idx+1}条步骤 step_no 必须为整数，实际为 "
                f"{type(step_no).__name__}({step_no!r})"
            )
            return {
                "parse_data": None,
                "is_success": is_success,
                "error_msg": error_msg
            }

    # 全部校验通过
    is_success = 1
    step_array = step_list

    return {
        "parse_data": step_array,
        "is_success": is_success,
        "error_msg": error_msg
    }