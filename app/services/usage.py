from datetime import date, timedelta

from ..config import settings
from ..db import read


def current_week_start() -> str:
    today = date.today()
    return (today - timedelta(days=today.weekday())).isoformat()


def estimate_tokens(text: str) -> int:
    return max(1, len(text) // settings.TOKEN_CHARS_RATIO) + 120


def get_quota(client_id: str) -> dict:
    week = current_week_start()
    with read() as conn:
        row = conn.execute(
            "SELECT tokens_used FROM usage WHERE client_id=? AND week_start=?", (client_id, week)
        ).fetchone()
    used = row["tokens_used"] if row else 0
    limit = settings.WEEKLY_TOKEN_LIMIT
    return {"used": used, "limit": limit, "remaining": max(0, limit - used), "week_start": week}


def try_reserve(conn, client_id: str, week: str, estimated: int) -> bool:
    conn.execute("INSERT OR IGNORE INTO usage(client_id, week_start) VALUES (?,?)", (client_id, week))
    cursor = conn.execute(
        """UPDATE usage SET tokens_used = tokens_used + ?
           WHERE client_id=? AND week_start=? AND tokens_used + ? <= ?""",
        (estimated, client_id, week, estimated, settings.WEEKLY_TOKEN_LIMIT),
    )
    return cursor.rowcount == 1


def settle(conn, client_id: str, week: str, estimated: int, actual: int) -> None:
    conn.execute(
        """UPDATE usage SET tokens_used = MAX(0, tokens_used + ?)
           WHERE client_id=? AND week_start=?""",
        (actual - estimated, client_id, week),
    )

