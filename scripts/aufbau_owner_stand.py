"""FB-27 R9: обход «Seitenaufbau» глазами владельца — пять типов бизнеса, 1440 и 390 px,
de и ru, БЕЗ JavaScript.

    python manage.py runserver 0.0.0.0:8000 --settings=config.settings.stand
    uv run python scripts/aufbau_owner_stand.py --setup        # один раз: пять тенантов
    uv run --with playwright==1.55.0 python scripts/aufbau_owner_stand.py <папка>

Для каждого бизнеса открывается каждая страница из выбора «Seitentyp»: экран отвечает,
не вылезает по ширине, у каждой строки схемы есть панель. На одной странице проходит
сценарий владельца без скриптов: добавить блок → «Speichern» → блок на сайте → убрать.
Не входит в CI (там нет браузера).
"""

import subprocess
import sys

CHROME = "/opt/pw-browsers/chromium"
BASE = "siteadaptor.de"
PASSWORD = "Stand-Passwort-123"
TENANTS = {
    "r9shop": "online_shop",
    "r9baeck": "bakery",
    "r9hotel": "hotel",
    "r9friseur": "friseur",
    "r9handw": "handwerker",
}

SETUP = f"""
from django.db import connection
from django.utils import timezone
from apps.tenants import onboarding
from apps.tenants.models import Domain, Tenant
from apps.tenants.services import create_business
for slug, btype in {TENANTS!r}.items():
    for old in Tenant.objects.filter(schema_name=slug):
        old.delete(force_drop=True)
    with connection.cursor() as c:
        c.execute(f"DROP SCHEMA IF EXISTS {{slug}} CASCADE")
    tenant, _ = create_business(business_name=f"Stand {{btype}}", slug=slug, business_type=btype,
        city="Haan", email=f"owner@{{slug}}.test", password={PASSWORD!r})
    tenant.published_at = timezone.now()
    tenant.enabled_locales = ["de", "ru"]
    tenant.save(update_fields=["published_at", "enabled_locales"])
    onboarding.mark_complete(tenant)
    Domain.objects.update_or_create(
        domain=f"{{slug}}.{BASE}", defaults={{"tenant": tenant, "is_primary": True}})
    print("READY", slug)
"""


def close_sheet(pg):
    """На телефоне панель блока — лист снизу; до кнопок шапки и схемы — «Fertig»."""
    done = pg.locator("[data-schema-done]")
    if done.count() and done.first.is_visible():
        done.first.click()
        pg.wait_for_load_state()


def main():  # noqa: PLR0915 — один линейный сценарий стенда
    if "--setup" in sys.argv:
        out = subprocess.run(
            [sys.executable, "manage.py", "shell", "--settings=config.settings.stand", "-c", SETUP],
            capture_output=True,
            text=True,
            check=False,
        )
        print((out.stdout + out.stderr)[-600:])
        return
    from playwright.sync_api import sync_playwright

    out_dir = sys.argv[1]
    ok, fail = 0, []

    def check(cond, label):
        nonlocal ok
        ok += bool(cond)
        if not cond:
            fail.append(label)
            print("  ✗ " + label)

    with sync_playwright() as p:
        browser = p.chromium.launch(
            executable_path=CHROME, args=[f"--host-resolver-rules=MAP *.{BASE} 127.0.0.1"]
        )
        for slug, btype in TENANTS.items():
            url = f"http://{slug}.{BASE}:8000"
            for width, height in ((1440, 900), (390, 844)):
                for lang in ("de", "ru"):
                    ctx = browser.new_context(
                        viewport={"width": width, "height": height},
                        locale="de-DE",
                        java_script_enabled=False,
                    )
                    pg = ctx.new_page()
                    pg.goto(url + "/accounts/login/")
                    pg.fill("input[name=login]", f"owner@{slug}.test")
                    pg.fill("input[name=password]", PASSWORD)
                    pg.click("button[type=submit]")
                    pg.wait_for_load_state()
                    ctx.add_cookies([{"name": "django_language", "value": lang, "url": url}])
                    tag = f"{btype} {width}px {lang}"
                    resp = pg.goto(url + "/dashboard/site/aufbau/")
                    check(resp is not None and resp.status == 200, f"{tag}: экран открывается")
                    codes = pg.eval_on_selector_all(
                        "select#schema-seite option", "els => els.map(e => e.value)"
                    )
                    check(len(codes) >= 3, f"{tag}: в выборе есть страницы ({len(codes)})")
                    for code in codes:
                        resp = pg.goto(f"{url}/dashboard/site/aufbau/?seite={code}")
                        good = resp is not None and resp.status == 200
                        check(good, f"{tag}: страница «{code}» открывается")
                        if not good:
                            continue
                        over = pg.evaluate(
                            "document.documentElement.scrollWidth - window.innerWidth"
                        )
                        check(over <= 0, f"{tag}: «{code}» без вылета по ширине ({over})")
                        refs = pg.eval_on_selector_all(
                            "[data-schema-block]", "els => els.map(e => e.getAttribute('href'))"
                        )
                        if refs:  # панель первой строки схемы открывается и без скриптов
                            resp = pg.goto(f"{url}/dashboard/site/aufbau/{refs[0]}")
                            panel = pg.locator("[data-schema-panel]").count()
                            check(
                                resp is not None and resp.status == 200 and panel == 1,
                                f"{tag}: «{code}» — панель строки открывается",
                            )
                            over = pg.evaluate(
                                "document.documentElement.scrollWidth - window.innerWidth"
                            )
                            check(over <= 0, f"{tag}: «{code}» панель без вылета ({over})")
                    if lang == "de":
                        # сценарий владельца без скриптов: блок → сохранить → сайт → убрать
                        pg.goto(url + "/dashboard/site/aufbau/?seite=text")
                        close_sheet(pg)
                        pg.click("[data-schema-add] summary")
                        pg.select_option("select[name=type]", "text")
                        pg.click("form:has(select[name=type]) button")
                        pg.wait_for_load_state()
                        title = f"R9 {slug} {width}"
                        pg.fill("[data-schema-fields] input[name=f_title]", title)
                        pg.click("[data-schema-fields] button[value=update]")
                        pg.wait_for_load_state()
                        close_sheet(pg)
                        pg.click("[data-schema-draft] button[value=save]")
                        pg.wait_for_load_state()
                        site = ctx.new_page()
                        site.goto(url + "/ueber-uns/")
                        check(title in site.content(), f"{tag}: блок без скриптов дошёл до сайта")
                        over = site.evaluate(
                            "document.documentElement.scrollWidth - window.innerWidth"
                        )
                        check(over <= 0, f"{tag}: витрина без вылета ({over})")
                        site.close()
                        pg.goto(url + "/dashboard/site/aufbau/?seite=text")
                        close_sheet(pg)
                        pg.locator("[data-schema-block]").filter(has_text=title).first.click()
                        pg.wait_for_load_state()
                        pg.click("[data-schema-more] summary")
                        pg.click("[data-schema-panel] a:has-text('Entfernen')")
                        pg.wait_for_load_state()
                        pg.click("button[value=delete]")
                        pg.wait_for_load_state()
                        close_sheet(pg)
                        pg.click("[data-schema-draft] button[value=save]")
                        pg.wait_for_load_state()
                        check(
                            pg.locator("[data-schema-block]").filter(has_text=title).count() == 0,
                            f"{tag}: блок убран",
                        )
                        if width == 390:
                            pg.screenshot(path=f"{out_dir}/r9_{slug}_{width}.png", full_page=True)
                    ctx.close()
    print(f"\n{ok}/{ok + len(fail)}")
    sys.exit(1 if fail else 0)


if __name__ == "__main__":
    main()
