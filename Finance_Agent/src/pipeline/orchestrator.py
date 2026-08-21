"""
全流程编排器 — 串联主流程 4 个智能体（agent1~4），均使用原版 Agent 代码

流程:
 ② 需求评审 → ⑦ 需求分析 → ⑩ 用例评审 → ⑬ 步骤生成
（②⑦⑩⑬ 为原版内部编号；agent5 对话助手不走此管线，由 API/前端单独调用）
"""
import asyncio
import sys
from dataclasses import dataclass, field
from pathlib import Path

# 让 4 个 Agent 保持原版导入路径（agent5 不走全流程管线）
_AGENTS_DIR = Path(__file__).resolve().parent / "agents"
sys.path.insert(0, str(_AGENTS_DIR / "agent1"))
sys.path.insert(0, str(_AGENTS_DIR / "agent2"))
sys.path.insert(0, str(_AGENTS_DIR / "agent3"))
sys.path.insert(0, str(_AGENTS_DIR / "agent4"))


@dataclass
class PipelineResult:
    """全流程执行结果"""
    requirement_spec: str = ""
    test_analysis: str = ""
    review_report: str = ""
    review_pass: bool = False
    review_coverage: float = 0.0
    test_steps: str = ""
    errors: list[str] = field(default_factory=list)


class FullPipeline:
    """串联主流程 4 个智能体（agent1~4）的全流程管线；agent5 由 API/前端单独调用"""

    async def run(self, input_text: str, skip_review: bool = False) -> dict:
        result = PipelineResult()

        # ================================================================
        # 阶段 ②: 需求评审智能体 — 流水线版本 Agent(1)
        # ================================================================
        print("=" * 60)
        print("  阶段 ②: 需求评审智能体")
        print("=" * 60)
        try:
            from src.agents.agent1.graph.workflow import build_graph as build_review_graph

            app = build_review_graph()
            # 新流水线版本: 一次性输入, 直接生成完整预评审报告
            state = {"requirement_input": input_text}
            final_state = await app.ainvoke(state)
            result.requirement_spec = final_state.get("final_report",
                                          final_state.get("final_output", ""))
            print("  [OK] 预评审报告已生成")
        except Exception as e:
            result.errors.append(f"需求评审失败: {e}")
            print(f"  [失败] 需求评审失败: {e}")

        if skip_review:
            result.requirement_spec = input_text

        # ================================================================
        # 阶段 ⑦: 需求AI测试分析智能体 — 原版 Requirements Test Analysis Agent
        # ================================================================
        print("\n" + "=" * 60)
        print("  阶段 ⑦: 需求AI测试分析智能体")
        print("=" * 60)
        try:
            from src.agents.agent2.loader import default_loader
            from src.agents.agent2.core.graph import agent_graph
            from langchain_core.messages import HumanMessage

            default_loader.load()
            analysis_input = result.requirement_spec or input_text
            analysis_result = await agent_graph.ainvoke(
                {"messages": [HumanMessage(content=analysis_input)]}
            )
            # `aggregated_context` 是知识库检索原文，不是六维报告；
            # 最终报告由 rag_response/chat_response 写入最后一条 AI 消息
            # （与 src/api/server.py `_stream_requirement_analysis` 的取法一致）
            messages = analysis_result.get("messages") or []
            answer = ""
            if messages:
                content = getattr(messages[-1], "content", "")
                if isinstance(content, str):
                    answer = content
                elif isinstance(content, list):
                    answer = "".join(
                        item.get("text", "") if isinstance(item, dict) else str(item)
                        for item in content
                    )
                else:
                    answer = str(content)
            result.test_analysis = answer
            print("  [OK] 测试分析报告已生成")
        except Exception as e:
            result.errors.append(f"需求分析失败: {e}")
            print(f"  [失败] 需求分析失败: {e}")

        # ================================================================
        # 阶段 ⑩: 测试用例评审智能体 — 原版 Intelligent Test Case Review Agent
        # ================================================================
        print("\n" + "=" * 60)
        print("  阶段 ⑩: 测试用例评审智能体")
        print("=" * 60)
        try:
            from src.agents.agent3.graph.workflow import build_graph as build_case_graph

            review_input = result.test_analysis or input_text
            graph = build_case_graph()
            review_result = await graph.ainvoke({"query": review_input})
            result.review_report = review_result.get("report_text", "")
            result.review_pass = review_result.get("pass_flag", False)
            checklist = review_result.get("checklist", [])
            passed_count = sum(1 for c in checklist if c.get("passed"))
            result.review_coverage = passed_count / 18 if checklist else 0
            print(f"  {'[OK] 评审通过' if result.review_pass else '[失败] 评审未通过'} "
                  f"(覆盖率: {result.review_coverage:.0%})")
        except Exception as e:
            result.errors.append(f"用例评审失败: {e}")
            print(f"  [失败] 用例评审失败: {e}")

        # ---- 评审不通过 → 停止，不继续 agent4 ----
        if not result.review_pass and not result.errors:
            print("\n  [终止] 用例评审未通过，跳过步骤生成，请修改用例后重新评审。")
            return {
                "requirement_spec": result.requirement_spec,
                "test_analysis": result.test_analysis,
                "review_report": result.review_report,
                "review_pass": result.review_pass,
                "review_coverage": result.review_coverage,
                "test_steps": "",
                "errors": result.errors,
            }

        # ================================================================
        # 阶段 ⑬: 测试步骤生成智能体 — 原版 Agent_4-main(1)
        # ================================================================
        print("\n" + "=" * 60)
        print("  阶段 ⑬: 测试步骤生成智能体")
        print("=" * 60)
        try:
            from modules.workflow.graph import build_workflow_graph

            gen_input = result.test_analysis or input_text
            graph = build_workflow_graph()
            gen_result = await graph.ainvoke({
                "query": gen_input, "test_case": None, "doc_content": "",
                "kb_keywords": {}, "kb_task_list": [], "rag_docs": [],
                "llm_json_raw": "", "parse_data": None,
                "is_success": 0, "output_text": "",
                "error_msg": "", "progress_msg": "",
            })
            result.test_steps = gen_result.get("output_text", "")
            print("  [OK] 测试步骤文档已生成")
        except Exception as e:
            result.errors.append(f"步骤生成失败: {e}")
            print(f"  [失败] 步骤生成失败: {e}")

        print("\n" + "=" * 60)
        print("  全流程执行完毕")
        print("=" * 60)
        if result.errors:
            print(f"  [警告]  {len(result.errors)} 个错误: {result.errors}")

        return {
            "requirement_spec": result.requirement_spec,
            "test_analysis": result.test_analysis,
            "review_report": result.review_report,
            "review_pass": result.review_pass,
            "review_coverage": result.review_coverage,
            "test_steps": result.test_steps,
            "errors": result.errors,
        }
