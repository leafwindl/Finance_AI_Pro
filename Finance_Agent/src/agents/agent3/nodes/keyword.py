"""步骤1: 从结构化用例确定性生成三路检索词（合并原 keyword_parse，直接产出 keywords）。"""
from ..graph.state import ReviewState


def _field(text: str, *labels: str) -> str:
    for line in text.splitlines():
        stripped = line.strip()
        for label in labels:
            prefix = f"{label}："
            if stripped.startswith(prefix):
                return stripped[len(prefix):].strip()
    return ""


def extract_keywords(state: ReviewState) -> dict:
    query = state.get("query", "")
    if not query:
        return {"keywords": {}}

    title = _field(query, "用例名称")
    module = _field(query, "所属模块")
    objective = _field(query, "测试场景/测试点", "测试场景")
    test_data = _field(query, "测试数据与输入条件", "测试数据")
    expected = _field(query, "预期结果")
    base = " ".join(part for part in (module, title, objective) if part).strip()
    keywords = {
        "standard_cases_query": base or query[:240],
        "history_defects_query": " ".join(
            part for part in (module, objective, test_data, expected, "异常 边界 历史缺陷") if part
        ),
        "test_spec_query": " ".join(
            part for part in (module, "ISTQB 测试用例 前置条件 测试数据 预期结果 评审规范") if part
        ),
    }
    return {"keywords": keywords}
