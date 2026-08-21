"""
模块化检索 Agent (Modular Retrieval Agent)

模块:
  cli                 — chat() 公开 API + CLI 交互
  loader              — 环境初始化 + 知识库加载
  kb_client           — 下游 KB REST API 客户端

图:
  core/graph.py       — LangGraph 图编排（extract_keywords → convert_keywords → retrieve_all → rag_response）

节点:
  handlers/keyword_extractor.py  — LLM 关键词提取
  handlers/keyword_converter.py  — 关键词拆分与兜底
  handlers/retriever.py          — 混合检索 + 分库并行
  handlers/llm_handler.py        — RAG 六维分析 / 闲聊
  handlers/output_handler.py     — 响应提取
"""
