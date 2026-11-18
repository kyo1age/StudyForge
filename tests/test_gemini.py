import json
import sqlite3
from concurrent.futures import ThreadPoolExecutor

import httpx2
import pytest
from google import genai
from google.genai import types

from .test_app import _generate, _upload, _wait_job, client, make_pdf, settings
from app.db import init_db, read, write
from app.services.llm.base import LlmError
from app.services.llm.factory import get_llm
from app.services.llm.gemini_budget import Budget
from app.services.llm import gemini_provider

LECTURE = (
    "ХІХ ғасырда Қазақ даласында әкімшілік өзгерістер жүргізілді. "
    "1822 жылғы «Сібір қырғыздары туралы жарғы» Орта жүзде хандық билікті жойды. "
    "Кенесары Қасымұлы бастаған көтеріліс 1837–1847 жылдары жалғасты."
)
QUESTION = {
    "question": "Орта жүздегі хандық билік қай жылы жойылды?",
    "options": ["1822 жылы", "1824 жылы", "1837 жылы", "1847 жылы"],
    "correct_index": 0,
    "explanation": "1822 жылғы жарғы Орта жүздегі хандық билікті жойды.",
    "source_page": 2,
}
MATERIALS = {
    "quiz": {"questions": [QUESTION]},
    "flashcards": {"cards": [{"question": "Көтеріліс қай жылдары жалғасты?",
                             "answer": "Көтеріліс 1837–1847 жылдары жалғасты.", "source_page": 2}]},
    "summary": {"main_topics": ["Әкімшілік өзгерістер"],
                "sections": [{"title": "Орта жүздегі өзгеріс", "points": [QUESTION["explanation"]]}]},
}


@pytest.fixture
def gemini(monkeypatch):
    for key, value in {
        "LLM_PROVIDER": "gemini", "GEMINI_API_KEY": "test-key-never-sent",
        "GEMINI_MODEL": "gemini-3.5-flash-lite", "GEMINI_INPUT_PRICE_PER_1M": "0.30",
        "GEMINI_OUTPUT_PRICE_PER_1M": "2.50", "GEMINI_DAILY_REQUEST_LIMIT": "30",
        "GEMINI_DAILY_BUDGET_USD": "2.00",
    }.items():
        monkeypatch.setattr(settings, key, value)
    get_llm.cache_clear()
    with write() as conn:
        conn.execute("DELETE FROM gemini_attempts")
    yield
    get_llm.cache_clear()


@pytest.fixture
def sdk(monkeypatch):
    """Use the real SDK and replace only its HTTP transport."""
    real_client = genai.Client
    attempts = []
    failures = []
    override = {}

    def handle(request):
        payload = json.loads(request.content)
        assert request.url.host == "generativelanguage.googleapis.com"
        assert request.headers["x-goog-api-key"] == "test-key-never-sent"
        assert "generateContent" in request.url.path
        attempts.append(payload)
        if failures:
            code = failures.pop(0)
            return httpx2.Response(code, json={"error": {
                "code": code, "message": "must never be shown to users", "status": "UNAVAILABLE",
            }})
        contents = payload["contents"][0]["parts"][0]["text"]
        kind = contents.split("Requested format: ")[1].split(".")[0]
        pages = json.loads(contents.split("Source pages (JSON):\n")[1])
        assert pages == [{"page": 2, "text": LECTURE}]
        config = payload["generationConfig"]
        assert config["maxOutputTokens"] == 4096
        assert config["responseMimeType"] == "application/json"
        assert "responseJsonSchema" in config
        material = {"title": "ХІХ ғасырдағы Қазақ даласы", "detected_language": "kk", **MATERIALS[kind], **override}
        return httpx2.Response(200, json={
            "modelVersion": "gemini-3.5-flash-lite-output",
            "candidates": [{"content": {"parts": [{"text": json.dumps(material, ensure_ascii=False)}], "role": "model"}}],
            "usageMetadata": {"promptTokenCount": 100, "candidatesTokenCount": 60,
                              "thoughtsTokenCount": 20, "totalTokenCount": 180},
        })

    with httpx2.Client(transport=httpx2.MockTransport(handle)) as transport_client:
        def local_client(**kwargs):
            options = kwargs["http_options"]
            assert options.timeout == 45000 and options.retry_options.attempts == 1
            kwargs["http_options"] = types.HttpOptions(
                **options.model_dump(exclude_none=True), httpx_client=transport_client,
            )
            return real_client(**kwargs)

        monkeypatch.setattr(genai, "Client", local_client)
        monkeypatch.setattr(gemini_provider, "time", type("NoSleep", (), {"sleep": staticmethod(lambda _: None)}))
        yield attempts, failures, override


def document():
    doc = _upload(make_pdf(["Cover page with faculty and author data.",
                            "Content here is replaced by the equivalent Kazakh test fixture."])).json()
    with write() as conn:
        conn.execute("UPDATE pages SET text=? WHERE document_id=? AND page_num=2", (LECTURE, doc["id"]))
    return doc["id"]


def test_gemini_formats_usage_history_and_settings(gemini, sdk):
    doc_id = document()
    info = client.get("/api/settings").json()
    assert info["generation_mode"] == "gemini"
    assert info["model_used"] == settings.GEMINI_MODEL
    assert "test-key-never-sent" not in str(info)
    for kind in MATERIALS:
        start = _generate(doc_id, kind, 2, 2)
        job = _wait_job(start["job_id"])
        assert job["status"] == "done", job
        result = job["generation"]
        assert result["generation_mode"] == result["provider"] == "gemini"
        assert result["model_used"] == "gemini-3.5-flash-lite-output"
        assert result["tokens_used"] == 180
        assert result["cost_usd"] == 0.000230
        assert result["thoughts_tokens"] == 20
        assert result["result"]["detected_language"] == "kk"
        if kind == "quiz":
            assert result["result"]["questions"][0] == QUESTION
        assert _generate(doc_id, kind, 2, 2)["generation"]["id"] == result["id"]
    assert len(sdk[0]) == 3


def test_cache_does_not_mix_mock_with_gemini(gemini, sdk, monkeypatch):
    doc_id = document()
    monkeypatch.setattr(settings, "LLM_PROVIDER", "mock")
    get_llm.cache_clear()
    mock = _wait_job(_generate(doc_id, "quiz", 2, 2)["job_id"])["generation"]
    monkeypatch.setattr(settings, "LLM_PROVIDER", "gemini")
    get_llm.cache_clear()
    real = _wait_job(_generate(doc_id, "quiz", 2, 2)["job_id"])["generation"]
    assert mock["id"] != real["id"]
    assert [item["provider"] for item in client.get(f"/api/generations?document_id={doc_id}").json()] == ["gemini", "mock"]


@pytest.mark.parametrize("change", [
    {"options": ["1822 жылы", "1822 жылы!", "1837 жылы", "1847 жылы"]},
    {"question": "Продолжите фразу о ханской власти"},
    {"source_page": 1},
    {"correct_index": 5},
])
def test_invalid_or_unsourced_results_are_not_saved_and_do_consume_budget(gemini, sdk, change):
    doc_id = document()
    sdk[2]["questions"] = [{**QUESTION, **change}]
    job = _wait_job(_generate(doc_id, "quiz", 2, 2)["job_id"])
    assert job["status"] == "error" and job["error_status"] == 422, job
    assert client.get(f"/api/generations?document_id={doc_id}").json() == []
    assert len(sdk[0]) == 1
    with read() as conn:
        assert conn.execute("SELECT cost_microusd FROM gemini_attempts").fetchone()[0] == 230


def test_retry_counts_as_attempt_and_daily_limit_blocks_before_http(gemini, sdk, monkeypatch):
    monkeypatch.setattr(settings, "GEMINI_DAILY_REQUEST_LIMIT", "2")
    sdk[1].append(503)
    doc_id = document()
    assert _wait_job(_generate(doc_id, "quiz", 2, 2)["job_id"])["status"] == "done"
    assert len(sdk[0]) == 2
    init_db()
    assert client.delete(f"/api/documents/{doc_id}").status_code == 204
    job = _wait_job(_generate(document(), "quiz", 2, 2)["job_id"])
    assert job["status"] == "error" and job["error_status"] == 429
    assert len(sdk[0]) == 2


def test_concurrent_reservations_cannot_both_spend_budget(gemini, monkeypatch):
    monkeypatch.setattr(settings, "GEMINI_DAILY_BUDGET_USD", "0.001")
    budget = Budget.from_settings()

    def reserve():
        try:
            budget.reserve(650)
            return True
        except LlmError as error:
            assert error.status_code == 429
            return False

    with ThreadPoolExecutor(2) as pool:
        assert sorted(pool.map(lambda _: reserve(), range(2))) == [False, True]


def test_missing_gemini_key_keeps_truthful_mock_mode(gemini, monkeypatch):
    monkeypatch.setattr(settings, "GEMINI_API_KEY", "")
    info = client.get("/api/settings").json()
    assert info["generation_mode"] == "mock"
    assert info["configured_provider"] == "gemini"
    assert info["fallback_reason"] == "missing_api_key"


def test_migration_preserves_legacy_history_and_ids(monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "DATA_DIR", tmp_path)
    monkeypatch.setattr(settings, "DB_PATH", tmp_path / "legacy.sqlite3")
    monkeypatch.setattr(settings, "UPLOAD_DIR", tmp_path / "uploads")
    with sqlite3.connect(settings.DB_PATH) as legacy:
        legacy.executescript("""
            CREATE TABLE generations (
                id INTEGER PRIMARY KEY AUTOINCREMENT, client_id TEXT, document_id INTEGER,
                page_from INTEGER, page_to INTEGER, material_type TEXT, result TEXT,
                tokens_used INTEGER, created_at TEXT, provider TEXT,
                UNIQUE (client_id, document_id, page_from, page_to, material_type)
            );
            INSERT INTO generations VALUES
                (41, 'legacy-client', 12, 2, 5, 'quiz', '{}', 123, '2026-01-01', NULL),
                (42, 'legacy-client', 12, 2, 5, 'summary', '{}', 123, '2026-01-01', 'mock'),
                (90, 'legacy-client', 12, 2, 5, 'flashcards', '{}', 123, '2026-01-01', 'mock');
            DELETE FROM generations WHERE id=90;
        """)
    init_db()
    init_db()
    with read() as conn:
        assert conn.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        records = conn.execute("SELECT id, provider, model_name, cache_scope FROM generations ORDER BY id")
        assert list(map(tuple, records)) == [(41, None, None, "legacy"), (42, "mock", "mock-generator", "mock:mock-generator")]
        assert conn.execute("SELECT seq FROM sqlite_sequence WHERE name='generations'").fetchone()[0] == 90

