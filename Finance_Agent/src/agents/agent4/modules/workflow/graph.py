from langgraph.graph import StateGraph, START, END
from modules.state.state_def import WorkflowState
from modules.workflow.nodes import (
    extract_keyword_node,
    kb_route_node,
    llm_gen_json_node,
    json_to_python_node,
    gen_markdown_node,
    gen_error_node
)
from modules.rag.nodes import knowledge_retrieve_node


# 条件路由函数
def route_after_json_parse(state: WorkflowState) -> str:
    if state["is_success"] == 1:
        return "gen_markdown_node"      # 成功 → 先转markdown
    return "gen_error_node"


def build_workflow_graph():
    # 初始化图，绑定状态
    graph_builder = StateGraph(WorkflowState)

    # 注册所有节点
    graph_builder.add_node("extract_keyword_node", extract_keyword_node)
    graph_builder.add_node("kb_route_node", kb_route_node)
    graph_builder.add_node("knowledge_retrieve_node", knowledge_retrieve_node)
    graph_builder.add_node("llm_gen_json_node", llm_gen_json_node)
    graph_builder.add_node("json_to_python_node", json_to_python_node)
    graph_builder.add_node("gen_markdown_node", gen_markdown_node)
    graph_builder.add_node("gen_error_node", gen_error_node)

    # 搭建主线流程
    graph_builder.add_edge(START, "extract_keyword_node")
    graph_builder.add_edge("extract_keyword_node", "kb_route_node")
    graph_builder.add_edge("kb_route_node", "knowledge_retrieve_node")
    graph_builder.add_edge("knowledge_retrieve_node", "llm_gen_json_node")
    graph_builder.add_edge("llm_gen_json_node", "json_to_python_node")

    # 分支路由
    graph_builder.add_conditional_edges(
        source="json_to_python_node",
        path=route_after_json_parse,
        path_map={
            "gen_markdown_node": "gen_markdown_node",
            "gen_error_node": "gen_error_node"
        }
    )

    # markdown 直接输出结束
    graph_builder.add_edge("gen_markdown_node", END)
    graph_builder.add_edge("gen_error_node", END)

    # 编译图
    graph = graph_builder.compile()
    return graph