"""Generate materials in-process. SQLite owns the job and quota state."""
import json
import logging
import uuid

from fastapi import HTTPException

from ..config import settings
from ..db import read, write
from .llm.base import LlmError
from .llm.factory import get_llm
from .usage import current_week_start, estimate_tokens, settle, try_reserve

logger = logging.getLogger(__name__)

_MATCH = """client_id=? AND document_id=? AND page_from=? AND page_to=? AND material_type=?"""


def _model_name(provider):
    return getattr(provider, "model_name", "mock-generator" if provider.name == "mock" else None)


def _cache_scope(provider):
    return f"{provider.name}:{_model_name(provider) or ''}"


def enqueue(key):
    """Atomically validate ownership, check the cache and reuse an active job."""
    client_id, document_id, page_from, page_to, _ = key
    with write() as conn:
        doc = conn.execute(
            "SELECT page_count FROM documents WHERE id=? AND client_id=?",
            (document_id, client_id),
        ).fetchone()
        if not doc:
            raise HTTPException(404, "Document not found")
        validate_range(page_from, page_to, doc["page_count"])
        scoped_key = (*key, _cache_scope(get_llm()))
        scoped_match = _MATCH + " AND cache_scope=?"
        existing = conn.execute(f"SELECT * FROM generations WHERE {scoped_match}", scoped_key).fetchone()
        if existing:
            return "", existing, False
        active = conn.execute(
            f"SELECT id FROM jobs WHERE {scoped_match} AND status IN ('pending', 'running')", scoped_key
        ).fetchone()
        if active:
            return active["id"], None, False
        job_id = str(uuid.uuid4())
        conn.execute(
            """INSERT INTO jobs(id, client_id, document_id, page_from, page_to, material_type, cache_scope)
               VALUES (?,?,?,?,?,?,?)""", (job_id, *scoped_key),
        )
        return job_id, None, True


def run_job(job_id: str) -> None:
    with write() as conn:
        job = conn.execute("SELECT * FROM jobs WHERE id=? AND status='pending'", (job_id,)).fetchone()
        if not job:
            return
        conn.execute("UPDATE jobs SET status='running' WHERE id=?", (job_id,))

    try:
        with read() as conn:
            pages = conn.execute(
                """SELECT page_num, text FROM pages WHERE document_id=? AND page_num BETWEEN ? AND ?
                   ORDER BY page_num""",
                (job["document_id"], job["page_from"], job["page_to"]),
            ).fetchall()
        context = "\n\n".join(page["text"].strip() for page in pages).strip()
        if not context.strip():
            raise LlmError("Selected pages contain no text")

        provider = get_llm()
        if _cache_scope(provider) != job["cache_scope"]:
            raise LlmError("Режим генерации изменился. Отправьте запрос повторно.", 409)
        context = context[:24000]
        week = current_week_start()
        estimated = estimate_tokens(context)
        with write() as conn:
            if not try_reserve(conn, job["client_id"], week, estimated):
                raise LlmError("Weekly AI token limit exceeded")
            conn.execute(
                "UPDATE jobs SET reserved_tokens=?, reservation_week=? WHERE id=?",
                (estimated, week, job_id),
            )

        source = _numbered_source(pages) if provider.name == "gemini" else context
        response = provider.generate(job["material_type"], source)
        with write() as conn:
            cursor = conn.execute(
                """INSERT INTO generations
                   (client_id, document_id, page_from, page_to, material_type, result, tokens_used,
                    provider, cache_scope, model_name, prompt_tokens, candidates_tokens, thoughts_tokens, cost_usd)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (job["client_id"], job["document_id"], job["page_from"], job["page_to"],
                 job["material_type"], json.dumps(response.data), response.tokens_used, provider.name,
                 job["cache_scope"], response.model_name or _model_name(provider), response.prompt_tokens,
                 response.candidates_tokens, response.thoughts_tokens, response.cost_usd),
            )
            _finish(conn, job_id, "done", generation_id=cursor.lastrowid, actual=response.tokens_used)
    except LlmError as exc:
        _fail(job_id, str(exc), exc.status_code)
    except Exception as exc:
        # Provider exception messages and tracebacks can contain source text or credentials.
        logger.error("Generation job %s failed (%s)", job_id, type(exc).__name__)
        _fail(job_id, "Internal generation error. Try again or check the server log.")


def _numbered_source(pages):
    excerpts = []
    remaining = 24_000
    for page in pages:
        text = page["text"].strip()[:remaining]
        if text:
            excerpts.append({"page": page["page_num"], "text": text})
            remaining -= len(text)
        if remaining == 0:
            break
    return json.dumps(excerpts, ensure_ascii=False)


def _fail(job_id, message, error_status=None):
    with write() as conn:
        _finish(conn, job_id, "error", error=message, error_status=error_status)


def _finish(conn, job_id, status, *, generation_id=None, error=None, error_status=None, actual=0):
    job = conn.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone()
    if not job:
        return
    if job["reserved_tokens"]:
        settle(conn, job["client_id"], job["reservation_week"], job["reserved_tokens"], actual)
    conn.execute(
        """UPDATE jobs SET status=?, error=?, error_status=?, generation_id=?, reserved_tokens=0,
                  finished_at=datetime('now') WHERE id=?""",
        (status, error, error_status, generation_id, job_id),
    )


def validate_range(page_from: int, page_to: int, page_count: int) -> None:
    if page_from > page_to:
        raise HTTPException(400, "First page must be before or equal to the last page")
    if page_to > page_count:
        raise HTTPException(400, f"Document has only {page_count} pages")
    if page_to - page_from + 1 > settings.MAX_PAGES_PER_GENERATION:
        raise HTTPException(400, f"Range exceeds the {settings.MAX_PAGES_PER_GENERATION}-page limit")

