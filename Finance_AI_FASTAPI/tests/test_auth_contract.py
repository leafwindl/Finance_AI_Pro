from contextlib import AbstractAsyncContextManager

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api import auth as auth_module
from app.core.config import Settings, get_settings
from app.data_gateway.pool import get_pool


class AsyncContext(AbstractAsyncContextManager):
    def __init__(self, value, events, label):
        self.value = value
        self.events = events
        self.label = label

    async def __aenter__(self):
        self.events.append(f"{self.label}:enter")
        return self.value

    async def __aexit__(self, exc_type, exc, traceback):
        self.events.append(f"{self.label}:exit")
        return False


class FakeConnection:
    def __init__(self, *, existing=None):
        self.existing = existing
        self.events = []
        self.executed = []

    def transaction(self):
        return AsyncContext(self, self.events, "transaction")

    async def fetchrow(self, query, *args):
        self.events.append("fetchrow")
        return self.existing

    async def execute(self, query, *args):
        self.events.append("execute")
        self.executed.append((query, args))
        return "INSERT 0 1"


class FakePool:
    def __init__(self, connection):
        self.connection = connection
        self.events = connection.events

    def acquire(self):
        return AsyncContext(self.connection, self.events, "acquire")


def build_client(pool) -> TestClient:
    app = FastAPI()
    app.include_router(auth_module.router)
    app.dependency_overrides[get_settings] = lambda: Settings()
    app.dependency_overrides[get_pool] = lambda: pool
    return TestClient(app)


def test_register_creates_user_and_session_in_one_transaction():
    connection = FakeConnection()
    with build_client(FakePool(connection)) as client:
        response = client.post(
            "/api/v1/auth/register",
            json={
                "name": " tester ",
                "email": "TESTER@example.com",
                "password": "123456",
            },
        )

    assert response.status_code == 201
    assert response.json()["user"]["name"] == "tester"
    assert response.json()["user"]["email"] == "tester@example.com"
    assert response.cookies.get("session_id")
    assert connection.events[0:2] == ["acquire:enter", "transaction:enter"]
    assert connection.events[-2:] == ["transaction:exit", "acquire:exit"]
    assert len(connection.executed) == 2


def test_register_rejects_existing_user_without_writes():
    connection = FakeConnection(existing={"user_id": "existing"})
    with build_client(FakePool(connection)) as client:
        response = client.post(
            "/api/v1/auth/register",
            json={
                "name": "tester",
                "email": "tester@example.com",
                "password": "123456",
            },
        )

    assert response.status_code == 409
    assert response.json()["detail"] == "用户名或邮箱已被注册"
    assert connection.executed == []
