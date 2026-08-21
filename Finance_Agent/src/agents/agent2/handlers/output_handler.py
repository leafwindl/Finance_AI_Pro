"""输出模块 — OutputHandler 封装响应提取与 CLI 输出"""

from ..core.state import AgentState


class OutputHandler:
    """输出处理器：从 AgentState 中提取响应，并格式化输出到 CLI。"""

    @staticmethod
    def extract_response(state: AgentState) -> str:
        """从 agent 状态中提取最终回复文本。"""
        for msg in reversed(state.get("messages", [])):
            if msg.type == "ai":
                return str(msg.content)
        return ""

    @staticmethod
    def print_result(state: AgentState, verbose: bool = False) -> None:
        """将 agent 结果格式化输出到 CLI。"""
        msgs = state.get("messages", [])
        user = [m for m in msgs if m.type == "human"]
        if user:
            print(f"\n> {user[-1].content}")

        resp = OutputHandler.extract_response(state)
        print(f"\n{resp}\n" if resp else "\n(未生成回复)\n")

        if verbose:
            OutputHandler._print_debug(state)

    @staticmethod
    def _print_debug(state: AgentState) -> None:
        """verbose 模式：输出调试信息。"""
        biz = state.get("biz_result", [])
        test_p = state.get("test_practice_result", [])
        test_s = state.get("test_standard_result", [])
        reg = state.get("regulatory_result", [])
        total = len(biz) + len(test_p) + len(test_s) + len(reg)
        print(f"[调试] 检索到 {total} 篇 (业务:{len(biz)} 测试实操:{len(test_p)} 测试制度:{len(test_s)} 法规:{len(reg)})")
        for label, docs in [("业务库", biz), ("测试实操库", test_p), ("测试制度库", test_s), ("法规库", reg)]:
            for d in docs:
                src = d.metadata.get("source", d.metadata.get("filename", "?"))
                print(f"  [{label}] {src} | {d.page_content[:60]}...")
