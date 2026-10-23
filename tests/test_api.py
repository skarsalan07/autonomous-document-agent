from fastapi.testclient import TestClient
from docx import Document

from app.config import Settings
from app.main import create_app
from app.schemas import (
    AgentResponse,
    DocumentMetadata,
    ExecutionSummary,
    QualityCheck,
    QualityResult,
)


def _response(request: str) -> AgentResponse:
    return AgentResponse(
        execution_id="test-execution",
        status="completed",
        request=request,
        document_type="Test Plan",
        plan=[],
        execution_summary=ExecutionSummary(total_tasks=0, completed_tasks=0, failed_tasks=0, skipped_tasks=0),
        quality_check=QualityResult(
            passed=True,
            checks=[QualityCheck(name="file_exists", passed=True, details="exists")],
            character_count=1000,
            file_size_bytes=1000,
        ),
        document=DocumentMetadata(filename="document-" + "a" * 32 + ".docx", size_bytes=1000, download_url="/documents/document-" + "a" * 32 + ".docx"),
        message="The document was generated and validated successfully.",
    )


def test_valid_request_accepted_and_response_returned(tmp_path):
    settings = Settings(generated_documents_dir=tmp_path)
    app = create_app(settings, workflow=lambda request, _settings, _execution_id: _response(request))
    client = TestClient(app)
    response = client.post("/agent", json={"request": "Create a short implementation plan"})
    assert response.status_code == 200
    assert response.json()["status"] == "completed"


def test_empty_and_missing_requests_are_rejected(tmp_path):
    client = TestClient(create_app(Settings(generated_documents_dir=tmp_path)))
    blank = client.post("/agent", json={"request": "   "})
    missing = client.post("/agent", json={})
    assert blank.status_code == 422
    assert missing.status_code == 422
    assert blank.json()["error"] == "invalid_request"
    assert "execution_id" in missing.json()


def test_configured_request_length_is_enforced(tmp_path):
    settings = Settings(generated_documents_dir=tmp_path, max_request_length=100)
    client = TestClient(create_app(settings))
    response = client.post("/agent", json={"request": "x" * 101})
    assert response.status_code == 422


def test_health_and_document_download_guards(tmp_path):
    settings = Settings(generated_documents_dir=tmp_path)
    client = TestClient(create_app(settings))
    assert client.get("/health").json()["status"] == "ok"
    filename = "document-" + "b" * 32 + ".docx"
    assert client.get(f"/documents/{filename}").status_code == 404
    assert client.get("/documents/..%5C.env").status_code in (400, 404)
    valid_path = tmp_path / filename
    Document().save(valid_path)
    downloaded = client.get(f"/documents/{filename}")
    assert downloaded.status_code == 200
    assert downloaded.headers["content-type"].startswith("application/vnd.openxmlformats")


def test_missing_groq_configuration_is_reported_without_a_fake_success(tmp_path):
    settings = Settings(groq_api_key="", groq_model="", generated_documents_dir=tmp_path)
    client = TestClient(create_app(settings))
    response = client.post("/agent", json={"request": "Create a concise implementation plan"})
    assert response.status_code == 503
    assert response.json()["error"] == "configuration_error"
    assert "execution_id" in response.json()
