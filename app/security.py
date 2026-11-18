"""Anonymous client identification via httpOnly cookie + dependency."""
import re
import uuid
from typing import Optional
from fastapi import Request, Response
from .config import settings
from .db import read, write

_CLIENT_ID_RE = re.compile(r"^[0-9a-f-]{36}$")

def _valid_client_id(value: Optional[str]) -> bool:
    if not value or not _CLIENT_ID_RE.match(value):
        return False
    try:
        uuid.UUID(value)
        return True
    except ValueError:
        return False

def ensure_client(request: Request, response: Response) -> str:
    candidate = request.cookies.get(settings.CLIENT_COOKIE, "")
    if _valid_client_id(candidate):
        with read() as conn:
            if conn.execute("SELECT 1 FROM clients WHERE client_id=?", (candidate,)).fetchone():
                return candidate
    client_id = str(uuid.uuid4())
    with write() as conn:
        conn.execute("INSERT OR IGNORE INTO clients(client_id) VALUES (?)", (client_id,))
    response.set_cookie(
        settings.CLIENT_COOKIE, client_id,
        max_age=60 * 60 * 24 * 365 * 5,
        httponly=True, samesite="lax", secure=settings.COOKIE_SECURE, path="/",
    )
    return client_id
