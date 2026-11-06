"""AIS A-1: браузерный стенд статей справки в шторке «✨ Assistent» (Playwright, Chromium).

Сценарий: «Zahlung & Lieferung» → кнопка ✨ → шторка показывает «Hilfe zu dieser Seite» →
статья раскрывается (details/summary) → ссылка ведёт на экран; поиск «Lieferung» — группы
«Anleitungen» и «Einstellungen»; ?artikel= раскрывает статью; русский интерфейс находит
статью по русскому слову; без JS — полная страница. Телефон 390 и 1440, без JS-ошибок
и горизонтального скролла.

    uv run python scripts/wizard_v4_pruefen_stand.py --setup        # бизнесы стенда, один раз
    uv run python scripts/wizard_v4_photo_stand.py --serve           # сервер стенда :8000
    uv run --with playwright==1.55.0 python scripts/assistant_help_stand.py

Не входит в CI (там нет браузера).
"""

from __future__ import annotations

import argparse
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__)))

from wizard_v4_pruefen_stand import BASE, CHROME, PASSWORD, Run  # noqa: E402

SLUG = "pbaeck"


def _ctx(browser, width, lang="de-DE", js=True):
    ctx = browser.new_context(
        viewport={"width": width, "height": 900}, locale=lang, java_script_enabled=js
    )
    page = ctx.new_page()
    errors = []
    page.on("pageerror", lambda e: errors.append(str(e)))
    url = f"http://{SLUG}.{BASE}:{{port}}"
    return ctx, page, errors, url


def _login(page, url):
    page.goto(url + "/accounts/login/")
    page.fill("input[name=login]", f"owner@{SLUG}.test")
    page.fill("input[name=password]", PASSWORD)
    page.click("button[type=submit]")


def _health(run, page, errors, label, width):
    scroll = page.evaluate("document.documentElement.scrollWidth")
    run.check(scroll <= width + 2, f"{label}: без горизонтального скролла ({scroll}px)")
    run.check(not errors, f"{label}: без JS-ошибок {errors[:2]}")
    errors.clear()


def drawer(run, browser, port, width):
    print(f"Шторка {width}px")
    ctx, page, errors, url = _ctx(browser, width)
    url = url.format(port=port)
    _login(page, url)
    page.goto(url + "/dashboard/settings/payments/")
    page.click("[data-assistant-open]")
    page.wait_for_selector("dialog[open] [data-help-here]", timeout=10000)
    dlg = page.locator("dialog[open]")
    run.check(dlg.locator('[data-help="bezahlung"]').count() == 1, "«Hilfe»: статья «Bezahlung»")
    dlg.locator('[data-help="bezahlung"] summary').click()
    run.check(
        dlg.locator('[data-help="bezahlung"] ol li').first.is_visible(),
        "статья раскрывается, шаги видны",
    )
    target = dlg.locator('[data-help="bezahlung"] a').first
    run.check(
        "/dashboard/settings/payments/" in (target.get_attribute("href") or ""), "ссылка на экран"
    )
    _health(run, page, errors, "Шторка", width)
    page.goto(url + "/dashboard/assistent/?q=Lieferung")
    run.check(page.locator("[data-help-results]").count() == 1, "поиск: группа «Anleitungen»")
    run.check(
        page.locator('[data-help="lieferung_abholung"]').count() == 1, "поиск: статья доставки"
    )
    run.check("Nichts gefunden" not in page.content(), "нет «Nichts gefunden» при находке")
    page.goto(url + "/dashboard/assistent/?artikel=oeffnungszeiten")
    run.check(
        page.locator('details[open][data-help="oeffnungszeiten"]').count() == 1,
        "?artikel= раскрывает статью",
    )
    page.goto(url + "/dashboard/assistent/?artikel=%3Cscript%3Ex")
    run.check("<script>x" not in page.content(), "мусорный ?artikel= не отражается")
    _health(run, page, errors, "Полная страница", width)
    ctx.close()


def russian(run, browser, port):
    print("Русский интерфейс")
    ctx, page, errors, url = _ctx(browser, 390, lang="ru-RU")
    url = url.format(port=port)
    _login(page, url)
    page.goto(url + "/dashboard/assistent/?q=доставка")
    body = page.content()
    run.check('data-help="lieferung_abholung"' in body, "ru: «доставка» находит статью")
    run.check("Доставка и самовывоз" in body, "ru: заголовок статьи переведён")
    _health(run, page, errors, "ru", 390)
    ctx.close()


def without_js(run, browser, port):
    print("Без JS")
    ctx, page, errors, url = _ctx(browser, 390, js=False)
    url = url.format(port=port)
    _login(page, url)
    page.goto(url + "/dashboard/assistent/?seite=payment-settings")
    run.check(page.locator("[data-help-here]").count() == 1, "без JS: «Hilfe» на полной странице")
    page.locator('[data-help="bezahlung"] summary').click()
    run.check(page.locator('[data-help="bezahlung"] ol li').first.is_visible(), "без JS: раскрытие")
    ctx.close()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()
    from playwright.sync_api import sync_playwright

    run = Run()
    with sync_playwright() as p:
        browser = p.chromium.launch(
            executable_path=CHROME, args=[f"--host-resolver-rules=MAP *.{BASE} 127.0.0.1"]
        )
        for width in (390, 1440):
            drawer(run, browser, args.port, width)
        russian(run, browser, args.port)
        without_js(run, browser, args.port)
        browser.close()
    print(f"\n{run.ok} ok, {len(run.fail)} fail")
    for f in run.fail:
        print("  FAIL:", f)
    sys.exit(1 if run.fail else 0)


if __name__ == "__main__":
    main()
