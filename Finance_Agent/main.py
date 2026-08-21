"""
智能测试全流程平台 — 统一入口

用法：
  全流程:  python main.py pipeline --input "需求文本"
  单智能体: python main.py agent --name agent1 --input "需求文本"
  API服务:  python -m src.api.server
"""
import argparse
import asyncio
import sys
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve()
sys.path.insert(0, str(_PROJECT_ROOT))

# 让 4 个 Agent 保持原版导入路径（agent5 走 API，不进 CLI 管线）
_AGENTS_DIR = _PROJECT_ROOT / "src" / "agents"
sys.path.insert(0, str(_AGENTS_DIR / "agent1"))
sys.path.insert(0, str(_AGENTS_DIR / "agent2"))
sys.path.insert(0, str(_AGENTS_DIR / "agent3"))
sys.path.insert(0, str(_AGENTS_DIR / "agent4"))

from dotenv import load_dotenv
load_dotenv(_PROJECT_ROOT / ".env")


def build_parser():
    parser = argparse.ArgumentParser(description="智能测试全流程平台")
    sub = parser.add_subparsers(dest="command", help="子命令")

    pipe = sub.add_parser("pipeline", help="运行全流程")
    pipe.add_argument("--input", "-i", required=True, help="需求文本")
    pipe.add_argument("--skip-review", action="store_true",
                      help="跳过需求评审")

    ag = sub.add_parser("agent", help="运行单个智能体")
    ag.add_argument("--name", "-n", required=True,
                    choices=["agent1", "agent2",
                             "agent3", "agent4"],
                    help="智能体名称")
    ag.add_argument("--input", "-i", required=True, help="输入文本")

    return parser


async def run_pipeline(input_text: str, skip_review: bool = False):
    from src.pipeline.orchestrator import FullPipeline
    pipeline = FullPipeline()
    result = await pipeline.run(input_text, skip_review=skip_review)
    return result


async def run_single_agent(name: str, input_text: str):
    if name == "agent1":
        from src.agents.agent1.graph.workflow import build_graph as build_review_graph
        app = build_review_graph()
        state = {"requirement_input": input_text, "file_content": "", "file_name": ""}
        result = await app.ainvoke(state)
        return result.get("final_output", "")

    elif name == "agent2":
        from src.agents.agent2.loader import default_loader
        from src.agents.agent2.core.graph import agent_graph
        from langchain_core.messages import HumanMessage

        default_loader.load()
        result = await agent_graph.ainvoke(
            {"messages": [HumanMessage(content=input_text)]}
        )
        return result.get("aggregated_context", "")

    elif name == "agent3":
        from src.agents.agent3.graph.workflow import build_graph as build_case_graph
        graph = build_case_graph()
        result = await graph.ainvoke({"query": input_text})
        return result.get("report_text", "")

    elif name == "agent4":
        # agent4 内部用 modules. 绝对导入，依赖 sys.path 已有 agent4 目录
        from modules.workflow.graph import build_workflow_graph
        graph = build_workflow_graph()
        result = await graph.ainvoke({
            "query": input_text, "test_case": None, "doc_content": "",
            "kb_keywords": {}, "kb_task_list": [], "rag_docs": [],
            "llm_json_raw": "", "parse_data": None,
            "is_success": 0, "output_text": "",
            "error_msg": "", "progress_msg": "",
        })
        return result.get("output_text", "")


if __name__ == "__main__":
    parser = build_parser()
    args = parser.parse_args()

    if args.command == "pipeline":
        result = asyncio.run(run_pipeline(args.input, args.skip_review))
        print("\n" + "=" * 60)
        print("  全流程执行完毕")
        print("=" * 60)
        for phase, output in result.items():
            print(f"\n--- {phase} ---")
            print(str(output)[:500])

    elif args.command == "agent":
        result = asyncio.run(run_single_agent(args.name, args.input))
        print("\n" + "=" * 60)
        print(f"  智能体 [{args.name}] 执行完毕")
        print("=" * 60)
        print(str(result)[:2000])

    else:
        parser.print_help()
