from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api import conversations as conversations_module
from app.api.auth import get_current_user
from app.core.config import Settings, get_settings
from app.data_gateway.pool import get_pool


def build_client() -> TestClient:
    app = FastAPI()
    app.include_router(conversations_module.router)
    app.dependency_overrides[get_current_user] = lambda: {
        "user_id": "user-1",
        "name": "tester",
        "email": "tester@example.com",
    }
    app.dependency_overrides[get_settings] = lambda: Settings()
    app.dependency_overrides[get_pool] = lambda: object()
    return TestClient(app)


def test_conversation_list_is_scoped_to_current_user(monkeypatch):
    captured = {}

    async def list_owned(pool, *, user_id, agent_id, limit):
        captured.update(user_id=user_id, agent_id=agent_id, limit=limit)
        return []

    monkeypatch.setattr(
        conversations_module,
        "list_owned_conversations",
        list_owned,
    )

    with build_client() as client:
        response = client.get(
            "/api/v1/conversations",
            params={"agent_id": "ai-test-analysis", "limit": 50},
        )

    assert response.status_code == 200
    assert response.json() == {"conversations": []}
    assert captured == {
        "user_id": "user-1",
        "agent_id": "ai-test-analysis",
        "limit": 50,
    }


def test_messages_from_another_user_are_reported_as_not_found(monkeypatch):
    async def no_owned_messages(pool, *, user_id, conversation_id):
        return None

    monkeypatch.setattr(
        conversations_module,
        "list_owned_messages",
        no_owned_messages,
    )

    with build_client() as client:
        response = client.get("/api/v1/conversations/conv_not_owned/messages")

    assert response.status_code == 404
    assert response.json()["detail"] == "会话不存在"
