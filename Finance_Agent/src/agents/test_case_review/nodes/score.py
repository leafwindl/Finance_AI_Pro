"""步骤8: 覆盖率计算 + Markdown 报告"""
from ..state import ReviewState


def calculate_coverage(state: ReviewState) -> dict:
    print("正在生成评审报告...")

    review_report = state.get("review_report", {})
    checklist = review_report.get("checklist", [])
    summary = review_report.get("summary", "无总体结论")

    total = 18
    passed = sum(1 for item in checklist if item.get("passed", False))
    coverage = round(passed / total, 2) if total else 0
    pass_flag = coverage >= 0.8

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
        status = "✅ PASS" if item.get("passed", False) else "❌ FAIL"
        issue = (item.get("issue") or "无").replace("\n", " ").replace("|", "\\|")
        suggestion = (item.get("suggestion") or "无").replace("\n", " ").replace("|", "\\|")
        lines.append(f"| {name} | {status} | {issue} | {suggestion} |")

    report_text = "\n".join(lines)
    print(f"  覆盖率: {coverage:.0%}, {'合格' if pass_flag else '不合格'}\n")

    return {
        "report_text": report_text,
        "pass_flag": pass_flag,
        "checklist": checklist,
    }
