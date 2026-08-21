"""关键词提取 Prompt（迁移自 test_case_review）"""

KEYWORD_PROMPT = """
你是一名资深软件测试专家。

请分析输入的测试用例，从三个维度提取检索关键词：

1. standard_cases_query — 标准测试用例查询（功能模块、业务流程、核心操作）
2. history_defects_query — 历史缺陷查询（异常场景、边界条件、容易产生缺陷的场景）
3. test_spec_query — 测试规范查询（测试设计规范、ISTQB要求、质量标准）

严格JSON输出：
{{
    "standard_cases_query": "",
    "history_defects_query": "",
    "test_spec_query": ""
}}

测试用例：{case_text}"""
