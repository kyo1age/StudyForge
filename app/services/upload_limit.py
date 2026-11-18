"""Bound the multipart request before it can spool an oversized file."""
from fastapi import HTTPException
from starlette.datastructures import Headers
from starlette.responses import JSONResponse

from ..config import settings

MULTIPART_OVERHEAD = 64 * 1024


class UploadBodyLimit:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if (scope["type"] != "http" or scope["method"] != "POST"
                or scope["path"].rstrip("/") != "/api/documents"):
            await self.app(scope, receive, send)
            return

        limit = settings.MAX_UPLOAD_BYTES + MULTIPART_OVERHEAD
        message = f"Upload exceeds the {settings.MAX_UPLOAD_BYTES / (1024 * 1024):g} MB file limit"
        size = Headers(scope=scope).get("content-length")
        if size is not None:
            try:
                content_length = int(size)
                if content_length < 0:
                    raise ValueError
            except ValueError:
                await JSONResponse({"detail": "Invalid Content-Length"}, status_code=400)(scope, receive, send)
                return
            if content_length > limit:
                await JSONResponse({"detail": message}, status_code=413)(scope, receive, send)
                return

        received = 0

        async def bounded_receive():
            nonlocal received
            event = await receive()
            if event["type"] == "http.request":
                received += len(event.get("body", b""))
                if received > limit:
                    raise HTTPException(413, message)
            return event

        await self.app(scope, bounded_receive, send)

