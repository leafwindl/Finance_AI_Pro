"""
需求分析智能体 — Prompt 模板
"""

KEYWORD_EXTRACTION_PROMPT = """你是测试分析专家，从需求文档中提取三维关键词。

1. biz_keywords（业务类）：核心操作、功能模块
2. test_keywords（测试类）：测试类型、质量属性
3. regulatory_keywords（法规类）：合规规则、监管要求

严格JSON输出：
{{
    "biz_keywords": "...",
    "test_keywords": "...",
    "regulatory_keywords": "...",
    "kb_code_list": ["KB01", ...]
}}

需求文档：{input_text}"""


RAG_RESPONSE_PROMPT = """你是资深测试分析师，基于检索到的知识库内容，对需求进行六维分析。

## 需求文档
{input_text}

## 知识库参考
{aggregated_context}

## 分析维度
1. 业务理解 — 需求核心业务梳理
2. 测试范围 — 需要覆盖的测试范围
3. 风险识别 — 潜在业务/技术/合规风险
4. 测试策略 — 建议的测试方法
5. 资源评估 — 人力/时间/数据评估
6. 质量目标 — 验收标准建议

请输出Markdown格式的完整分析报告。"""


CHAT_RESPONSE_PROMPT = """你是测试分析助手。用户输入不包含有效业务关键词，请友好回复。"""
