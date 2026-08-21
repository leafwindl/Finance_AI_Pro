"""
智能测试分析助手
  CLI 交互:  python main.py
  CLI 管道:  python main.py - < input.txt
  前端 API:  from main import chat; await chat("问题")
"""

from .loader import bootstrap
bootstrap()

from .cli import main, chat  # noqa: E402, F401  — chat 保持向后兼容

if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
