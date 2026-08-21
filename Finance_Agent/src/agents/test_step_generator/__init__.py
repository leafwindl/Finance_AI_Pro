"""
⑬ 测试步骤生成智能体 — 关键词提取 × KB检索 × LLM生成详细步骤

输入: 评审通过的测试用例标题
流程: 关键词提取 → 路由KB → 知识检索 → LLM生成JSON → 解析 → 成功/失败分支
输出: 详细测试步骤文档
"""
from .graph import build_workflow_graph

__all__ = ["build_workflow_graph"]
