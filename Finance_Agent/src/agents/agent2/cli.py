"""
CLI 与前端 API — chat() / CLI 交互 / 入口 main()
"""

import sys

from langchain_core.messages import HumanMessage

from .loader import default_loader
from .core.graph import agent_graph
from .handlers.output_handler import OutputHandler


# ---- 前端 API ----
async def chat(query: str, *, user_id: str = "default") -> str:
    """供外部 import 调用的 API：from modular_agent.cli import chat; await chat("问题")"""
    default_loader.load()
    state = {"messages": [HumanMessage(content=query)]}
    result = await agent_graph.ainvoke(state, config={"configurable": {"user_id": user_id}})
    return OutputHandler.extract_response(result)


# ---- CLI ----
async def _cli_once(question: str) -> None:
    default_loader.load()
    result = await agent_graph.ainvoke(
        {"messages": [HumanMessage(content=question)]},
        config={"configurable": {"user_id": "default"}},
    )
    OutputHandler.print_result(result)


async def _cli_loop() -> None:
    default_loader.load()
    print("智能测试分析助手（Ctrl+C 停止）\n")
    while True:
        try:
            q = input("> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break
        if not q:
            continue
        result = await agent_graph.ainvoke(
            {"messages": [HumanMessage(content=q)]},
            config={"configurable": {"user_id": "default"}},
        )
        OutputHandler.print_result(result)


async def main() -> None:
    if len(sys.argv) > 1:
        arg = sys.argv[1]
        if arg == "-":
            q = sys.stdin.read().strip()
            if q:
                await _cli_once(q)
        else:
            await _cli_once(" ".join(sys.argv[1:]))
    else:
        await _cli_loop()
