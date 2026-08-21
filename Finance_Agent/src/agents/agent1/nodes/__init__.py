"""
需求预评审智能体 - 节点模块 (流水线版本)

流水线节点列表:
    1. requirement_parser  - 需求解析
    2. keyword_extractor   - 关键词提取
    3. kb_router           - 知识库路由
    4. knowledge_retrieval - 知识库检索
    5. six_points_eval     - 六大要点评估
    6. risk_assessment     - 风险评估
    7. report_generator    - 报告生成

辅助模块:
    llm_config            - LLM 配置
"""
