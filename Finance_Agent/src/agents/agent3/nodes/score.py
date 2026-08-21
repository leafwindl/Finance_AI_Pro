"""步骤8: 覆盖率计算 + Markdown 报告生成"""
from typing import Dict, Any

from ..graph.state import ReviewState


def calculate_coverage(state: ReviewState) -> Dict[str, Any]:
    """
    对应 Dify: 覆盖率计算 Code 节点
    输入: review_report
    输出: report_text, pass_flag
    """
    print("正在生成评审报告...")

    review_report = state.get("review_report", {})
    checklist = review_report.get("checklist", [])
    summary = review_report.get("summary", "无总体结论")

    total = 18
    passed = sum(1 for item in checklist if item.get("passed", False))

    coverage = round(passed / total, 2) if total else 0
    pass_flag = coverage >= 0.8  # 80% 通过阈值

    # 构建 Markdown 报告
    status_title = (
        "[PASS] **测试用例评审合格**" if pass_flag
        else "[FAIL] **测试用例评审不合格**"
    )

    lines = [
        status_title,
        f"**ISTQB 检查项合规率：** `{passed}/{total}` ({coverage:.0%})\n",
        f"**总体结论：** {summary}\n",
        "### 18 项检查清单",
        "| 检查项 | 状态 | 问题定位 | 修改建议 |",
        "| :--- | :---: | :--- | :--- |",
    ]

    for item in checklist:
        name = item.get("item", "-")
        status = "[PASS]" if item.get("passed", False) else "[FAIL]"
        issue = (item.get("issue") or "无").replace("\n", " ").replace("|", "\\|")
        suggestion = (item.get("suggestion") or "无").replace("\n", " ").replace("|", "\\|")
        lines.append(f"| {name} | {status} | {issue} | {suggestion} |")

    report_text = "\n".join(lines)
    print("  报告生成完成\n")

    return {
        "report_text": report_text,
        "pass_flag": pass_flag,
        "checklist": checklist,
    }
