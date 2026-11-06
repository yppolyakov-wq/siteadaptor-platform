"""AIS W4-6: сквозной стенд мастера v4 — от `/registrieren/` до опубликованного сайта.

Пять типов (Waren · Termine · Zimmer · Tickets · Anfragen) на телефоне 390 px, bakery и hotel
ещё и на 1440 px. Путь: регистрация → письмо (прямая ссылка console-бэкенда) → пароль →
ожидание схемы → вход → Firma → Angebot prüfen → Recht (отказ, затем публикация) → Fertig →
главная кабинета с «Nächster Schritt» → «Verkauf öffnen». Гость: 503 до публикации, 200 после.
На каждой странице: без JS-ошибок и горизонтального скролла. План —
docs/ais-w4-6-wizard-stand-plan-2026-11-06.md (там же команды сервера и Celery).

    uv run --with playwright==1.55.0 python scripts/wizard_v4_e2e_stand.py

Хосты `*.siteadaptor.de` и `siteadaptor.de` направляются на локальный сервер правилом
резолвера Chromium; публичному хосту нужен Domain у public-тенанта. Не входит в CI.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
import time

CHROME = "/opt/pw-browsers/chromium"
BASE = "siteadaptor.de"
PASSWORD = "Stand-Passwort-123"
# (slug, тип, ширина)
PERSONAS = [
    ("e2ebaeck", "bakery", 390),
    ("e2efris", "friseur", 390),
    ("e2ehotel", "hotel", 390),
    ("e2eevent", "events", 390),
    ("e2ehand", "handwerker", 390),
    ("e2ebaeckd", "bakery", 1440),
    ("e2ehoteld", "hotel", 1440),
]

CLEAN = """
from django.core.cache import cache
from apps.tenants.models import Tenant, SignupRequest
slugs = {slugs!r}
SignupRequest.objects.filter(slug__in=slugs).delete()
for t in Tenant.objects.filter(slug__in=slugs):
    t.delete(force_drop=True)
client = cache._cache.get_client() if hasattr(cache, "_cache") else None
n = 0
if client is not None:
    for key in client.scan_iter("*rl:*"):
        client.delete(key); n += 1
print("CLEAN", n)
"""


class Run:
    def __init__(self):
        self.ok = 0
        self.fail = []

    def check(self, cond, label):
        if cond:
            self.ok += 1
            print(f"  ✓ {label}")
        else:
            self.fail.append(label)
            print(f"  ✗ {label}")


def _shell(code: str) -> str:
    out = subprocess.run(
        [sys.executable, "manage.py", "shell", "--settings=config.settings.stand", "-c", code],
        capture_output=True,
        text=True,
        check=False,
    )
    return out.stdout + out.stderr[-800:]


def _health(run, page, errors, label, width):
    scroll = page.evaluate("document.documentElement.scrollWidth")
    run.check(scroll <= width + 2, f"{label}: без горизонтального скролла ({scroll}px)")
    run.check(not errors, f"{label}: без JS-ошибок {errors[:2]}")
    errors.clear()


def _primary(page):
    page.locator("main button.ui-btn-primary[type=submit]").last.click()
    page.wait_for_load_state()


def register(run, page, errors, port, slug, btype, width):
    pub = f"http://{BASE}:{port}"
    page.goto(f"{pub}/registrieren/?type={btype}")
    if page.locator(f"input[type=radio][name=business_type][value={btype}]").count():
        page.check(f"input[type=radio][name=business_type][value={btype}]")
    page.fill("input[name=business_name]", f"Stand {btype}")
    page.fill("input[name=city]", "Hilden")
    page.fill("input[name=slug]", slug)
    page.fill("input[name=email]", f"owner@{slug}.test")
    page.fill("input[name=password1]", PASSWORD)
    page.fill("input[name=password2]", PASSWORD)
    _health(run, page, errors, "Registrierung", width)
    page.locator("form button[type=submit]").last.click()
    page.wait_for_load_state()
    link = page.locator("a[href*='/registrieren/bestaetigen/']")
    run.check(link.count() == 1, "письмо подтверждения: прямая ссылка")
    if not link.count():
        return False
    page.goto(link.first.get_attribute("href"))
    page.fill("input[name=password]", PASSWORD)
    page.locator("form button[type=submit]").last.click()
    for _ in range(60):
        page.wait_for_load_state()
        if f"{slug}.{BASE}" in page.url:
            break
        time.sleep(2)
        page.reload()
    run.check(f"{slug}.{BASE}" in page.url, f"схема готова → поддомен ({page.url[:60]})")
    return f"{slug}.{BASE}" in page.url


def owner_path(run, browser, port, slug, btype, width):
    print(f"\n{btype} · {width}px ({slug})")
    url = f"http://{slug}.{BASE}:{port}"
    ctx = browser.new_context(viewport={"width": width, "height": 900}, locale="de-DE")
    page = ctx.new_page()
    errors = []
    page.on("pageerror", lambda e: errors.append(str(e)))
    if not register(run, page, errors, port, slug, btype, width):
        ctx.close()
        return
    guest = browser.new_context(locale="de-DE").new_page()
    run.check(guest.goto(url + "/").status == 503, "гость до публикации: 503")

    if "/accounts/login/" in page.url or page.locator("input[name=login]").count():
        page.fill("input[name=login]", f"owner@{slug}.test")
        page.fill("input[name=password]", PASSWORD)
        page.click("button[type=submit]")
        page.wait_for_load_state()
    page.goto(url + "/dashboard/")
    run.check("/dashboard/setup/" in page.url, "кабинет уводит в мастер")
    # AIS-3: первый шаг — «Was haben Sie schon?»; без ключей видны Website и «Nichts».
    run.check(page.locator("[data-quelle-form]").count() == 1, "шаг «Was haben Sie schon?»")
    run.check(
        page.locator('[data-quelle-option="website"]').count() == 1
        and page.locator('[data-quelle-option="none"]').count() == 1,
        "карточки Website и «Nichts davon»",
    )
    _health(run, page, errors, "Was haben Sie schon?", width)
    run.check(page.locator("textarea[name=sentence]").count() == 1, "поле «in einem Satz»")
    page.check("input[name=had][value=none]")
    if btype == "bakery":  # AIS-2: фраза → строки «Angebot prüfen», в базу ничего
        page.fill("textarea[name=sentence]", "Bäckerei: Brötchen 0,50 €, Brezel 0,80 €")
    _primary(page)
    run.check(page.locator("[data-setup-hours]").count() == 1, "Firma: часы сеткой")
    _health(run, page, errors, "Firma", width)
    page.fill("#id_address", "Hauptstraße 1, 40721 Hilden")
    page.fill("#id_contact_phone", "02103 12345")
    page.fill("input[name=oh_0_open]", "08:00")
    page.fill("input[name=oh_0_close]", "18:00")
    _primary(page)

    run.check(
        page.locator("[data-pruefen-form], [data-pruefen-none]").count() == 1,
        "шаг «Angebot prüfen»",
    )
    _health(run, page, errors, "Angebot", width)
    if btype == "bakery" and page.locator("#id_pruefen_text").count():
        offer = page.locator("#id_pruefen_text").input_value()
        run.check("Brötchen — 0,50 €" in offer, "фраза → строки в «Prüfen»")
        run.check(
            page.locator("[data-pruefen-from-sentence]").count() == 1, "пометка «Aus Ihrem Satz»"
        )
    if page.locator("button[value=offer_examples]").count():
        page.click("button[value=offer_examples]")
        page.wait_for_load_state()
        page.click("[data-pruefen-preview]")
        page.wait_for_load_state()
        rows = page.locator("[data-pruefen-row]").count()
        run.check(rows >= 1, f"образцы → таблица: {rows} строк")
        _health(run, page, errors, "Prüfen", width)
        page.click("[data-pruefen-confirm]")
        page.wait_for_load_state()
        _health(run, page, errors, "Übernommen", width)
    else:
        run.check(False, "образцы для типа")
    if page.locator("[data-recht-form]").count() == 0:
        _primary(page)
    run.check(page.locator("[data-recht-form]").count() == 1, "шаг «Rechtliches & Veröffentlichen»")
    _health(run, page, errors, "Recht", width)

    page.click("[data-recht-publish]")
    page.wait_for_load_state()
    run.check(page.locator("[data-recht-blockers]").count() == 1, "без Impressum — недостающее")
    page.fill("#id_recht_legal_representative", "Anna Muster")
    page.select_option("#id_recht_legal_form", "ek")
    page.fill("#id_recht_register_court", "Amtsgericht Düsseldorf")
    page.fill("#id_recht_register_number", "HRA 12345")
    page.fill("#id_recht_tax_number", "135/5000/1234")
    page.click("[data-recht-publish]")
    page.wait_for_load_state()
    run.check("Ihre Website ist jetzt online" in page.content(), "«Fertig» после публикации")
    _health(run, page, errors, "Fertig", width)
    run.check(guest.goto(url + "/").status == 200, "гость после публикации: 200")
    if btype == "handwerker":  # W4-6b: Leistungen auf Anfrage — подпись вместо «0,00 €»
        guest.goto(url + "/sortiment/")
        body = guest.content()
        run.check("Preis auf Anfrage" in body, "витрина: «Preis auf Anfrage»")
        run.check("0,00" not in body, "витрина: нигде нет «0,00»")

    page.goto(url + "/dashboard/")
    run.check("/dashboard/setup/" not in page.url, "после мастера кабинет открывается")
    cards = page.locator("[data-next-step]").count()
    run.check(1 <= cards <= 3, f"«Nächster Schritt»: {cards} карточки")
    run.check("Ihre Website ist zu" not in page.content(), "без старого чек-листа")
    _health(run, page, errors, "Übersicht", width)
    resp = page.goto(url + "/dashboard/verkauf-oeffnen/")
    run.check(resp.status == 200, f"«Verkauf öffnen» открывается ({resp.status})")
    _health(run, page, errors, "Verkauf öffnen", width)
    ctx.close()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--only", default="")
    args = parser.parse_args()
    personas = [p for p in PERSONAS if not args.only or p[0] == args.only]
    print(_shell(CLEAN.format(slugs=[p[0] for p in personas])).strip().splitlines()[-1:])
    from playwright.sync_api import sync_playwright  # глобальный Playwright, не из venv

    run = Run()
    with sync_playwright() as p:
        browser = p.chromium.launch(
            executable_path=CHROME,
            args=[f"--host-resolver-rules=MAP *.{BASE} 127.0.0.1, MAP {BASE} 127.0.0.1"],
        )
        for slug, btype, width in personas:
            # Лимит регистраций — 5 в час на сеть; стенд регистрирует 7 бизнесов подряд.
            _shell(CLEAN.format(slugs=[]))
            owner_path(run, browser, args.port, slug, btype, width)
        browser.close()
    print(f"\n{run.ok} ok, {len(run.fail)} fail")
    for f in run.fail:
        print("  FAIL:", f)
    sys.exit(1 if run.fail else 0)


if __name__ == "__main__":
    main()
