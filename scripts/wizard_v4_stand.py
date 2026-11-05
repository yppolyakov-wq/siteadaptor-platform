"""AIS-W W4-1: браузерный стенд мастера v4 (Playwright, Chromium) — путь владельца.

Тенант `wizardv4` (создаётся `--setup`): сайт неопубликован, мастер v4. Путь:
вход → кабинет уводит в мастер → «Firma» (часы сеткой) → «Angebot» → «Rechtliches &
Veröffentlichen»: список недостающего → поля Impressum → «Website veröffentlichen» →
«Fertig». Гостем: до публикации витрина 503, после — 200. На каждой странице: без
JS-ошибок и горизонтального скролла, телефон 390 px и десктоп 1440 px.

    python manage.py runserver 0.0.0.0:8000 --settings=config.settings.stand
    uv run python scripts/wizard_v4_stand.py --setup     # один раз: тенант и владелец
    uv run python scripts/wizard_v4_stand.py

Хост `wizardv4.siteadaptor.de` направляется на локальный сервер правилом резолвера
Chromium. Не входит в CI (там нет браузера).
"""

from __future__ import annotations

import argparse
import subprocess
import sys

from playwright.sync_api import sync_playwright

CHROME = "/opt/pw-browsers/chromium-1194/chrome-linux/chrome"
BASE = "siteadaptor.de"
SLUG = "wizardv4"
EMAIL = "owner@wizardv4.test"
PASSWORD = "Stand-Passwort-123"

SETUP = f"""
from django.contrib.auth import get_user_model
from django_tenants.utils import schema_context
from apps.tenants.models import Domain, Tenant
from apps.tenants.services import create_business
from apps.core.models import Membership

Tenant.objects.filter(schema_name={SLUG!r}).delete()
tenant, _ = create_business(business_name="Bäckerei Stand", slug={SLUG!r},
    business_type="bakery", city="Hilden", email={EMAIL!r}, password={PASSWORD!r})
tenant.published_at = None
tenant.site_config = {{**(tenant.site_config or {{}}), "onboarding": {{"v": 2, "flow": "v4"}}}}
tenant.address = ""
tenant.save(update_fields=["published_at", "site_config", "address"])
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


def _health(run, page, errors, label, width):
    scroll = page.evaluate("document.documentElement.scrollWidth")
    run.check(scroll <= width + 2, f"{label}: без горизонтального скролла ({scroll}px)")
    run.check(not errors, f"{label}: без JS-ошибок {errors[:2]}")
    errors.clear()


def owner_path(run, browser, port, width):
    print(f"Владелец, {width}px")
    url = f"http://{SLUG}.{BASE}:{port}"
    ctx = browser.new_context(viewport={"width": width, "height": 900}, locale="de-DE")
    page = ctx.new_page()
    errors = []
    page.on("pageerror", lambda e: errors.append(str(e)))

    guest = browser.new_context(locale="de-DE").new_page()
    run.check(guest.goto(url + "/").status == 503, "гость до публикации: 503")

    page.goto(url + "/accounts/login/")
    page.fill("input[name=login]", EMAIL)
    page.fill("input[name=password]", PASSWORD)
    page.click("button[type=submit]")
    page.goto(url + "/dashboard/")
    run.check("/dashboard/setup/" in page.url, "кабинет уводит в мастер")
    run.check(page.locator("[data-setup-hours]").count() == 1, "Firma: часы сеткой")
    _health(run, page, errors, "Firma", width)
    page.fill("#id_address", "Hauptstraße 1, 40721 Hilden")
    page.fill("#id_contact_phone", "02103 12345")
    page.fill("input[name=oh_0_open]", "07:00")
    page.fill("input[name=oh_0_close]", "18:00")
    page.click("button.ui-btn-primary")
    page.wait_for_load_state()

    # Angebot — дальше
    page.click("button.ui-btn-primary")
    page.wait_for_load_state()
    run.check(page.locator("[data-recht-form]").count() == 1, "шаг «Rechtliches & Veröffentlichen»")
    _health(run, page, errors, "Recht", width)

    page.click("[data-recht-publish]")
    page.wait_for_load_state()
    run.check(
        page.locator("[data-recht-blockers]").count() == 1, "без Impressum — список недостающего"
    )
    run.check(guest.goto(url + "/").status == 503, "гость после отказа: всё ещё 503")

    page.fill("#id_recht_legal_representative", "Anna Muster")
    page.select_option("#id_recht_legal_form", "ek")
    page.fill("#id_recht_register_court", "Amtsgericht Düsseldorf")
    page.fill("#id_recht_register_number", "HRA 12345")
    page.fill("#id_recht_tax_number", "135/5000/1234")
    page.click("[data-recht-publish]")
    page.wait_for_load_state()
    run.check(
        "Fertig" in page.content() or "online" in page.content(), "после публикации — «Fertig»"
    )
    _health(run, page, errors, "Fertig", width)
    run.check(guest.goto(url + "/").status == 200, "гость после публикации: 200")
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
        print(out.stdout[-400:], out.stderr[-1500:])
        return
    run = Run()
    with sync_playwright() as p:
        browser = p.chromium.launch(
            executable_path=CHROME, args=[f"--host-resolver-rules=MAP *.{BASE} 127.0.0.1"]
        )
        owner_path(run, browser, args.port, 390)
        browser.close()
    print(f"\n{run.ok} ok, {len(run.fail)} fail")
    for f in run.fail:
        print("  FAIL:", f)
    sys.exit(1 if run.fail else 0)


if __name__ == "__main__":
    main()
