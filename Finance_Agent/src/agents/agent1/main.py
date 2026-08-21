"""
需求预评审智能体 - 流水线调用入口

使用方法:
    python main.py
    或
    python main.py --input "需求描述文本"
    或
    python main.py --file requirements.txt

流水线模式:
    用户一次性输入完整需求描述 → 系统自动执行全流程 → 输出完整预评审报告
    无对话交互、无多轮确认。
"""

import asyncio
import argparse
import sys

from graph.workflow import app


def print_banner():
    """打印横幅"""
    print()
    print("=" * 55)
    print("  证券需求预评审智能体 (报告生成模式)")
    print("  输入完整需求描述，自动生成预评审报告")
    print("=" * 55)
    print()


async def run_pipeline(requirement_text: str, file_path: str = None) -> dict:
    """
    执行完整的预评审流水线。

    Args:
        requirement_text: 用户输入的需求描述文本
        file_path: 可选的文件路径，读取文件内容作为补充

    Returns:
        dict: 最终状态, 包含 final_report
    """
    file_content = ""
    file_name = ""

    # 如果提供了文件路径, 读取文件内容
    if file_path:
        try:
            from utils.file_reader import extract_text
            with open(file_path, "rb") as f:
                file_bytes = f.read()
            file_content = extract_text(file_bytes, file_path)
            file_name = file_path
            print(f"[入口] 已读取文件: {file_path} ({len(file_content)} 字符)")
        except FileNotFoundError:
            print(f"[入口] [警告] 文件不存在: {file_path}")
        except Exception as e:
            print(f"[入口] [警告] 文件读取失败: {e}")

    # 构造初始状态
    state = {
        "requirement_input": requirement_text,
        "file_content": file_content,
        "file_name": file_name,
    }

    print(f"[入口] 需求文本长度: {len(requirement_text)} 字符")
    print(f"[入口] 开始执行预评审流水线...\n")

    # 执行流水线
    result = await app.ainvoke(state)

    return result


def print_report(result: dict):
    """打印最终报告"""
    final_output = result.get("final_output", result.get("final_report", ""))

    print()
    print("=" * 55)
    if not final_output:
        print("  [警告] 未能生成报告，请检查输入和日志")
    else:
        print(final_output)
    print("=" * 55)
    print()


async def main():
    parser = argparse.ArgumentParser(
        description="证券需求预评审智能体 - 自动生成预评审报告"
    )
    parser.add_argument(
        "--input", "-i",
        type=str,
        help="需求描述文本（直接在命令行中传入）",
    )
    parser.add_argument(
        "--file", "-f",
        type=str,
        help="需求文档文件路径（.txt / .md / .docx / .pdf）",
    )
    args = parser.parse_args()

    print_banner()

    # 优先使用命令行参数
    if args.input:
        requirement_text = args.input
    elif args.file:
        # 从文件读取
        try:
            with open(args.file, "r", encoding="utf-8") as f:
                requirement_text = f.read()
        except UnicodeDecodeError:
            with open(args.file, "r", encoding="gbk", errors="replace") as f:
                requirement_text = f.read()
    else:
        # 交互式输入: 让用户一次性输入完整需求
        print("请输入完整的需求描述 (输入完成后按 Ctrl+Z 然后回车, 或输入 /done 结束):")
        print()
        lines = []
        while True:
            try:
                line = input()
                if line.strip() == "/done":
                    break
                lines.append(line)
            except EOFError:
                break
        requirement_text = "\n".join(lines)

    if not requirement_text or not requirement_text.strip():
        print("[失败] 未提供需求描述，无法执行。")
        print("   用法: python main.py --input \"需求描述文本\"")
        print("   或:   python main.py --file requirements.txt")
        sys.exit(1)

    # 执行流水线
    result = await run_pipeline(
        requirement_text.strip(),
        file_path=args.file,
    )

    # 打印报告
    print_report(result)

    # 检查风险等级
    risk_analysis = result.get("risk_analysis", {})
    if risk_analysis:
        risk_level = risk_analysis.get("overall_risk_level", "N/A")
        print(f"[风险等级] {risk_level}")
        key_concerns = risk_analysis.get("key_concerns", [])
        if key_concerns:
            print(f"[重点关注] {len(key_concerns)} 项")
            for concern in key_concerns:
                print(f"  - {concern}")

    # 检查信息完整度
    six_points = result.get("six_points", {})
    if six_points:
        completeness = six_points.get("completeness_score", "N/A")
        missing = six_points.get("missing_items", [])
        print(f"[信息完整度] {completeness}%")
        if missing:
            print(f"[缺失项] {len(missing)} 项")


if __name__ == "__main__":
    asyncio.run(main())
