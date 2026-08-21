import pytest
from pydantic import ValidationError

from app.core.config import Settings
from app.main import app
from app.schemas.chat import ChatRequest
from app.agent_gateway.registry import build_registry


def test_all_agents_are_enabled():
    # 契约 §4：五个稳定 agent_id
    registry = build_registry(Settings())
    assert set(registry) == {
        "requirement-pre-review",
        "ai-test-analysis",
        "accounting-expert",
        "business-analyst",
        "ai-assistant",
    }
    assert all(agent.enabled for agent in registry.values())
    assert registry["requirement-pre-review"].stateful is True
    assert registry["ai-assistant"].stateful is True
    assert {agent.base_url for agent in registry.values()} == {"http://127.0.0.1:8101"}


def test_chat_request_normalizes_empty_conversation_and_deduplicates_files():
    request = ChatRequest(
        query=" 测试 ",
        conversation_id="",
        agent_id="ai-test-analysis",
        file_ids=["file_1", "file_1"],
    )
    assert request.query == "测试"
    assert request.conversation_id is None
    assert request.file_ids == ["file_1"]


def test_chat_request_rejects_unknown_agent():
    with pytest.raises(ValidationError):
        ChatRequest(query="测试", agent_id="unknown")


def test_openapi_declares_chat_as_sse():
    response = app.openapi()["paths"]["/api/v1/chat"]["post"]["responses"]["200"]
    assert "text/event-stream" in response["content"]
