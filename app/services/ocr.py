"""Manage OCR resources without running native libraries in the API process."""
import logging
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from threading import BoundedSemaphore
from time import monotonic

from fastapi import HTTPException

from ..config import settings

logger = logging.getLogger(__name__)
_slots = BoundedSemaphore(2)
LANGUAGES = ("kaz", "rus", "eng")
MAX_PAGES = 30
PAGE_SECONDS = 15
DOCUMENT_SECONDS = 120


def fill_pages(content, pages, indices, progress):
    if not indices:
        return []
    missing = [lang for lang in LANGUAGES if not (settings.OCR_TESSDATA_DIR / f"{lang}.traineddata").is_file()]
    if missing:
        message = "OCR недоступен. Настройте OCR_TESSDATA_DIR и установите модели: " + ", ".join(missing)
        if any(page.strip() for page in pages):
            return [message]
        raise HTTPException(422, message)
    if len(indices) > MAX_PAGES:
        raise HTTPException(422, f"OCR поддерживает до {MAX_PAGES} страниц без текстового слоя за загрузку. Разделите PDF.")
    if not _slots.acquire(blocking=False):
        raise HTTPException(503, "OCR занят. Повторите загрузку после завершения других распознаваний.")

    try:
        deadline = monotonic() + DOCUMENT_SECONDS
        with tempfile.TemporaryDirectory(prefix="ocr-", dir=settings.DATA_DIR) as directory:
            pdf_path = Path(directory) / "input.pdf"
            pdf_path.write_bytes(content)
            for step, index in enumerate(indices, 1):
                progress("ocr", step, len(indices), index + 1)
                remaining = deadline - monotonic()
                if remaining <= 0:
                    raise HTTPException(422, "Превышено время OCR для документа. Разделите PDF.")
                result = _recognize(pdf_path, index, min(PAGE_SECONDS, remaining))
                text = result.replace("\x00", "").strip()
                if sum(char.isalnum() for char in text) > sum(char.isalnum() for char in pages[index]):
                    pages[index] = text
    finally:
        _slots.release()
    return []


def _recognize(path, index, timeout):
    environment = {key: value for key, value in os.environ.items()
                   if key.upper() not in {"OPENAI_API_KEY", "GEMINI_API_KEY", "GOOGLE_API_KEY"}}
    environment.update(OMP_THREAD_LIMIT="1", PYTHONDONTWRITEBYTECODE="1")
    try:
        result = subprocess.run(
            [sys.executable, "-m", "app.services.ocr_worker", str(path), str(index), str(settings.OCR_TESSDATA_DIR)],
            cwd=settings.BASE_DIR,
            env=environment,
            capture_output=True, check=True, timeout=timeout,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        return result.stdout.decode("utf-8")
    except subprocess.TimeoutExpired as exc:
        raise HTTPException(422, f"Превышено время OCR страницы {index + 1}. Уменьшите размер или разрешение скана.") from exc
    except (subprocess.CalledProcessError, OSError, UnicodeError) as exc:
        logger.warning("OCR worker failed on page %s: %s", index + 1, type(exc).__name__)
        raise HTTPException(422, f"Не удалось распознать страницу {index + 1}. Проверьте PDF и модели Tesseract.") from exc

