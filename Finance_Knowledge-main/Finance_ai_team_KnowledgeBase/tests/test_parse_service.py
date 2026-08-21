from fastapi.testclient import TestClient

from services.parse_service import app


def test_parse_service_advertises_markdown_support():
    with TestClient(app) as client:
        response = client.get("/health")

    assert response.status_code == 200
    assert ".txt" in response.json()["supported_formats"]
    assert ".md" in response.json()["supported_formats"]


def test_parse_service_accepts_markdown_upload():
    with TestClient(app) as client:
        response = client.post(
            "/parse",
            files={"file": ("sample.md", "# Title\n\nMarkdown content.", "text/markdown")},
        )

    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    assert body["data"]["content"] == "# Title\n\nMarkdown content."
    assert body["data"]["source_type"] == "txt"
