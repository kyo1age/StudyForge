"""PDF validation and text extraction."""
from dataclasses import dataclass
from io import BytesIO
from typing import List
from fastapi import HTTPException, UploadFile
from pypdf import PdfReader
from ..config import settings
from . import ocr

PDF_MAGIC = b"%PDF-"

@dataclass
class ExtractedPdf:
    page_count: int
    pages: List[str]
    warnings: list[str]

async def read_and_validate_upload(file: UploadFile) -> bytes:
    if file.content_type not in ("application/pdf", "application/octet-stream"):
        raise HTTPException(415, "Only PDF files are supported")
    limit = settings.MAX_UPLOAD_BYTES / (1024 * 1024)
    size_error = f"File exceeds the {limit:g} MB limit"
    if file.size is not None and file.size > settings.MAX_UPLOAD_BYTES:
        raise HTTPException(413, size_error)
    chunks, total = [], 0
    while True:
        chunk = await file.read(1024 * 512)
        if not chunk:
            break
        total += len(chunk)
        if total > settings.MAX_UPLOAD_BYTES:
            raise HTTPException(413, size_error)
        chunks.append(chunk)
    content = b"".join(chunks)
    if not content:
        raise HTTPException(400, "Empty file")
    if not content.startswith(PDF_MAGIC):
        raise HTTPException(415, "File is not a valid PDF (bad signature)")
    return content

def extract_pages(content: bytes, progress=lambda *_: None) -> ExtractedPdf:
    try:
        reader = PdfReader(BytesIO(content))
        if reader.is_encrypted and not reader.decrypt(""):
            raise HTTPException(422, "PDF is encrypted and cannot be processed")
        page_count = len(reader.pages)
        if page_count == 0:
            raise HTTPException(422, "PDF contains no pages")
        if page_count > settings.MAX_PDF_PAGES:
            raise HTTPException(422, f"PDF exceeds the {settings.MAX_PDF_PAGES}-page limit")
        pages: List[str] = []
        total_chars = 0
        for index, page in enumerate(reader.pages, 1):
            progress("text", index, page_count, index)
            text = (page.extract_text() or "").replace("\x00", "")
            total_chars += len(text)
            if total_chars > settings.MAX_EXTRACTED_CHARS:
                raise HTTPException(422, "PDF contains too much text. Split it into smaller files.")
            pages.append(text)
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(422, "Damaged or unreadable PDF file")
    indices = [index for index, text in enumerate(pages) if sum(char.isalnum() for char in text) < 20]
    warnings = ocr.fill_pages(content, pages, indices, progress)
    if sum(map(len, pages)) > settings.MAX_EXTRACTED_CHARS:
        raise HTTPException(422, "PDF contains too much text. Split it into smaller files.")
    if not any(p.strip() for p in pages):
        raise HTTPException(422, "В PDF не найден читаемый текст. Проверьте качество скана.")
    return ExtractedPdf(page_count, pages, warnings)

