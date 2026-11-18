from concurrent.futures import ThreadPoolExecutor
from threading import Event

import httpx

from .test_app import _generate, _upload, _wait_job, client, client2, settings
from app.db import init_db, read, write
from app.services import jobs
from app.services.llm.factory import get_llm
from app.services.llm.openai_provider import OpenAiLlmProvider


def test_settings_expose_effective_mode_without_secrets(monkeypatch):
    monkeypatch.setattr(settings, "LLM_PROVIDER", "openai")
    monkeypatch.setattr(settings, "OPENAI_API_KEY", "")
    get_llm.cache_clear()
    try:
        info = client.get("/api/settings").json()
        assert info == {
            "provider": "mock", "configured_provider": "openai", "fallback_reason": "missing_api_key",
            "generation_mode": "mock", "model_used": "mock-generator",
            "max_upload_bytes": settings.MAX_UPLOAD_BYTES, "max_pdf_pages": settings.MAX_PDF_PAGES,
            "max_pages_per_generation": settings.MAX_PAGES_PER_GENERATION,
        }
    finally:
        get_llm.cache_clear()


def test_delete_cascades_and_unlinks():
    document = _upload().json()
    doc_id = document["id"]
    assert document["created_at"]
    job_id = _generate(doc_id, "summary")["job_id"]
    generation = _wait_job(job_id)["generation"]
    assert generation["provider"] == "mock"
    with read() as conn:
        stored_name = conn.execute("SELECT stored_name FROM documents WHERE id=?", (doc_id,)).fetchone()[0]
    path = settings.UPLOAD_DIR / stored_name
    assert path.is_file()
    assert client2.delete(f"/api/documents/{doc_id}").status_code == 404
    assert client.delete(f"/api/documents/{doc_id}").status_code == 204
    assert client.get(f"/api/generations/{generation['id']}").status_code == 404
    assert client.get(f"/api/jobs/{job_id}").status_code == 404
    assert not path.exists()
    with read() as conn:
        assert conn.execute("SELECT 1 FROM pages WHERE document_id=?", (doc_id,)).fetchone() is None


def test_running_job_reused_and_document_not_deleted(monkeypatch):
    started, finish = Event(), Event()
    real_provider = get_llm()

    class BlockingProvider:
        name = "mock"

        def generate(self, material_type, context):
            started.set()
            assert finish.wait(8)
            return real_provider.generate(material_type, context)

    monkeypatch.setattr(jobs, "get_llm", BlockingProvider)
    doc_id = _upload().json()["id"]
    with ThreadPoolExecutor(1) as pool:
        original = pool.submit(_generate, doc_id, "quiz")
        try:
            assert started.wait(5)
            duplicate = _generate(doc_id, "quiz")
            assert client2.get(f"/api/jobs/{duplicate['job_id']}").status_code == 404
            assert client.get(f"/api/jobs/{duplicate['job_id']}").json()["status"] == "running"
            assert client.delete(f"/api/documents/{doc_id}").status_code == 409
        finally:
            finish.set()
        assert original.result(timeout=5)["job_id"] == duplicate["job_id"]
    assert _wait_job(duplicate["job_id"])["status"] == "done"


def test_restart_refunds_reservation_from_original_week():
    doc_id = _upload().json()["id"]
    client_id = client.cookies.get(settings.CLIENT_COOKIE)
    week = "2000-01-03"
    job_id, _, _ = jobs.enqueue((client_id, doc_id, 1, 3, "quiz"))
    with write() as conn:
        conn.execute("INSERT INTO usage VALUES (?,?,?)", (client_id, week, 180))
        conn.execute("UPDATE jobs SET status='running', reserved_tokens=150, reservation_week=? WHERE id=?", (week, job_id))
    init_db()
    assert client.get(f"/api/jobs/{job_id}").json()["status"] == "error"
    with read() as conn:
        assert conn.execute("SELECT tokens_used FROM usage WHERE client_id=? AND week_start=?", (client_id, week)).fetchone()[0] == 30


def test_upload_limit_reports_actual_configuration(monkeypatch):
    monkeypatch.setattr(settings, "MAX_UPLOAD_BYTES", 1024 * 1024)
    uploaded = _upload(b"%PDF-" + b"x" * (1024 * 1024))
    assert uploaded.status_code == 413
    assert "1 MB" in uploaded.json()["detail"]
    response = client.post("/api/documents", content=b"x" * (2 * 1024 * 1024))
    assert response.status_code == 413


def test_upload_limit_applies_to_stream_without_content_length(monkeypatch):
    monkeypatch.setattr(settings, "MAX_UPLOAD_BYTES", 1024)
    boundary = "fixture"
    chunks = iter([
        b'--fixture\r\nContent-Disposition: form-data; name="file"; filename="lecture.pdf"\r\n'
        b'Content-Type: application/pdf\r\n\r\n%PDF-',
        b"x" * 70000, b"\r\n--fixture--\r\n"
    ])
    response = client.post("/api/documents", content=chunks, headers={
        "Content-Type": f"multipart/form-data; boundary={boundary}",
    })
    assert response.status_code == 413, response.text


def test_openai_adapter_retries_invalid_output_offline(monkeypatch):
    monkeypatch.setattr(settings, "OPENAI_API_KEY", "test-placeholder")
    monkeypatch.setattr(settings, "OPENAI_BASE_URL", "https://test.invalid/v1")
    real_client = httpx.Client
    requests = []

    def respond(request):
        requests.append(request.url.path)
        content = '{"title":"Notes","sections":[{"title":"Topic","points":["Fact"]}]}'
        return httpx.Response(200, json={
            "choices": [{"message": {"content": content if len(requests) > 1 else "not JSON"}}],
            "usage": {"total_tokens": 180},
        })

    monkeypatch.setattr(httpx, "Client", lambda **kwargs: real_client(
        **kwargs, transport=httpx.MockTransport(respond),
    ))
    result = OpenAiLlmProvider().generate("summary", "Example lesson")
    assert requests == ["/v1/chat/completions", "/v1/chat/completions"]
    assert result.data["sections"][0]["points"] == ["Fact"]
    assert result.tokens_used == 180

