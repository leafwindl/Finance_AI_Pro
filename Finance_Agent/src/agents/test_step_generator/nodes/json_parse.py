"""步骤5: JSON 解析 — 提取 ```json 代码块 + 严格字段校验（v2 新版）"""
import re
import json
from ..state import WorkflowState


def json_to_python_node(state: WorkflowState) -> dict:
    raw_text = state.get("llm_json_raw", "")
    is_success = 0
    step_array: list = []
    error_msg = ""

    # 1. 提取 ```json 代码块
    pattern = r'```\s*json\s*\n([\s\S]*?)\s*```'
    match_res = re.search(pattern, raw_text)
    if not match_res:
        return {
            "parse_data": None,
            "is_success": 0,
            "error_msg": "未找到 ```json 代码块",
        }

    json_str = match_res.group(1).strip()

    # 2. JSON 语法校验
    try:
        step_list = json.loads(json_str)
    except json.JSONDecodeError as e:
        return {
            "parse_data": None,
            "is_success": 0,
            "error_msg": f"JSON格式错误：{str(e)}",
        }

    # 3. 顶层必须是非空数组
    if not isinstance(step_list, list) or len(step_list) == 0:
        return {
            "parse_data": None,
            "is_success": 0,
            "error_msg": "JSON内容必须是不为空的步骤数组",
        }

    # 4. 校验每条必填字段: step_no, operate_content, expect_result
    required_fields = {"step_no", "operate_content", "expect_result"}
    for idx, item in enumerate(step_list):
        if not isinstance(item, dict):
            return {
                "parse_data": None,
                "is_success": 0,
                "error_msg": f"第{idx+1}条步骤不是对象",
            }
        if not required_fields.issubset(item.keys()):
            return {
                "parse_data": None,
                "is_success": 0,
                "error_msg": f"第{idx+1}条步骤缺失必填字段(step_no/operate_content/expect_result)",
            }

    # 全部校验通过
    return {
        "parse_data": step_list,
        "is_success": 1,
        "error_msg": "",
    }
