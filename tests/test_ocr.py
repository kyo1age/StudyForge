import io

import pytest
from PIL import Image, ImageDraw, ImageFont

from .test_app import _generate, _upload, _wait_job, client, make_pdf, settings
from app.services import ocr


def scanned_pdf():
    image = Image.new("RGB", (1800, 650), "white")
    draw = ImageDraw.Draw(image)
    font = ImageFont.truetype("arial.ttf", 59)
    for line, text in enumerate((
        "Әже, ғалым, қазақ, жаңбыр, өнер.",
        "Ұлт, күн, қаһарман, ілім.",
        "Русский текст для проверки.",
        "English text for recognition.",
    )):
        draw.text((85, 85 + line * 110), text, fill="black", font=font)
    pdf = io.BytesIO()
    image.save(pdf, "PDF", resolution=220)
    return pdf.getvalue()


def test_text_pdf_does_not_invoke_ocr(monkeypatch):
    def fail(*args):
        raise AssertionError("Unexpected OCR")
    monkeypatch.setattr(ocr, "_recognize", fail)
    assert _upload(make_pdf(["This page already contains a complete sentence."])).status_code == 201
    assert _upload(b"%PDF-broken").status_code == 422


@pytest.mark.skipif(not all((settings.OCR_TESSDATA_DIR / f"{lang}.traineddata").is_file()
                           for lang in ocr.LANGUAGES), reason="Install the three Tesseract models")
def test_scan_recognition_and_generation(monkeypatch):
    original = ocr._recognize
    invoked = []

    def count(path, index, timeout):
        invoked.append(index)
        return original(path, index, timeout)
    monkeypatch.setattr(ocr, "_recognize", count)

    upload = _upload(scanned_pdf(), "scan.pdf")
    assert upload.status_code == 201, upload.text
    doc = upload.json()
    assert [page["page_num"] for page in doc["pages"]] == [1]
    text = doc["pages"][0]["text_preview"]
    assert set("әғқңөұүһі") <= set(text.casefold()), text
    assert "Русский текст" in text
    assert "English text" in text

    for kind in ("summary", "flashcards", "quiz"):
        job = _wait_job(_generate(doc["id"], kind, 1, 1)["job_id"])
        assert job["status"] == "done", job
        assert job["generation"]["result"]
    assert client.get(f"/api/documents/{doc['id']}").status_code == 200
    assert invoked == [0]


def test_mixed_pdf_preserves_order_and_targets_weak_pages(monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "OCR_TESSDATA_DIR", tmp_path)
    for lang in ocr.LANGUAGES:
        (tmp_path / f"{lang}.traineddata").touch()
    calls = []
    def recognize(path, index, timeout):
        calls.append(index)
        return "Текст, распознанный со второй страницы."
    monkeypatch.setattr(ocr, "_recognize", recognize)
    response = _upload(make_pdf(["The first page contains readable text.", "2", "The third page contains readable text."]))
    assert response.status_code == 201, response.text
    pages = response.json()["pages"]
    assert [page["page_num"] for page in pages] == [1, 2, 3]
    assert "познанный" in pages[1]["text_preview"]
    assert calls == [1]

