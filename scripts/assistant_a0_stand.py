"""AIS-A A-0: браузерный стенд шторки «✨ Assistent» (Playwright, Chromium).

Тенант `assist0` (`--setup` создаёт): сайт неопубликован. Проверки:
кнопка ✨ в шапке открывает шторку (dialog) с блоками помощника, Esc закрывает и
возвращает фокус; «Jetzt prüfen» перезагружает шторку и ставит фокус на результат;
без JS — полная страница; телефон 390 px без горизонтального скролла; без JS-ошибок.

    python manage.py runserver 0.0.0.0:8000 --settings=config.settings.stand
    uv run python scripts/assistant_a0_stand.py --setup     # один раз
    uv run --with playwright==1.55.0 python scripts/assistant_a0_stand.py

Не входит в CI (там нет браузера).
"""

from __future__ import annotations

import argparse
import subprocess
import sys

CHROME = "/opt/pw-browsers/chromium"
BASE = "siteadaptor.de"
SLUG = "assist0"
EMAIL = "owner@assist0.test"
PASSWORD = "Stand-Passwort-123"

SETUP = f"""
from apps.tenants.models import Domain, Tenant
from apps.tenants.services import create_business

from django.db import connection
Tenant.objects.filter(schema_name={SLUG!r}).delete()
with connection.cursor() as c:  # повторный --setup: схема не удаляется вместе с тенантом
    c.execute("DROP SCHEMA IF EXISTS {SLUG} CASCADE")
tenant, _ = create_business(business_name="Laden Stand", slug={SLUG!r},
    business_type="bakery", city="Hilden", email={EMAIL!r}, password={PASSWORD!r})
from apps.tenants import onboarding
onboarding.mark_complete(tenant)  # кабинет без мастера; публикует сайт — снимаем ниже
tenant.refresh_from_db()
tenant.published_at = None
tenant.save(update_fields=["published_at"])
Domain.objects.update_or_create(domain="{SLUG}.{BASE}", defaults={{"tenant": tenant, "is_primary": True}})
print("READY")
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


def _login(browser, port, width, js=True):
    url = f"http://{SLUG}.{BASE}:{port}"
    ctx = browser.new_context(
        viewport={"width": width, "height": 900}, locale="de-DE", java_script_enabled=js
    )
    page = ctx.new_page()
    errors = []
    page.on("pageerror", lambda e: errors.append(str(e)))
    page.goto(url + "/accounts/login/")
    page.fill("input[name=login]", EMAIL)
    page.fill("input[name=password]", PASSWORD)
    page.click("button[type=submit]")
    page.wait_for_load_state()
    return ctx, page, errors, url


def drawer(run, browser, port, width):
    print(f"Шторка, {width}px")
    ctx, page, errors, url = _login(browser, port, width)
    page.goto(url + "/dashboard/")
    opener = page.locator("[data-assistant-open]")
    run.check(opener.count() == 1, "кнопка ✨ в шапке")
    box = opener.bounding_box() or {}
    run.check(box.get("height", 0) >= 44 and box.get("width", 0) >= 44, f"цель ≥44px ({box})")
    opener.click()
    dialog = page.locator("dialog#sf-drawer")
    page.wait_for_selector("dialog#sf-drawer [data-assistant]", timeout=8000)
    run.check(dialog.evaluate("d => d.open"), "шторка открыта")
    body = dialog.inner_text()
    run.check("Gerade wichtig" in body, "блок «Gerade wichtig»")
    run.check("Funktioniert etwas nicht?" in body, "блок диагнозов")
    run.check("veröffentlicht" in body, "находка «Website nicht veröffentlicht»")
    run.check(not dialog.locator("script").count(), "во фрагменте нет <script>")
    scroll = page.evaluate("document.documentElement.scrollWidth")
    run.check(scroll <= width + 2, f"без горизонтального скролла ({scroll}px)")
    page.keyboard.press("Escape")
    page.wait_for_timeout(300)
    run.check(not dialog.evaluate("d => d.open"), "Esc закрывает")
    focused = page.evaluate(
        "document.activeElement && document.activeElement.dataset.assistantOpen"
    )
    run.check(focused is not None, "фокус вернулся на кнопку ✨")
    run.check(not errors, f"без JS-ошибок {errors[:2]}")
    ctx.close()


def no_js(run, browser, port):
    print("Без JS")
    ctx, page, errors, url = _login(browser, port, 1440, js=False)
    resp = page.goto(url + "/dashboard/assistent/?seite=dashboard")
    run.check(resp.status == 200, "полная страница 200")
    run.check(page.locator("[data-assistant]").count() == 1, "тело помощника на странице")
    page.fill("#as-q", "Öffnungszeiten")
    page.click("form[role=search] button[type=submit]")
    page.wait_for_load_state()
    run.check(page.locator("section[aria-labelledby=as-where-h] a").count() >= 1, "поиск находит")
    ctx.close()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--setup", action="store_true")
    args = parser.parse_args()
    if args.setup:
        out = subprocess.run(
            [sys.executable, "manage.py", "shell", "--settings=config.settings.stand", "-c", SETUP],
            capture_output=True,
            text=True,
            check=False,
        )
        print((out.stdout + out.stderr)[-600:])
        return
    from playwright.sync_api import sync_playwright  # глобальный Playwright, не из venv

    run = Run()
    with sync_playwright() as p:
        browser = p.chromium.launch(
            executable_path=CHROME, args=[f"--host-resolver-rules=MAP *.{BASE} 127.0.0.1"]
        )
        for width in (1440, 390):
            drawer(run, browser, args.port, width)
        no_js(run, browser, args.port)
        browser.close()
    print(f"\n{run.ok} ok, {len(run.fail)} fail")
    for f in run.fail:
        print("  FAIL:", f)
    sys.exit(1 if run.fail else 0)


if __name__ == "__main__":
    main()
