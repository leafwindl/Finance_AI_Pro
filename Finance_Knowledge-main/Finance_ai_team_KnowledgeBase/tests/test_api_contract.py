from fastapi.testclient import TestClient

import kb_ingest_server


def test_ingest_rejects_two_input_modes(monkeypatch):
    monkeypatch.setattr(kb_ingest_server, "_get_embedding_model", lambda _: object())
    with TestClient(kb_ingest_server.create_app()) as client:
        response = client.post(
            "/ingest",
            json={"file_path": "document.md", "content": "# document"},
        )

    assert response.status_code == 200
    assert response.json() == {
        "success": False,
        "error": "file_path 和 content 只能传一个",
    }


def test_content_mode_preserves_safe_source_file_name(monkeypatch):
    captured = {}

    monkeypatch.setattr(
        kb_ingest_server,
        "build_output",
        lambda *args, **kwargs: {
            "doc_hash": "hash",
            "metadata": {"title": "标题", "source_file": "temporary.md", "meta_fields": {}},
            "chunks": [],
        },
    )

    def fake_write(data, *args, **kwargs):
        captured.update(data["metadata"])
        return True

    monkeypatch.setattr(kb_ingest_server, "write_to_postgres", fake_write)
    monkeypatch.setattr(kb_ingest_server, "_verify_pg_write", lambda *args, **kwargs: True)

    result = kb_ingest_server.process_one_document(
        content="# 标题",
        file_name="../document.md",
        no_embed=True,
        pg_write=True,
        es_write=False,
        pg_config={
            "host": "unused",
            "port": 5432,
            "dbname": "unused",
            "user": "unused",
            "password": "unused",
        },
    )

    assert result["success"] is True
    assert captured["source_file"] == "document.md"
