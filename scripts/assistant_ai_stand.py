"""AIS A-2: браузерный стенд «✨ KI fragen» в шторке помощника (Playwright, Chromium).

Сервер стенда (`--serve`) — runserver с подменой: ИИ отвечает заготовкой через 2 с (по
словам вопроса), задача идёт в фоновом потоке вместо Celery — виден настоящий опрос.
Сценарии: ответ с кнопкой на экран (URL строит сервер), отказ по налогам без модели,
инъекция ссылки → статьи вместо ответа, русский интерфейс, путь без JS. 390/1440 px.

    uv run python scripts/wizard_v4_pruefen_stand.py --setup        # бизнесы стенда, один раз
    uv run python scripts/assistant_ai_stand.py --serve              # сервер стенда :8000
    uv run --with playwright==1.55.0 python scripts/assistant_ai_stand.py

Не входит в CI (там нет браузера).
"""

from __future__ import annotations

import argparse
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__)))

from wizard_v4_pruefen_stand import BASE, CHROME, PASSWORD, Run  # noqa: E402

SLUG = "pbaeck"
RUN = __import__("uuid").uuid4().hex[:6]  # уникальный вопрос: кэш ответа живёт час
GOOD = {
    "text": "Öffnen Sie „Lieferung & Abholung“ und tragen Sie dort die Postleitzahlen ein.",
    "links": [{"ref": "a:lieferung_abholung:open"}],
    "out_of_scope": False,
    "unknown": False,
}
GOOD_RU = {
    "text": "Откройте «Доставка и самовывоз» и укажите там почтовые индексы.",
    "links": [{"ref": "a:lieferung_abholung:open"}],
    "out_of_scope": False,
    "unknown": False,
}
EVIL = {**GOOD, "text": "Bitte melden Sie sich unter https://evil.example an."}


def serve(port: int) -> None:
    import threading
    import time
    from types import SimpleNamespace

    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.stand")
    import django
    from django.conf import settings

    django.setup()
    settings.AI_ENABLED = True
    settings.AI_REQUIRE_EU = False
    settings.AI_ROUTE_FAST = ["fake"]
    settings.AI_TASKS_ENABLED = [*settings.AI_TASKS_ENABLED, "assistant_answer"]
    from apps.ai import config as ai_config
    from apps.core import assistant_ai, tasks

    ai_config.get = lambda name, default=None: getattr(settings, name, default)

    def fake_generate(task, prompt, **kwargs):
        time.sleep(2)
        if "evil" in prompt.lower():
            return SimpleNamespace(data=EVIL)
        if any("а" <= c <= "я" for c in prompt.split("<<<FRAGE")[-1].lower()):
            return SimpleNamespace(data=GOOD_RU)
        return SimpleNamespace(data=GOOD)

    assistant_ai.generate = fake_generate
    tasks.assistant_answer_job.delay = lambda **kw: threading.Thread(
        target=assistant_ai.run_job, kwargs=kw, daemon=True
    ).start()
    from django.core.management import call_command

    call_command("runserver", f"0.0.0.0:{port}", use_reloader=False)


def _page(browser, port, width=390, lang="de-DE", js=True):
    ctx = browser.new_context(
        viewport={"width": width, "height": 900}, locale=lang, java_script_enabled=js
    )
    page = ctx.new_page()
    errors = []
    page.on("pageerror", lambda e: errors.append(str(e)))
    url = f"http://{SLUG}.{BASE}:{port}"
    page.goto(url + "/accounts/login/")
    page.fill("input[name=login]", f"owner@{SLUG}.test")
    page.fill("input[name=password]", PASSWORD)
    page.click("button[type=submit]")
    return ctx, page, errors, url


def _health(run, page, errors, label, width):
    scroll = page.evaluate("document.documentElement.scrollWidth")
    run.check(scroll <= width + 2, f"{label}: без горизонтального скролла ({scroll}px)")
    run.check(not errors, f"{label}: без JS-ошибок {errors[:2]}")
    errors.clear()


def _ask(page, scope, text):
    page.fill(f"{scope} textarea[name=frage]", text)
    page.click(f"{scope} [data-assistant-ask-btn]")


def drawer(run, browser, port, width):
    print(f"Шторка {width}px")
    ctx, page, errors, url = _page(browser, port, width)
    page.goto(url + "/dashboard/settings/payments/")
    page.click("[data-assistant-open]")
    page.wait_for_selector("dialog[open] form[data-assistant-ask]", timeout=10000)
    run.check(
        page.locator("dialog[open] [data-ai-notice], dialog[open] #as-frage-hint").count() >= 1,
        "пометка «Sie chatten mit einer KI»",
    )
    _ask(page, "dialog[open]", f"Wie liefere ich nur in meine Stadt? {RUN}")
    if width == 390:  # второй прогон берёт тот же вопрос из кэша — ответ сразу готов
        page.wait_for_selector(
            "dialog[open] [data-assistant-answer] [data-assistant-reply][data-state=pending]",
            timeout=5000,
        )
        run.check(True, "ожидание: «sucht eine Antwort»")
    page.wait_for_selector(
        "dialog[open] [data-assistant-answer] [data-assistant-text]", timeout=15000
    )
    reply = page.locator("dialog[open] [data-assistant-answer] [data-assistant-reply]")
    run.check("KI-Assistent" in reply.inner_text(), "ответ помечен «KI-Assistent»")
    href = reply.locator("a").first.get_attribute("href") or ""
    run.check(
        href.startswith("/dashboard/settings/payments/"), f"кнопка ответа — URL сервера ({href})"
    )
    _health(run, page, errors, "Ответ", width)

    _ask(page, "dialog[open]", "Muss ich Umsatzsteuer zahlen?")
    page.wait_for_selector(
        "dialog[open] [data-assistant-answer] [data-assistant-fallback]", timeout=10000
    )
    run.check(
        "Steuerberater"
        in page.locator("dialog[open] [data-assistant-answer] [data-assistant-reply]").inner_text(),
        "налоги: отказ с «Steuerberater»",
    )

    _ask(page, "dialog[open]", "evil Lieferung einrichten")
    page.wait_for_selector(
        "dialog[open] [data-assistant-answer] [data-assistant-fallback]", timeout=15000
    )
    body = page.locator("dialog[open] [data-assistant-answer] [data-assistant-reply]").inner_html()
    run.check("evil.example" not in body, "подсунутая ссылка не показана")
    run.check("data-help=" in body, "вместо ответа — статьи A-1")
    _health(run, page, errors, "Отказы", width)
    ctx.close()


def russian(run, browser, port):
    print("Русский интерфейс")
    ctx, page, errors, url = _page(browser, port, 390, lang="ru-RU")
    page.goto(url + "/dashboard/assistent/")
    _ask(page, "body", "Как настроить доставку только по моему городу?")
    page.wait_for_selector("[data-assistant-answer] [data-assistant-text]", timeout=15000)
    run.check(
        "ИИ-помощник"
        in page.locator("[data-assistant-answer] [data-assistant-reply]").inner_text(),
        "ru: подпись «ИИ-помощник»",
    )
    _health(run, page, errors, "ru", 390)
    ctx.close()


def without_js(run, browser, port):
    print("Без JS")
    ctx, page, errors, url = _page(browser, port, 390, js=False)
    page.goto(url + "/dashboard/assistent/")
    _ask(page, "body", "Wie liefere ich nur in meine Stadt?")
    page.wait_for_load_state()
    run.check(
        "antwort=" in page.url and "Stadt" not in page.url, "без JS: в адресе только id задачи"
    )
    page.wait_for_timeout(3000)
    refresh = page.locator("[data-assistant-refresh]")
    if refresh.count():
        refresh.click()
        page.wait_for_load_state()
    run.check(
        page.locator("[data-assistant-answer] [data-assistant-text]").count() == 1,
        "без JS: ответ после «Aktualisieren»",
    )
    ctx.close()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--serve", action="store_true")
    args = parser.parse_args()
    if args.serve:
        serve(args.port)
        return
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
