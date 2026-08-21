from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api import knowledge as knowledge_module
from app.api.auth import get_current_user
from app.core.config import Settings, get_settings
from app.data_gateway.kb_pool import get_kb_pool
from app.graph_gateway.neo4j import get_driver


def build_client() -> TestClient:
    app = FastAPI()
    app.include_router(knowledge_module.router)
    app.dependency_overrides[get_current_user] = lambda: {
        "user_id": "user-1",
        "name": "tester",
        "email": "tester@example.com",
    }
    app.dependency_overrides[get_settings] = lambda: Settings()
    app.dependency_overrides[get_kb_pool] = lambda: object()
    app.dependency_overrides[get_driver] = lambda: object()
    return TestClient(app)


def test_graph_returns_nodes_and_links(monkeypatch):
    async def fake_driver():
        return object()

    async def fake_fetch_graph(driver):
        assert driver is not None
        return {
            "nodes": [
                {"id": "kb__KB01", "type": "kb", "kb_code": "KB01",
                 "label": "系统业务知识库", "count": 2},
                {"id": "doc__a" * 12, "type": "doc", "doc_id": "a" * 24,
                 "kb_code": "KB01", "label": "文档一", "source_file": "KB01/x.md"},
            ],
            "links": [{"source": "kb__KB01", "target": "doc__" + "a" * 24, "type": "CONTAINS"}],
            "meta": {"total_nodes": 2, "total_links": 1, "refreshed_at": "now"},
        }

    monkeypatch.setattr(knowledge_module, "get_driver", fake_driver)
    monkeypatch.setattr(knowledge_module, "fetch_graph", fake_fetch_graph)

    with build_client() as client:
        response = client.get("/api/v1/knowledge/graph")

    assert response.status_code == 200
    body = response.json()
    assert body["meta"]["total_nodes"] == 2
    assert body["nodes"][0]["type"] == "kb"


def test_graph_neo4j_unavailable_returns_503(monkeypatch):
    async def failing_driver():
        raise RuntimeError("connection refused")

    monkeypatch.setattr(knowledge_module, "get_driver", failing_driver)

    with build_client() as client:
        response = client.get("/api/v1/knowledge/graph")

    assert response.status_code == 503
    assert response.json()["error"]["code"] == "knowledge_graph_unavailable"
    assert response.json()["error"]["retryable"] is True


def test_kb_list(monkeypatch):
    async def fake_list(pool):
        return [{"kb_code": "KB01", "kb_name": "系统业务知识库", "document_count": 46}]

    monkeypatch.setattr(knowledge_module, "list_kbs", fake_list)

    with build_client() as client:
        response = client.get("/api/v1/knowledge/kbs")

    assert response.status_code == 200
    assert response.json()["kbs"][0]["kb_code"] == "KB01"


def test_kb_documents_not_found(monkeypatch):
    async def empty(pool, kb_code):
        return None

    monkeypatch.setattr(knowledge_module, "list_documents_by_kb", empty)

    with build_client() as client:
        response = client.get("/api/v1/knowledge/kbs/KB99/documents")

    assert response.status_code == 404
    assert response.json()["detail"] == "知识库不存在"


def test_kb_documents_ok(monkeypatch):
    async def fake(pool, kb_code):
        return {
            "kb_code": kb_code,
            "kb_name": "系统业务知识库",
            "documents": [
                {"doc_id": "a" * 24, "title": "文档一", "source_file": "KB01/x.md",
                 "chunk_count": 3, "version": 1}
            ],
        }

    monkeypatch.setattr(knowledge_module, "list_documents_by_kb", fake)

    with build_client() as client:
        response = client.get("/api/v1/knowledge/kbs/KB01/documents")

    assert response.status_code == 200
    assert response.json()["documents"][0]["chunk_count"] == 3


def test_document_content_not_found(monkeypatch):
    async def empty(pool, doc_id):
        return None

    monkeypatch.setattr(knowledge_module, "get_document_content", empty)

    with build_client() as client:
        response = client.get("/api/v1/knowledge/documents/000000000000000000000000/content")

    assert response.status_code == 404
    assert response.json()["detail"] == "文档不存在"


def test_document_subgraph_returns_chunks_and_entities(monkeypatch):
    async def fake_driver():
        return object()

    async def fake_subgraph(driver, doc_id):
        assert doc_id == "a" * 24
        return {
            "doc_id": doc_id,
            "title": "文档一",
            "kb_code": "KB01",
            "nodes": [
                {"id": "chunk__" + doc_id + "_0000", "type": "chunk", "doc_id": doc_id,
                 "kb_code": "KB01", "label": "系统定位", "text": "正文"},
                {"id": "entity__登录", "type": "entity", "name": "登录",
                 "entity_type": "MODULE", "kb_code": "KB01", "description": "登录模块"},
            ],
            "links": [
                {"source": "chunk__" + doc_id + "_0000", "target": "doc__" + doc_id, "type": "PART_OF"},
                {"source": "chunk__" + doc_id + "_0000", "target": "entity__登录", "type": "HAS_ENTITY"},
            ],
            "meta": {"total_nodes": 2, "total_links": 2},
        }

    monkeypatch.setattr(knowledge_module, "get_driver", fake_driver)
    monkeypatch.setattr(knowledge_module, "fetch_document_subgraph", fake_subgraph)

    with build_client() as client:
        response = client.get("/api/v1/knowledge/documents/" + "a" * 24 + "/subgraph")

    assert response.status_code == 200
    body = response.json()
    assert body["nodes"][1]["type"] == "entity"
    assert body["links"][0]["type"] == "PART_OF"


def test_document_subgraph_not_found(monkeypatch):
    async def fake_driver():
        return object()

    async def no_subgraph(driver, doc_id):
        return None

    monkeypatch.setattr(knowledge_module, "get_driver", fake_driver)
    monkeypatch.setattr(knowledge_module, "fetch_document_subgraph", no_subgraph)

    with build_client() as client:
        response = client.get(
            "/api/v1/knowledge/documents/000000000000000000000000/subgraph"
        )

    assert response.status_code == 404
    assert response.json()["detail"] == "文档不存在"


def test_document_content_assembles_markdown(monkeypatch):
    async def fake(pool, doc_id):
        return {
            "doc_id": doc_id,
            "title": "文档一",
            "source_file": "KB01/x.md",
            "kb_code": "KB01",
            "content_markdown": "# 文档一\n\n## 系统定位\n\n正文",
            "chunk_count": 1,
            "chars": 20,
        }

    monkeypatch.setattr(knowledge_module, "get_document_content", fake)

    with build_client() as client:
        response = client.get("/api/v1/knowledge/documents/" + "a" * 24 + "/content")

    assert response.status_code == 200
    assert response.json()["content_markdown"].startswith("# 文档一")