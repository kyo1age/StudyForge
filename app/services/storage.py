"""Safe file storage for uploaded PDFs."""
import re
import uuid
from pathlib import Path
from ..config import settings

_UNSAFE_NAME_RE = re.compile(r"[^\w .()-]+")

def sanitize_filename(name: str) -> str:
    name = (name or "document.pdf").replace("\\", "/").rsplit("/", 1)[-1]
    name = _UNSAFE_NAME_RE.sub("_", name).strip(" ._")
    return name[:120] or "document.pdf"

def save_upload(content: bytes) -> tuple[str, Path]:
    stored_name = f"{uuid.uuid4().hex}.pdf"
    path = settings.UPLOAD_DIR / stored_name
    path.write_bytes(content)
    return stored_name, path

def delete_upload(stored_name: str) -> None:
    if not re.fullmatch(r"[0-9a-f]{32}\.pdf", stored_name or ""):
        return
    (settings.UPLOAD_DIR / stored_name).unlink(missing_ok=True)
