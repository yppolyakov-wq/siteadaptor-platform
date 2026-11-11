"""M21.11 P5b: браузерный стенд «вставок» редактора страниц.

Ссылка на свою страницу из списка, кнопка-призыв, раскрывашка «Frage/Antwort»,
галерея из нескольких фото, медиатека, фото-ссылка и замена фото → витрина.

    python manage.py runserver 0.0.0.0:8000 --settings=config.settings.stand
    uv run python scripts/text_pages_stand.py --setup     # один раз (тенант ptx)
    uv run --with playwright==1.55.0 python scripts/editor_p5b_stand.py

Не входит в CI (там нет браузера).
"""

from __future__ import annotations

import argparse
import io
import tempfile

CHROME = "/opt/pw-browsers/chromium"
BASE = "siteadaptor.de"
SLUG = "ptx"
PASSWORD = "Stand-Passwort-123"


def _png(color) -> str:
    from PIL import Image

    buf = io.BytesIO()
    Image.new("RGB", (640, 480), color).save(buf, "PNG")
    f = tempfile.NamedTemporaryFile(suffix=".png", delete=False)
    f.write(buf.getvalue())
    f.close()
    return f.name


def main():  # noqa: PLR0915 — один линейный сценарий стенда
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8000)
    args = ap.parse_args()
    from playwright.sync_api import sync_playwright

    ok, fail = 0, []

    def check(cond, label):
        nonlocal ok
        ok += bool(cond)
        if not cond:
            fail.append(label)
        print(("  ✓ " if cond else "  ✗ ") + label)

    url = f"http://{SLUG}.{BASE}:{args.port}"
    with sync_playwright() as p:
        browser = p.chromium.launch(
            executable_path=CHROME, args=[f"--host-resolver-rules=MAP *.{BASE} 127.0.0.1"]
        )
        page = browser.new_context(
            viewport={"width": 1440, "height": 900}, locale="de-DE"
        ).new_page()
        errors = []
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.goto(url + "/accounts/login/")
        page.fill("input[name=login]", f"owner@{SLUG}.test")
        page.fill("input[name=password]", PASSWORD)
        page.click("button[type=submit]")
        page.wait_for_load_state()

        page.goto(url + "/dashboard/site/seiten/neu/")
        page.fill("input[name=title]", "P5b Stand")
        page.fill("input[name=slug]", "p5b-stand")
        area = page.locator(".rte-area")
        area.click()
        page.keyboard.type("Mehr dazu ")

        print("Link zu einer Seite")
        page.click("[data-rte-cmd=pageLink]")
        dlg = page.locator(".rte-pop[role=dialog]")
        check(dlg.count() == 1, "окно выбора страницы")
        check(
            page.get_attribute("[data-rte-cmd=pageLink]", "aria-expanded") == "true",
            "aria-expanded",
        )
        page.keyboard.type("Über")
        btn = dlg.locator("ul button").first
        check(btn.count() == 1, "поиск находит «Über uns»")
        btn.click()
        check(area.locator('a[href="/ueber-uns/"]').count() == 1, "ссылка на свою страницу")

        print("Schaltfläche")
        page.keyboard.press("End")
        page.click("[data-rte-cmd=ctaButton]")
        page.fill(".rte-pop input[id$='-t']", "Jetzt anfragen")
        page.fill(".rte-pop input[id$='-u']", "javascript:alert(1)")
        page.click(".rte-pop button:has-text('Einfügen')")
        check(area.locator("a.sf-btn").count() == 0, "javascript: отклонён")
        page.fill(".rte-pop input[id$='-u']", "https://example.org/kontakt")
        page.click(".rte-pop button:has-text('Einfügen')")
        check(
            area.locator('a.sf-btn[href="https://example.org/kontakt"]').count() == 1,
            "кнопка-призыв вставлена",
        )

        print("Frage & Antwort")
        page.click("[data-rte-cmd=faq]")
        page.keyboard.type("Wann liefern Sie?")
        page.keyboard.press("Enter")
        page.keyboard.type("Dienstags.")
        check(area.locator("details summary").inner_text().strip() == "Wann liefern Sie?", "вопрос")
        check("Dienstags." in area.locator("details").inner_text(), "Enter в вопросе → ответ")

        print("Galerie")
        with page.expect_file_chooser() as fc:
            page.click("[data-rte-cmd=gallery]")
        fc.value.set_files([_png((200, 80, 80)), _png((80, 200, 80)), _png((80, 80, 200))])
        page.wait_for_function(
            "document.querySelectorAll('.rte-area .sf-gallery figure').length === 3"
        )
        check(area.locator(".sf-gallery figure").count() == 3, "галерея из 3 фото")

        print("Foto: Link + ersetzen")
        area.locator(".sf-gallery figure").first.click()
        pop = page.locator(".rte-pop")
        ln = pop.locator("input[id$='-ln']")
        ln.fill("/ueber-uns/")
        ln.press("Tab")
        check(
            area.locator('.sf-gallery figure a[href="/ueber-uns/"] img').count() == 1, "фото-ссылка"
        )
        old_src = area.locator(".sf-gallery figure img").first.get_attribute("src")
        with page.expect_file_chooser() as fc:
            pop.locator("button:has-text('Bild ersetzen')").click()
        fc.value.set_files(_png((10, 10, 10)))
        page.wait_for_function(
            "(s) => document.querySelector('.rte-area .sf-gallery figure img').getAttribute('src') !== s",
            arg=old_src,
        )
        check(True, "фото заменено")
        page.keyboard.press("Escape")

        print("Mediathek")
        page.click("[data-rte-cmd=mediaLib]")
        page.wait_for_selector(".rte-pop button img")
        n = page.locator(".rte-pop button img").count()
        check(n >= 3, f"медиатека показывает загруженное ({n})")
        page.locator(".rte-pop button").first.click()
        check(area.locator(":scope > figure").count() >= 1, "фото из медиатеки вставлено")
        page.keyboard.press("Escape")

        page.click("button:has-text('Speichern')")
        page.wait_for_load_state()

        print("Витрина")
        page.goto(url + "/seite/p5b-stand/")
        body = page.locator("[data-page-body]")
        check(body.locator('a[href="/ueber-uns/"]').count() >= 1, "ссылка на свою страницу")
        check(body.locator("a.sf-btn").count() == 1, "кнопка")
        bg = page.evaluate(
            "() => getComputedStyle(document.querySelector('a.sf-btn')).backgroundColor"
        )
        check(bg not in ("rgba(0, 0, 0, 0)", "transparent"), "кнопка с фоном")
        check(body.locator("details:not([open]) summary").count() == 1, "раскрывашка закрыта")
        body.locator("summary").click()
        check(body.locator("details[open]").count() == 1, "раскрывается по клику")
        check(body.locator(".sf-gallery figure").count() == 3, "галерея")
        check(not errors, "без JS-ошибок: " + "; ".join(errors[:3]))
        browser.close()
    print(f"\n{ok}/{ok + len(fail)}")
    raise SystemExit(1 if fail else 0)


if __name__ == "__main__":
    main()
