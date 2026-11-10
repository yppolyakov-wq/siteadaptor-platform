"""M21.6: браузерный стенд «Website › Seiten» (Playwright, Chromium).

Кабинет: создать страницу визуальным редактором → список → витрина во всю ширину
(1440 и 390 px) → «Eigene Seite» в редакторе меню → удалить. Плюс текст «Versand»
над способами доставки на /versand/.

    python manage.py runserver 0.0.0.0:8000 --settings=config.settings.stand
    uv run python scripts/content_pages_stand.py --setup     # один раз
    uv run python scripts/content_pages_stand.py

Не входит в CI (там нет браузера).
"""

from __future__ import annotations

import argparse
import subprocess
import sys

CHROME = "/opt/pw-browsers/chromium"
BASE = "siteadaptor.de"
SLUG = "pcms"
PASSWORD = "Stand-Passwort-123"

SETUP = f"""
from django.utils import timezone
from apps.tenants.models import Domain, Tenant
from apps.tenants.services import create_business
from apps.tenants import onboarding
Tenant.objects.filter(schema_name={SLUG!r}).delete()
tenant, _ = create_business(business_name="Stand Teeladen", slug={SLUG!r},
    business_type="online_shop", city="Haan", email="owner@{SLUG}.test", password={PASSWORD!r})
tenant.published_at = timezone.now()
cfg = dict(tenant.site_config or {{}})
cfg["site_defaults"] = {{**(cfg.get("site_defaults") or {{}}), "text_width": "full"}}
tenant.site_config = cfg
tenant.save(update_fields=["published_at", "site_config"])
onboarding.mark_complete(tenant)
Domain.objects.update_or_create(domain="{SLUG}.{BASE}", defaults={{"tenant": tenant, "is_primary": True}})
from django_tenants.utils import schema_context
with schema_context({SLUG!r}):
    from apps.core.models import ContentPage
    ContentPage.objects.all().delete()
    ContentPage.objects.create(slug="versand", title="Versand", body="<p>Wir versenden mit DHL.</p>")
print("READY")
"""


class Run:
    def __init__(self):
        self.ok, self.fail = 0, []

    def check(self, cond, label):
        (self.fail.append(label) if not cond else None)
        self.ok += bool(cond)
        print(("  ✓ " if cond else "  ✗ ") + label)


def _shell(code):
    out = subprocess.run(
        [sys.executable, "manage.py", "shell", "--settings=config.settings.stand", "-c", code],
        capture_output=True,
        text=True,
        check=False,
    )
    return out.stdout + out.stderr[-800:]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--setup", action="store_true")
    ap.add_argument("--port", type=int, default=8000)
    args = ap.parse_args()
    if args.setup:
        print(_shell(SETUP)[-300:])
        return
    from playwright.sync_api import sync_playwright

    run = Run()
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

        print("Kabinett")
        page.goto(url + "/dashboard/site/seiten/")
        run.check(page.locator("[data-page-row=versand]").count() == 1, "список: страница Versand")
        run.check("„Versand“" in page.content(), "подпись «на странице Versand»")
        page.click("[data-page-new]")
        page.fill("input[name=title]", "Zahlungsarten")
        bar = page.locator(".rte-bar button")
        run.check(bar.count() >= 9, f"редактор: {bar.count()} кнопок (H2/H3/¶/…/Bild)")
        area = page.locator(".rte-area")
        area.click()
        page.keyboard.type("Bezahlen")
        page.click(".rte-bar button[aria-label='Überschrift']")
        page.keyboard.press("End")
        page.keyboard.press("Enter")
        page.keyboard.type("PayPal, Vorkasse oder bar bei Abholung.")
        page.click("button.ui-btn-primary")
        page.wait_for_load_state()
        run.check("Seite angelegt" in page.content(), "сохранено")
        run.check('value="zahlungsarten"' in page.content(), "адрес из заголовка")
        run.check(not errors, f"кабинет без JS-ошибок {errors[:2]}")

        print("Website")
        for width in (1440, 390):
            page.set_viewport_size({"width": width, "height": 900})
            page.goto(url + "/seite/zahlungsarten/")
            html = page.content()
            run.check("<h2>Bezahlen</h2>" in html, f"{width}: заголовок H2 на витрине")
            art = page.locator("[data-content-page]").bounding_box()
            main = page.locator("main").bounding_box() or {"width": width}
            run.check(
                art and art["width"] >= main["width"] - 80,
                f"{width}: во всю ширину ({art and int(art['width'])}/{int(main['width'])})",
            )
            scroll = page.evaluate("document.documentElement.scrollWidth")
            run.check(scroll <= width + 2, f"{width}: без горизонтального скролла ({scroll})")
        page.set_viewport_size({"width": 1440, "height": 900})
        page.goto(url + "/versand/")
        run.check("Wir versenden mit DHL." in page.content(), "/versand/: свой текст над способами")
        page.goto(url + "/seite/versand/")
        run.check(
            page.url.rstrip("/").endswith("/versand"), f"/seite/versand/ → /versand/ ({page.url})"
        )

        print("Menü")
        page.goto(url + "/dashboard/site/menu/")
        run.check("Eigene Seite" in page.content(), "редактор меню: «Eigene Seite»")

        print("Löschen")
        page.goto(url + "/dashboard/site/seiten/")
        btn = page.locator("[data-page-row=zahlungsarten] button.ui-btn-danger")
        btn.click()
        btn.click()  # data-confirm-tap: второе касание подтверждает
        page.wait_for_load_state()
        run.check(page.locator("[data-page-row=zahlungsarten]").count() == 0, "удалено")
        resp = page.goto(url + "/seite/zahlungsarten/")
        run.check(resp.status == 404, f"после удаления 404 ({resp.status})")
        run.check(not errors, f"без JS-ошибок {errors[:2]}")
        browser.close()
    print(f"\n{run.ok} ✓, {len(run.fail)} ✗")
    sys.exit(1 if run.fail else 0)


if __name__ == "__main__":
    main()
