"""
需求预评审智能体 - LangGraph 图编排 (流水线版本)

重构说明:
    从"多轮对话式需求澄清"改为"自动化需求预评审报告生成"。
    图结构从复杂的条件路由图变为线性流水线:
    START → 需求解析 → 关键词提取 → KB路由 → 知识检索 → 六大要点评估 → 风险评估 → 报告生成 → END

=============================================================
图结构概览:
=============================================================

START
  │
  ▼
┌─────────────────────────┐
│ 1. requirement_parser    │  需求解析节点
│    理解+结构化需求         │
└──────────┬──────────────┘
           ▼
┌─────────────────────────┐
│ 2. keyword_extractor     │  关键词提取 (保留)
│    提取多领域关键词        │
└──────────┬──────────────┘
           ▼
┌─────────────────────────┐
│ 3. kb_router             │  知识库路由 (保留)
│    分配检索查询词          │
└──────────┬──────────────┘
           ▼
┌─────────────────────────┐
│ 4. knowledge_retrieval   │  知识库检索 (保留)
│    并行检索多个KB         │
└──────────┬──────────────┘
           ▼
┌─────────────────────────┐
│ 5. six_points_eval       │  六大要点评估
│    自动生成6维度评估       │
└──────────┬──────────────┘
           ▼
┌─────────────────────────┐
│ 6. risk_assessment       │  风险评估
│    四维度风险分析          │
└──────────┬──────────────┘
           ▼
┌─────────────────────────┐
│ 7. report_generator      │  报告生成
│    输出完整预评审报告       │
└──────────┬──────────────┘
           ▼
          END
"""

from langgraph.graph import StateGraph, START, END

from ..state import RequirementState

# 导入所有节点函数
from ..nodes.requirement_parser import requirement_parser
from ..nodes.keyword_extractor import extract_keywords
from ..nodes.kb_router import route_keywords_to_kb
from ..nodes.knowledge_retrieval import knowledge_retrieval
from ..nodes.six_points_eval import six_points_eval
from ..nodes.risk_assessment import risk_assessment
from ..nodes.report_generator import report_generator


# ================================================================
# 构建 StateGraph (线性流水线, 无条件路由)
# ================================================================

def build_graph(checkpointer=None) -> StateGraph:
    """
    构建需求预评审智能体的 LangGraph 图 (流水线版本)。

    这是一个纯线性流水线:
        需求输入 → 解析 → 关键词 → 知识检索 → 六大要点 → 风险评估 → 报告 → 输出

    没有条件分支、没有用户交互循环、没有对话状态管理。

    Args:
        checkpointer: 可选的检查点存储器 (用于状态持久化)

    Returns:
        已编译的 LangGraph StateGraph 实例
    """

    # ---- 1. 创建图 ----
    graph = StateGraph(RequirementState)

    # ---- 2. 添加所有节点 (按流水线顺序) ----
    # 第1步: 需求解析
    graph.add_node("requirement_parser", requirement_parser)

    # 第2步: 关键词提取 (保留原有能力)
    graph.add_node("keyword_extractor", extract_keywords)

    # 第3步: 知识库路由 (保留原有能力)
    graph.add_node("kb_router", route_keywords_to_kb)

    # 第4步: 知识库检索 (保留原有能力)
    graph.add_node("knowledge_retrieval", knowledge_retrieval)

    # 第5步: 六大要点评估 (新)
    graph.add_node("six_points_eval", six_points_eval)

    # 第6步: 风险评估 (新)
    graph.add_node("risk_assessment", risk_assessment)

    # 第7步: 报告生成 (新)
    graph.add_node("report_generator", report_generator)

    # ---- 3. 构建线性流水线边 ----
    # START → 需求解析
    graph.add_edge(START, "requirement_parser")

    # 需求解析 → 关键词提取
    graph.add_edge("requirement_parser", "keyword_extractor")

    # 关键词提取 → KB路由
    graph.add_edge("keyword_extractor", "kb_router")

    # KB路由 → 知识库检索
    graph.add_edge("kb_router", "knowledge_retrieval")

    # 知识库检索 → 六大要点评估
    graph.add_edge("knowledge_retrieval", "six_points_eval")

    # 六大要点评估 → 风险评估
    graph.add_edge("six_points_eval", "risk_assessment")

    # 风险评估 → 报告生成
    graph.add_edge("risk_assessment", "report_generator")

    # 报告生成 → END
    graph.add_edge("report_generator", END)

    # ---- 4. 编译 ----
    return graph.compile(checkpointer=checkpointer)


# ================================================================
# 创建 App 实例 (供 main.py / server.py 导入)
# ================================================================

app = build_graph()
