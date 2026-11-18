"""SQLite access layer: connection management, schema init, small helpers."""
import sqlite3
import threading
from contextlib import contextmanager

from .config import settings

_GENERATIONS_SQL = """
CREATE TABLE IF NOT EXISTS generations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    client_id TEXT NOT NULL,
    document_id INTEGER NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    page_from INTEGER NOT NULL,
    page_to INTEGER NOT NULL,
    material_type TEXT NOT NULL,
    result TEXT NOT NULL,
    tokens_used INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    provider TEXT,
    model_name TEXT,
    prompt_tokens INTEGER,
    candidates_tokens INTEGER,
    thoughts_tokens INTEGER,
    cost_usd REAL,
    cache_scope TEXT NOT NULL,
    UNIQUE (client_id, document_id, page_from, page_to, material_type, cache_scope)
)
"""
_GENERATIONS_INDEX = """
CREATE INDEX IF NOT EXISTS idx_generations_client ON generations(client_id, document_id)
"""

_INIT_SQL = """
PRAGMA journal_mode=WAL;
PRAGMA foreign_keys=ON;

CREATE TABLE IF NOT EXISTS clients (
    client_id TEXT PRIMARY KEY,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS documents (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    client_id TEXT NOT NULL REFERENCES clients(client_id),
    filename TEXT NOT NULL,
    stored_name TEXT NOT NULL,
    size INTEGER NOT NULL,
    page_count INTEGER NOT NULL,
    status TEXT NOT NULL DEFAULT 'ready',
    error TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_documents_client ON documents(client_id);

CREATE TABLE IF NOT EXISTS pages (
    document_id INTEGER NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    page_num INTEGER NOT NULL,
    text TEXT NOT NULL,
    PRIMARY KEY (document_id, page_num)
);

CREATE TABLE IF NOT EXISTS usage (
    client_id TEXT NOT NULL,
    week_start TEXT NOT NULL,
    tokens_used INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (client_id, week_start)
);

CREATE TABLE IF NOT EXISTS jobs (
    id TEXT PRIMARY KEY,
    client_id TEXT NOT NULL,
    document_id INTEGER NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    page_from INTEGER NOT NULL,
    page_to INTEGER NOT NULL,
    material_type TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',
    error TEXT,
    generation_id INTEGER,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    finished_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_jobs_client ON jobs(client_id, document_id);

CREATE TABLE IF NOT EXISTS gemini_attempts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    day_utc TEXT NOT NULL,
    cost_microusd INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_gemini_attempts_day ON gemini_attempts(day_utc);
""" + _GENERATIONS_SQL + ";" + _GENERATIONS_INDEX + ";"

_write_lock = threading.RLock()


def init_db() -> None:
    settings.DATA_DIR.mkdir(parents=True, exist_ok=True)
    settings.UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    with _connect() as conn:
        conn.executescript(_INIT_SQL)
    # Older databases may already contain orphan rows from when FK checks were
    # disabled. Keep their history during the table rebuild.
    with write(foreign_keys=False) as conn:
        _migrate_generations(conn)
        _add_column(conn, "jobs", "reserved_tokens", "INTEGER NOT NULL DEFAULT 0")
        _add_column(conn, "jobs", "reservation_week", "TEXT")
        _add_column(conn, "jobs", "cache_scope", "TEXT NOT NULL DEFAULT 'legacy'")
        _add_column(conn, "jobs", "error_status", "INTEGER")
        conn.execute("""
            UPDATE usage SET tokens_used = MAX(0, tokens_used - COALESCE((
                SELECT SUM(reserved_tokens) FROM jobs
                WHERE jobs.client_id = usage.client_id AND reservation_week = usage.week_start
                  AND status IN ('pending','running')
            ), 0))
        """)
        conn.execute(
            """UPDATE jobs SET status='error',
                      error='Interrupted by server restart',
                      reserved_tokens=0,
                      finished_at=datetime('now')
               WHERE status IN ('pending','running')"""
        )


def _columns(conn, table):
    return {row["name"] for row in conn.execute(f"PRAGMA table_info({table})")}


def _add_column(conn, table, name, definition):
    if name not in _columns(conn, table):
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {name} {definition}")


def _migrate_generations(conn):
    if "cache_scope" in _columns(conn, "generations"):
        return
    _add_column(conn, "generations", "provider", "TEXT")
    previous_sequence = conn.execute("SELECT seq FROM sqlite_sequence WHERE name='generations'").fetchone()
    conn.execute("ALTER TABLE generations RENAME TO generations_previous")
    conn.execute(_GENERATIONS_SQL)
    conn.execute("""
        INSERT INTO generations
            (id, client_id, document_id, page_from, page_to, material_type,
             result, tokens_used, created_at, provider, model_name, cache_scope)
        SELECT id, client_id, document_id, page_from, page_to, material_type,
               result, tokens_used, created_at, provider,
               CASE WHEN provider='mock' THEN 'mock-generator' END,
               CASE WHEN provider='mock' THEN 'mock:mock-generator' ELSE 'legacy' END
        FROM generations_previous
    """)
    conn.execute("DROP TABLE generations_previous")
    if previous_sequence:
        conn.execute("""INSERT INTO sqlite_sequence(name, seq) SELECT 'generations', ?
                        WHERE NOT EXISTS (SELECT 1 FROM sqlite_sequence WHERE name='generations')""",
                     (previous_sequence[0],))
        conn.execute("UPDATE sqlite_sequence SET seq=MAX(seq, ?) WHERE name='generations'", (previous_sequence[0],))
    conn.execute(_GENERATIONS_INDEX)


@contextmanager
def _connect(*, foreign_keys=True):
    conn = sqlite3.connect(settings.DB_PATH, timeout=30, isolation_level=None)
    conn.row_factory = sqlite3.Row
    try:
        conn.execute("PRAGMA foreign_keys=ON" if foreign_keys else "PRAGMA foreign_keys=OFF")
        yield conn
    finally:
        conn.close()


@contextmanager
def read():
    with _connect() as conn:
        yield conn


@contextmanager
def write(*, foreign_keys=True):
    with _write_lock:
        with _connect(foreign_keys=foreign_keys) as conn:
            try:
                conn.execute("BEGIN IMMEDIATE")
                yield conn
                conn.execute("COMMIT")
            except Exception:
                if conn.in_transaction:
                    conn.execute("ROLLBACK")
                raise
