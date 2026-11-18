"""Anonymous client identification via httpOnly cookie + dependency."""
import re
import uuid
from typing import Optional
from urllib.parse import urlsplit
from fastapi import Request, Response
from starlette.datastructures import Headers, MutableHeaders, URL
from starlette.responses import JSONResponse
from .config import settings
from .db import read, write

_CLIENT_ID_RE = re.compile(r"^[0-9a-f-]{36}$")


def _origin(value):
    try:
        parsed = urlsplit(value)
        if (parsed.scheme not in {"http", "https"} or not parsed.hostname
                or parsed.username is not None or parsed.password is not None
                or parsed.path or parsed.query or parsed.fragment):
            return None
        return parsed.scheme, parsed.hostname.lower(), parsed.port or (443 if parsed.scheme == "https" else 80)
    except ValueError:
        return None


class SameOriginApi:
    """Protect the local API from browser cross-origin writes and cached data."""
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or not scope["path"].startswith("/api/"):
            await self.app(scope, receive, send)
            return

        async def private_send(message):
            if message["type"] == "http.response.start":
                MutableHeaders(scope=message)["Cache-Control"] = "no-store"
            await send(message)

        headers = Headers(scope=scope)
        if scope["method"] not in {"GET", "HEAD", "OPTIONS"}:
            origin = headers.get("origin")
            target = str(URL(scope=scope).replace(path="", query="", fragment=""))
            if (headers.get("sec-fetch-site") == "cross-site"
                    or (origin is not None and (_origin(origin) is None or _origin(origin) != _origin(target)))):
                await JSONResponse({"detail": "Cross-origin API request denied"}, status_code=403)(scope, receive, private_send)
                return
        await self.app(scope, receive, private_send)

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
