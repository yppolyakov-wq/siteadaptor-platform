"""M21.11 P5: браузерный стенд пакета 🟢 редактора страниц.

Зачёркнутый/индексы/«убрать форматирование», стиль абзаца (Lead/klein/Hinweis),
вложенный список по Tab, три колонки, эмодзи, вставка как текст (Ctrl+Shift+V),
полный экран, автосохранение черновика → сохранение → витрина.

    python manage.py runserver 0.0.0.0:8000 --settings=config.settings.stand
    uv run python scripts/text_pages_stand.py --setup     # один раз (тенант ptx)
    uv run --with playwright==1.55.0 python scripts/editor_p5_stand.py

Не входит в CI (там нет браузера).
"""

from __future__ import annotations

import argparse

CHROME = "/opt/pw-browsers/chromium"
BASE = "siteadaptor.de"
SLUG = "ptx"
PASSWORD = "Stand-Passwort-123"


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
        ctx = browser.new_context(viewport={"width": 1440, "height": 900}, locale="de-DE")
        page = ctx.new_page()
        errors = []
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.goto(url + "/accounts/login/")
        page.fill("input[name=login]", f"owner@{SLUG}.test")
        page.fill("input[name=password]", PASSWORD)
        page.click("button[type=submit]")
        page.wait_for_load_state()

        print("Neue Seite: Vorlagen")
        page.goto(url + "/dashboard/site/seiten/")
        page.click("[data-page-new] summary")
        check(page.is_visible("[data-page-starter=faq]"), "меню заготовок открывается")
        page.click("[data-page-starter=faq]")
        page.wait_for_load_state()
        check("Häufige Fragen" in page.input_value("input[name=title]"), "FAQ-заготовка в форме")
        area = page.locator(".rte-area")
        check("Wie kann ich bestellen?" in area.inner_text(), "вопросы FAQ в редакторе")

        print("Zeichen")
        page.fill("input[name=title]", "P5 Stand")
        page.fill("input[name=slug]", "p5-stand")
        area.click()
        page.keyboard.press("Control+End")
        page.keyboard.press("Enter")
        page.keyboard.type("Streich")
        page.keyboard.press("Shift+Home")
        page.click("[data-rte-cmd=strikeThrough]")
        check(area.locator("strike, s").count() == 1, "зачёркнутый")
        page.keyboard.press("End")
        page.keyboard.press("Enter")
        page.keyboard.type("m2")
        page.keyboard.press("Shift+ArrowLeft")
        page.click("[data-rte-cmd=superscript]")
        check(area.locator("sup").count() == 1, "верхний индекс")

        print("Absatz")
        page.keyboard.press("End")
        page.keyboard.press("Enter")
        page.keyboard.type("Wichtiger Hinweis")
        page.click("[data-rte-cmd=sf-note]")
        check(area.locator("p.sf-note").count() == 1, "плашка Hinweis")
        check(
            page.get_attribute("[data-rte-cmd=sf-note]", "aria-pressed") == "true",
            "кнопка Hinweis нажата",
        )
        page.click("[data-rte-cmd=sf-lead]")
        check(
            area.locator("p.sf-lead").count() == 1 and area.locator("p.sf-note").count() == 0,
            "стиль абзаца взаимоисключающий",
        )

        print("Liste + Tab")
        page.keyboard.press("End")
        page.keyboard.press("Enter")
        page.click("[data-rte-cmd=insertUnorderedList]")
        page.keyboard.type("Eins")
        page.keyboard.press("Enter")
        page.keyboard.type("Zwei")
        page.keyboard.press("Tab")
        check(area.locator("ul ul li, ul li ul li").count() >= 1, "Tab — вложенный список")
        page.keyboard.press("Shift+Tab")
        check(area.locator("ul ul").count() == 0, "Shift+Tab — обратно")
        # a11y: в первом пункте Tab не ловушка — фокус уходит из текста.
        area.locator("li >> nth=0").click()
        page.keyboard.press("Tab")
        left = page.evaluate("() => !document.activeElement.classList.contains('rte-area')")
        check(left, "Tab в первом пункте уводит фокус (нет ловушки)")
        area.locator("li >> nth=1").click()
        page.keyboard.press("End")
        page.keyboard.press("Enter")
        page.keyboard.press("Enter")

        print("Drei Spalten + Emoji")
        page.click("[data-rte-cmd=columns3]")
        check(area.locator("div.sf-grid3 > div").count() == 3, "три колонки")
        page.keyboard.type("Links")
        page.click("[data-rte-cmd=emoji]")
        check(page.is_visible(".rte-emoji"), "окно эмодзи")
        page.keyboard.press("Escape")
        check(not page.is_visible(".rte-emoji"), "Esc закрывает эмодзи")
        page.click("[data-rte-cmd=emoji]")
        page.click(".rte-emoji button >> nth=3")
        check("👍" in area.inner_text(), "эмодзи вставлен")

        print("Als Text einfügen")
        # http-стенд: доступа к буферу нет — та же последовательность, что у браузера:
        # клавиши Strg+Shift+V, затем событие paste с HTML и текстом.
        page.evaluate(
            """() => { const a = document.querySelector('.rte-area');
              a.dispatchEvent(new KeyboardEvent('keydown', {key: 'V', ctrlKey: true, shiftKey: true, bubbles: true}));
              const dt = new DataTransfer();
              dt.setData('text/html', '<b>FETT</b>'); dt.setData('text/plain', 'FETT');
              a.dispatchEvent(
                new ClipboardEvent('paste', {clipboardData: dt, bubbles: true, cancelable: true})); }"""
        )
        page.wait_for_timeout(200)
        check(
            "FETT" in area.inner_text() and area.locator("b:has-text('FETT')").count() == 0,
            "Strg+Shift+V — без форматирования",
        )

        print("Vollbild")
        page.click("[data-rte-cmd=fullscreen]")
        check(page.locator(".rte-wrap.rte-full").count() == 1, "полный экран")
        check(
            page.evaluate(
                "() => document.querySelector('header, nav, aside')?.closest('[inert]') !== null"
            ),
            "страница под оверлеем inert",
        )
        check(page.get_attribute(".rte-wrap", "aria-modal") == "true", "aria-modal")
        page.focus("[data-rte-cmd=bold]")
        page.keyboard.press("Escape")
        check(page.locator(".rte-wrap.rte-full").count() == 0, "Esc с кнопки панели выходит")
        page.click("[data-rte-cmd=fullscreen]")
        area.click()
        page.keyboard.press("Escape")
        check(page.locator(".rte-wrap.rte-full").count() == 0, "Esc выходит")

        print("Entwurf")
        page.wait_for_timeout(1000)
        page.reload()
        check(page.is_visible(".rte-draft"), "черновик предложен после перезагрузки")
        page.click(".rte-draft button >> nth=0")
        check("Links" in page.locator(".rte-area").inner_text(), "черновик восстановлен")
        page.fill("input[name=title]", "P5 Stand")
        page.fill("input[name=slug]", "p5-stand")
        page.click("button:has-text('Speichern')")
        page.wait_for_load_state()
        stored = page.evaluate(
            "() => Object.keys(localStorage).filter(k => k.startsWith('rte-draft:')).length"
        )
        check(stored == 0, "после «Speichern» черновик удалён")

        print("Витрина")
        page.goto(url + "/seite/p5-stand/")
        body = page.locator("[data-page-body]")
        check(body.locator("strike, s").count() >= 1, "зачёркнутый на витрине")
        check(body.locator("sup").count() >= 1, "sup на витрине")
        check(body.locator("p.sf-lead").count() >= 1, "Lead на витрине")
        check(body.locator(".sf-grid3 > div").count() == 3, "три колонки на витрине")
        cols = page.evaluate(
            "() => getComputedStyle(document.querySelector('.sf-grid3')).gridTemplateColumns"
            ".split(' ').length"
        )
        check(cols == 3, "сетка из 3 колонок на десктопе")
        page.set_viewport_size({"width": 390, "height": 800})
        cols = page.evaluate("() => getComputedStyle(document.querySelector('.sf-grid3')).display")
        check(cols != "grid", "на телефоне колонки друг под другом")
        check(not errors, "без JS-ошибок: " + "; ".join(errors[:3]))
        browser.close()
    print(f"\n{ok}/{ok + len(fail)}")
    raise SystemExit(1 if fail else 0)


if __name__ == "__main__":
    main()
