from dataclasses import dataclass

from app.core.config import Settings


@dataclass(frozen=True)
class AgentDefinition:
    agent_id: str
    name: str
    base_url: str
    enabled: bool
    stateful: bool = False


def build_registry(settings: Settings) -> dict[str, AgentDefinition]:
    base_url = settings.agent_platform_url.rstrip("/")
    return {
        "requirement-pre-review": AgentDefinition(
            "requirement-pre-review",
            "需求预评审智能体",
            base_url,
            True,
            True,
        ),
        "ai-test-analysis": AgentDefinition(
            "ai-test-analysis",
            "需求 AI 测试分析智能体",
            base_url,
            True,
        ),
        "accounting-expert": AgentDefinition(
            "accounting-expert",
            "测试用例评审智能体",
            base_url,
            True,
        ),
        "business-analyst": AgentDefinition(
            "business-analyst",
            "测试步骤生成智能体",
            base_url,
            True,
        ),
        "ai-assistant": AgentDefinition(
            "ai-assistant",
            "智能对话助手",
            base_url,
            True,
            # 契约 §4：ai-assistant 有状态（多轮记忆，见 §8）
            True,
        ),
    }
