"""AIS-7: стенд «✨ Text vorschlagen» (Python-Playwright, не входит в CI).

Нужен сервер с ИИ на фейковом маршруте (настройки стенда — docs/ais-7-texts-from-facts-
plan-2026-11-06.md) и тенант с владельцем (сквозной стенд мастера создаёт `e2ebaeck`).

    uv run --with playwright==1.55.0 python scripts/ais7_text_draft_stand.py --port 8001

Проверяет: у нового товара — подсказка «Erst speichern»; у сохранённого с текстом —
предложение рядом, «Übernehmen» заменяет, «Rückgängig» возвращает; «Über uns» в Студии
заполняется в пустые поля; 390 px без скролла и JS-ошибок.
"""

from __future__ import annotations

import argparse
import sys

CHROME = "/opt/pw-browsers/chromium"
BASE = "siteadaptor.de"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=8001)
    parser.add_argument("--slug", default="e2ebaeck")
    parser.add_argument("--password", default="Stand-Passwort-123")
    parser.add_argument("--product", required=True, help="pk товара с заполненным описанием")
    args = parser.parse_args()
    from playwright.sync_api import sync_playwright

    url = f"http://{args.slug}.{BASE}:{args.port}"
    ok, fail = 0, []

    def check(cond, label):
        nonlocal ok
        if cond:
            ok += 1
            print(f"  ✓ {label}")
        else:
            fail.append(label)
            print(f"  ✗ {label}")

    def wait_status(page, box, needle):
        page.wait_for_function(
            "([b, n]) => (document.querySelector(b + ' [data-ai-draft-status]').textContent"
            " || '').indexOf(n) !== -1",
            arg=[box, needle],
            timeout=20000,
        )

    with sync_playwright() as p:
        browser = p.chromium.launch(
            executable_path=CHROME, args=[f"--host-resolver-rules=MAP *.{BASE} 127.0.0.1"]
        )
        for width in (1440, 390):
            print(f"\nText vorschlagen · {width}px")
            ctx = browser.new_context(viewport={"width": width, "height": 900}, locale="de-DE")
            page = ctx.new_page()
            errors = []
            page.on("pageerror", lambda e, errs=errors: errs.append(str(e)))
            page.goto(url + "/accounts/login/")
            page.fill("input[name=login]", f"owner@{args.slug}.test")
            page.fill("input[name=password]", args.password)
            page.click("button[type=submit]")
            page.wait_for_load_state()

            page.goto(url + "/catalog/products/new/")
            check(
                page.locator("[data-ai-draft-unsaved]").count() == 1,
                "новый товар: «Erst speichern»",
            )

            page.goto(url + f"/catalog/products/{args.product}/edit/")
            area = page.locator("#id_description_de + * .rte-area")
            before = area.inner_html()
            page.click("[data-ai-draft-box] [data-ai-draft]")
            wait_status(page, "[data-ai-draft-box]", "Vorschlag unten")
            check(area.inner_html() == before, "заполненное описание не тронуто")
            page.click("[data-ai-draft-take]")
            check("Frisch gebacken" in area.inner_text(), "«Übernehmen» заменил описание")
            page.click("[data-ai-draft-undo]")
            check(area.inner_html() == before, "«Rückgängig» вернул прежний текст")

            page.goto(url + "/dashboard/site/home/")
            page.wait_for_load_state()
            title = page.locator("input[name=about_title]")
            if title.count():
                page.evaluate(
                    "() => { for (const n of ['about_title', 'about_text']) {"
                    " const el = document.querySelector('[name=' + n + ']'); el.value = ''; } }"
                )
                box = page.locator("[data-ai-draft-box][data-kind=about]")
                check(box.count() == 1, "Студия: кнопка у «Über uns»")
                page.evaluate(
                    "() => document.querySelector('[data-ai-draft-box][data-kind=about]"
                    " [data-ai-draft]').click()"
                )
                wait_status(page, "[data-ai-draft-box][data-kind=about]", "eingefügt")
                check(title.input_value() == "Willkommen bei uns", "«Über uns»: заголовок заполнен")
            else:
                check(False, "Студия: поле about_title есть")
            scroll = page.evaluate("document.documentElement.scrollWidth")
            check(scroll <= width + 2, f"без горизонтального скролла ({scroll}px)")
            check(not errors, f"без JS-ошибок {errors[:2]}")
            ctx.close()
        browser.close()
    print(f"\n{ok} ok, {len(fail)} fail")
    for f in fail:
        print("  FAIL:", f)
    sys.exit(1 if fail else 0)


if __name__ == "__main__":
    main()
