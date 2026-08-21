from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api import chat as chat_module
from app.api.auth import get_current_user
from app.core.config import Settings, get_settings
from app.data_gateway.pool import get_pool


def build_test_client() -> TestClient:
    app = FastAPI()
    app.include_router(chat_module.router)
    app.dependency_overrides[get_current_user] = lambda: {
        "user_id": "user-1",
        "name": "tester",
        "email": "tester@example.com",
    }
    app.dependency_overrides[get_settings] = lambda: Settings()
    app.dependency_overrides[get_pool] = lambda: object()
    return TestClient(app)


def test_chat_normalizes_agent_stream_and_persists_messages(monkeypatch):
    calls = {"conversation": 0, "user": 0, "assistant": 0}

    async def create_conversation(*args, **kwargs):
        calls["conversation"] += 1

    async def get_files(*args, **kwargs):
        return []

    async def insert_user(*args, **kwargs):
        calls["user"] += 1
        return 10

    async def insert_assistant(*args, **kwargs):
        calls["assistant"] += 1
        assert kwargs["content"] == "完整回答"
        return 11

    class FakeAgentClient:
        def __init__(self, settings):
            self.settings = settings

        async def stream(self, agent, payload):
            assert agent.agent_id == "ai-test-analysis"
            assert payload["agent_id"] == "ai-test-analysis"
            assert payload["thread_id"].startswith("conv_")
            yield "progress", {"node": "retrieve", "message": "检索中"}
            yield "delta", {"text": "完整"}
            yield "delta", {"text": "回答"}
            yield "completed", {"answer": "完整回答", "metadata": {"hits": 2}}

    monkeypatch.setattr(chat_module, "create_conversation", create_conversation)
    monkeypatch.setattr(chat_module, "get_owned_ready_files", get_files)
    monkeypatch.setattr(chat_module, "insert_user_message", insert_user)
    monkeypatch.setattr(chat_module, "insert_assistant_message", insert_assistant)
    monkeypatch.setattr(chat_module, "AgentClient", FakeAgentClient)

    with build_test_client() as client:
        response = client.post(
            "/api/v1/chat",
            json={
                "query": "分析需求",
                "agent_id": "ai-test-analysis",
                "client_message_id": "client-1",
            },
        )

    assert response.status_code == 200
    assert "event: progress" in response.text
    assert response.text.count("event: delta") == 2
    assert "event: completed" in response.text
    assert '"answer": "完整回答"' in response.text
    assert '"conversation_id": "conv_' in response.text
    assert calls == {"conversation": 1, "user": 1, "assistant": 1}


def test_accounting_expert_is_routed_and_persisted(monkeypatch):
    calls = {"conversation": 0, "user": 0, "assistant": 0}

    async def create_conversation(*args, **kwargs):
        calls["conversation"] += 1
        assert kwargs["agent_id"] == "accounting-expert"

    async def get_files(*args, **kwargs):
        return []

    async def insert_user(*args, **kwargs):
        calls["user"] += 1
        return 20

    async def insert_assistant(*args, **kwargs):
        calls["assistant"] += 1
        assert kwargs["content"] == "评审完成"
        assert kwargs["metadata"]["check_count"] == 18
        return 21

    class FakeAgentClient:
        def __init__(self, settings):
            self.settings = settings

        async def stream(self, agent, payload):
            assert agent.agent_id == "accounting-expert"
            assert agent.base_url == "http://127.0.0.1:8101"
            assert payload["agent_id"] == "accounting-expert"
            assert payload["thread_id"].startswith("conv_")
            yield "progress", {"node": "review_generate", "message": "评审中"}
            yield "completed", {
                "answer": "评审完成",
                "metadata": {"pass_flag": True, "check_count": 18},
            }

    monkeypatch.setattr(chat_module, "create_conversation", create_conversation)
    monkeypatch.setattr(chat_module, "get_owned_ready_files", get_files)
    monkeypatch.setattr(chat_module, "insert_user_message", insert_user)
    monkeypatch.setattr(chat_module, "insert_assistant_message", insert_assistant)
    monkeypatch.setattr(chat_module, "AgentClient", FakeAgentClient)

    with build_test_client() as client:
        response = client.post(
            "/api/v1/chat",
            json={
                "query": "评审用例",
                "agent_id": "accounting-expert",
                "client_message_id": "agent-3-message",
            },
        )

    assert response.status_code == 200
    assert "event: progress" in response.text
    assert "event: delta" in response.text
    assert "event: completed" in response.text
    assert '"answer": "评审完成"' in response.text
    assert calls == {"conversation": 1, "user": 1, "assistant": 1}


def test_duplicate_client_message_is_rejected(monkeypatch):
    async def create_conversation(*args, **kwargs):
        return None

    async def get_files(*args, **kwargs):
        return []

    async def duplicate(*args, **kwargs):
        return None

    monkeypatch.setattr(chat_module, "create_conversation", create_conversation)
    monkeypatch.setattr(chat_module, "get_owned_ready_files", get_files)
    monkeypatch.setattr(chat_module, "insert_user_message", duplicate)

    with build_test_client() as client:
        response = client.post(
            "/api/v1/chat",
            json={
                "query": "重复请求",
                "agent_id": "business-analyst",
                "client_message_id": "same-id",
            },
        )

    assert response.status_code == 409


def test_invalid_attachment_does_not_leave_empty_conversation(monkeypatch):
    created = 0

    async def create_conversation(*args, **kwargs):
        nonlocal created
        created += 1

    async def no_owned_files(*args, **kwargs):
        return []

    monkeypatch.setattr(chat_module, "create_conversation", create_conversation)
    monkeypatch.setattr(chat_module, "get_owned_ready_files", no_owned_files)

    with build_test_client() as client:
        response = client.post(
            "/api/v1/chat",
            json={
                "query": "尝试引用其他用户附件",
                "agent_id": "ai-test-analysis",
                "file_ids": ["file_not_owned"],
            },
        )

    assert response.status_code == 404
    assert created == 0


def test_stream_error_returns_conversation_id_for_safe_retry(monkeypatch):
    failed = []

    async def create_conversation(*args, **kwargs):
        return None

    async def get_files(*args, **kwargs):
        return []

    async def insert_user(*args, **kwargs):
        return 10

    async def mark_failed(*args, **kwargs):
        failed.append(kwargs["error_code"])

    class FailingAgentClient:
        def __init__(self, settings):
            self.settings = settings

        async def stream(self, agent, payload):
            yield "error", {
                "code": "knowledge_base_unavailable",
                "message": "知识库暂不可用",
                "retryable": True,
            }

    monkeypatch.setattr(chat_module, "create_conversation", create_conversation)
    monkeypatch.setattr(chat_module, "get_owned_ready_files", get_files)
    monkeypatch.setattr(chat_module, "insert_user_message", insert_user)
    monkeypatch.setattr(chat_module, "mark_request_failed", mark_failed)
    monkeypatch.setattr(chat_module, "AgentClient", FailingAgentClient)

    with build_test_client() as client:
        response = client.post(
            "/api/v1/chat",
            json={
                "query": "分析需求",
                "agent_id": "ai-test-analysis",
                "client_message_id": "client-error-1",
            },
        )

    assert response.status_code == 200
    assert "event: error" in response.text
    assert '"conversation_id": "conv_' in response.text
    assert '"code": "knowledge_base_unavailable"' in response.text
    assert failed == ["knowledge_base_unavailable"]
