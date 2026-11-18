"""Run against a local StudyForge server with a disposable database and Mock Mode."""
import argparse
import io
import re
from pathlib import Path

from playwright.sync_api import expect, sync_playwright
from reportlab.pdfgen import canvas


def fixture_pdf():
    stream = io.BytesIO()
    pdf = canvas.Canvas(stream)
    for text in (
        "Erosion gradually carries sediment away from exposed mountain slopes.",
        "Rivers deposit the sediment when water slows down near the coast.",
        "<b>Layers of sediment can record changes in past environments.</b>",
        "Pressure helps compact loose material into sedimentary rock.",
        "Scientists compare rock layers to study the history of a landscape.",
    ):
        pdf.drawString(55, 720, text)
        pdf.showPage()
    pdf.save()
    return stream.getvalue()


def assert_width(page):
    assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth"), page.url


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default="http://127.0.0.1:8000")
    parser.add_argument("--screenshots", type=Path)
    args = parser.parse_args()
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        page = browser.new_page(viewport={"width": 1440, "height": 1024})
        page.set_default_timeout(7000)
        page_errors = []
        console_errors = []
        page.on("pageerror", lambda error: page_errors.append(str(error)))
        page.on("console", lambda msg: console_errors.append(msg.text) if msg.type == "error" else None)
        page.goto(args.url)
        expect(page.get_by_role("heading", name="Обзор", exact=True)).to_be_visible()
        expect(page.locator("#mode")).to_have_text("Mock Mode")
        assert_width(page)
        page.keyboard.press("Tab")
        expect(page.get_by_role("link", name="К основному содержимому")).to_be_focused()
        page.keyboard.press("Enter")
        expect(page.locator("#main")).to_be_focused()
        if args.screenshots:
            args.screenshots.mkdir(parents=True, exist_ok=True)
            page.screenshot(path=args.screenshots / "dashboard-dark.png", full_page=True)

        page.locator("#navigation").get_by_text("Документы", exact=True).click()
        page.locator('input[type=file]').set_input_files({
            "name": "broken.pdf", "mimeType": "application/pdf", "buffer": b"%PDF-broken",
        })
        expect(page.get_by_role("alert")).to_contain_text("Damaged or unreadable PDF")
        assert all("422" in item for item in console_errors), console_errors
        console_errors.clear()

        page.locator('input[type=file]').set_input_files({
            "name": "landscape.txt", "mimeType": "text/plain", "buffer": b"plain text",
        })
        expect(page.get_by_role("alert")).to_contain_text("расширением .pdf")

        payload = {
            "name": "landscape-check.pdf", "mimeType": "application/pdf", "buffer": fixture_pdf(),
        }
        # Exercise the same drag handler as a PDF dropped from the OS.
        transfer = page.evaluate_handle(
            """payload => {
                const transfer = new DataTransfer();
                transfer.items.add(new File([new Uint8Array(payload.bytes)], payload.name, {type: payload.type}));
                return transfer;
            }""", {"bytes": list(payload["buffer"]), "name": payload["name"], "type": payload["mimeType"]},
        )
        page.locator(".dropzone").dispatch_event("drop", {"dataTransfer": transfer})
        document_button = page.get_by_role("button", name="Открыть landscape-check.pdf")
        expect(document_button).to_be_visible()
        document_button.click()
        dialog = page.get_by_role("dialog")
        expect(dialog.get_by_text("<b>Layers of sediment", exact=False)).to_be_visible()
        assert dialog.locator(".page-previews b").count() == 0
        dialog.get_by_role("button", name="Использовать в AI Study").click()

        page.locator("#to-page").fill("1")
        page.locator("#from-page").fill("2")
        page.get_by_role("button", name="Сгенерировать").click()
        expect(page.get_by_role("alert")).to_contain_text("Укажите диапазон")
        page.locator("#from-page").fill("1")
        page.locator("#to-page").fill("5")

        page.get_by_role("button", name="Сгенерировать").click()
        expect(page.locator(".summary-section").first).to_be_visible()
        expect(page.locator(".material .badge.mock")).to_have_text("Mock Mode")

        page.get_by_role("radio", name=re.compile("Карточки")).check()
        page.get_by_role("button", name="Сгенерировать").click()
        flashcard = page.locator(".flashcard")
        expect(flashcard).to_be_visible()
        flashcard.focus()
        page.keyboard.press("Space")
        expect(flashcard).to_have_attribute("aria-pressed", "true")
        page.get_by_role("button", name="Знаю", exact=True).click()
        expect(page.get_by_text("Карточка 2 из 2")).to_be_visible()
        page.get_by_role("button", name="Повторить", exact=True).click()
        expect(page.get_by_text("Знаю: 1 · Повторить: 1")).to_be_visible()
        page.get_by_role("button", name="Назад", exact=True).click()
        expect(page.get_by_text("Карточка 1 из 2")).to_be_visible()

        page.get_by_role("radio", name=re.compile("^Тест")).check()
        page.get_by_role("button", name="Сгенерировать").click()
        expect(page.get_by_text("Вопрос 1 из 5")).to_be_visible()
        results = page.request.get(f"{args.url.rstrip('/')}/api/generations").json()
        questions = next(item["result"]["questions"] for item in results if item["material_type"] == "quiz")
        correct, wrong = questions[0]["options"][0], questions[1]["options"][1]
        page.locator(".option").filter(has_text=correct).click()
        page.get_by_role("button", name="Далее", exact=True).click()
        page.locator(".option").filter(has_text=wrong).click()
        page.get_by_role("button", name="Назад", exact=True).click()
        expect(page.locator(".option").filter(has_text=correct).get_by_role("radio")).to_be_checked()
        for _ in range(4):
            page.get_by_role("button", name="Далее", exact=True).click()
        page.get_by_role("button", name="Завершить тест").click()
        expect(page.locator(".score-number")).to_have_text("20%")
        expect(page.locator(".review-item").first).to_contain_text(correct)
        expect(page.locator(".review-item").nth(1)).to_contain_text(wrong)
        expect(page.locator(".review-item").nth(2)).to_contain_text("пропущено")
        page.get_by_role("button", name="Пройти ещё раз").click()
        expect(page.get_by_text("Ответы: 0/5")).to_be_visible()

        page.locator("#navigation").get_by_text("История", exact=True).click()
        expect(page.locator("main .entry")).to_have_count(3)
        page.locator("main .entry button").first.click()
        expect(page.get_by_text("Вопрос 1 из 5")).to_be_visible()

        page.get_by_role("button", name="Светлая тема").click()
        page.reload()
        expect(page.locator("html")).to_have_attribute("data-theme", "light")
        page.locator("#navigation").get_by_text("Обзор", exact=True).click()
        for width in (1440, 768, 390, 320):
            page.set_viewport_size({"width": width, "height": 900})
            assert_width(page)
            if width <= 390:
                assert page.locator("#navigation").evaluate("nav => nav.scrollWidth <= nav.clientWidth")
            for name in ("Документы", "AI Study", "История", "Настройки", "Обзор"):
                page.locator("#navigation").get_by_text(name, exact=True).click()
                expect(page.get_by_role("heading", name=name, exact=True, level=1)).to_be_visible()
                assert_width(page)
            if args.screenshots and width in (1440, 390):
                page.screenshot(path=args.screenshots / f"dashboard-light-{width}.png", full_page=True)

        page.locator("#navigation").get_by_text("Документы", exact=True).click()
        document_button.click()
        dialog.get_by_role("button", name="Удалить", exact=True).click()
        expect(dialog.get_by_role("heading", name="Удалить документ?")).to_be_visible()
        dialog.get_by_role("button", name="Удалить PDF").click()
        expect(page.get_by_text("Нет загруженных документов")).to_be_visible()
        page.locator("#navigation").get_by_text("История", exact=True).click()
        expect(page.get_by_text("История пока пуста")).to_be_visible()

        assert not page_errors, page_errors
        assert not console_errors, console_errors
        page.route("**/api/quota", lambda route: route.abort("internetdisconnected"))
        page.reload()
        expect(page.get_by_role("alert")).to_contain_text("Сервер недоступен")
        page.unroute("**/api/quota")
        page.get_by_role("button", name="Повторить", exact=True).click()
        expect(page.get_by_role("heading", name="История", exact=True)).to_be_visible()
        browser.close()
    print("Chromium: PDF, parsing error, Mock generation, quiz and retry, cards, history, deletion, theme, network recovery and 4 widths passed.")


if __name__ == "__main__":
    main()

