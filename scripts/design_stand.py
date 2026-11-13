"""FB-27 «Design»: обход экрана глазами владельца — пять типов бизнеса, 1440 и 390 px,
de и ru, БЕЗ JavaScript.

    python manage.py runserver 0.0.0.0:8000 --noreload --settings=config.settings.stand
    uv run python scripts/aufbau_owner_stand.py --setup        # один раз: пять тенантов
    uv run --with playwright==1.55.0 python scripts/design_stand.py <папка>

Три вкладки открываются и не вылезают по ширине; «Speichern» без правок оставляет на своей
вкладке; готовый дизайн применяется через панель подтверждения, галочка перестройки главной
снята, и без неё блоки главной остаются на местах. Не входит в CI (там нет браузера).
"""

import sys

from aufbau_owner_stand import BASE, CHROME, PASSWORD, TENANTS


def main():  # noqa: PLR0915 — один линейный сценарий стенда
    from playwright.sync_api import sync_playwright

    out_dir = sys.argv[1]
    ok, fail = 0, []

    def check(cond, label):
        nonlocal ok
        ok += bool(cond)
        if not cond:
            fail.append(label)
            print("  ✗ " + label)

    def home_rows(pg, url):
        pg.goto(url + "/dashboard/site/aufbau/?seite=home")
        return pg.eval_on_selector_all(
            "[data-schema-row] [data-schema-block]",
            "els => els.map(e => e.getAttribute('data-schema-block'))",
        )

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
                    for tab in ("fertig", "farben", "karten"):
                        resp = pg.goto(f"{url}/dashboard/design/?tab={tab}")
                        check(
                            resp is not None and resp.status == 200, f"{tag}: «{tab}» открывается"
                        )
                        current = pg.locator("[data-design-tab][aria-current=page]")
                        check(
                            current.count() == 1
                            and current.get_attribute("data-design-tab") == tab,
                            f"{tag}: открыта вкладка «{tab}»",
                        )
                        over = pg.evaluate(
                            "document.documentElement.scrollWidth - window.innerWidth"
                        )
                        check(over <= 0, f"{tag}: «{tab}» без горизонтального вылета ({over})")
                        if tab != "fertig":
                            pg.click("[data-design-form] button[type=submit]")
                            pg.wait_for_load_state()
                            check(
                                f"tab={tab}" in pg.url, f"{tag}: после «Speichern» — та же вкладка"
                            )
                            check(
                                pg.locator("[role=status]").count() >= 1,
                                f"{tag}: «{tab}» подтверждает сохранение",
                            )
                    # готовые дизайны: панель подтверждения и отмена
                    pg.goto(url + "/dashboard/design/")
                    cards = pg.locator("[data-design-card]")
                    check(cards.count() >= 1, f"{tag}: есть готовые дизайны ({cards.count()})")
                    check(
                        pg.locator("[data-design-confirm]").count() == 0,
                        f"{tag}: панели нет, пока дизайн не выбран",
                    )
                    cards.last.locator("a").first.click()
                    pg.wait_for_load_state()
                    panel = pg.locator("[data-design-confirm]")
                    check(panel.count() == 1, f"{tag}: «Übernehmen» открывает панель")
                    check(
                        not pg.locator("input[name=rebuild_home]").is_checked(),
                        f"{tag}: перестройка главной выключена",
                    )
                    over = pg.evaluate("document.documentElement.scrollWidth - window.innerWidth")
                    check(over <= 0, f"{tag}: панель без горизонтального вылета ({over})")
                    if width == 390 and lang == "de":
                        pg.screenshot(path=f"{out_dir}/design_{slug}_390.png", full_page=True)
                    panel.locator("a").last.click()
                    pg.wait_for_load_state()
                    check(
                        pg.locator("[data-design-confirm]").count() == 0,
                        f"{tag}: «Abbrechen» закрывает панель",
                    )
                    pg.goto(url + "/dashboard/design/?alle=1")
                    check(
                        pg.locator("#design-looks").count() == 1, f"{tag}: «Alle Designs» открыты"
                    )
                    if width == 1440 and lang == "de":
                        # применение без галочки: блоки главной остаются на местах
                        before = home_rows(pg, url)
                        pg.goto(url + "/dashboard/design/")
                        pg.locator("[data-design-card]").last.locator("a").first.click()
                        pg.wait_for_load_state()
                        pg.click("[data-design-confirm] form button")
                        pg.wait_for_load_state()
                        check(
                            pg.locator("[data-design-card] >> text=Aktiv").count() == 1,
                            f"{tag}: применённый дизайн помечен «Aktiv»",
                        )
                        pg.screenshot(path=f"{out_dir}/design_{slug}_1440.png", full_page=True)
                        check(home_rows(pg, url) == before, f"{tag}: блоки главной на местах")
                        site = pg.goto(url + "/")
                        check(
                            site is not None and site.status == 200, f"{tag}: витрина открывается"
                        )
                    ctx.close()
        browser.close()
    total = ok + len(fail)
    print(f"{ok}/{total}")
    if fail:
        sys.exit(1)


if __name__ == "__main__":
    main()
