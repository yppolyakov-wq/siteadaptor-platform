"""FB-27 R1: браузерный стенд экрана «Seitenaufbau» (1440 и 390 px).

    python manage.py runserver 0.0.0.0:8000 --settings=config.settings.stand
    uv run python scripts/text_pages_stand.py --setup     # один раз (тенант ptx)
    uv run --with playwright==1.55.0 python scripts/aufbau_stand.py <папка для скриншотов>

Не входит в CI (там нет браузера).
"""

import sys

from playwright.sync_api import sync_playwright

OUT = sys.argv[1]
ok = 0
fail = []


def check(c, label):
    global ok
    ok += bool(c)
    print(("  ✓ " if c else "  ✗ ") + label)
    if not c:
        fail.append(label)


U = "http://ptx.siteadaptor.de:8000"
with sync_playwright() as p:
    b = p.chromium.launch(
        executable_path="/opt/pw-browsers/chromium",
        args=["--host-resolver-rules=MAP *.siteadaptor.de 127.0.0.1"],
    )
    for w, h in ((1440, 900), (390, 844)):
        ctx = b.new_context(viewport={"width": w, "height": h}, locale="de-DE")
        pg = ctx.new_page()
        errs = []
        pg.on("pageerror", lambda e, errs=errs: errs.append(str(e)))
        pg.goto(U + "/accounts/login/")
        pg.fill("input[name=login]", "owner@ptx.test")
        pg.fill("input[name=password]", "Stand-Passwort-123")
        pg.click("button[type=submit]")
        pg.wait_for_load_state()
        pg.goto(U + "/dashboard/site/aufbau/")
        pg.wait_for_load_state()
        print(f"--- {w}px")
        check(pg.locator("select#schema-seite").count() == 1, "select типа страницы")
        check(pg.locator("[data-schema-type] button").is_visible(), "кнопка «Öffnen» видна")
        opts = pg.locator("select#schema-seite option").all_inner_texts()
        print("    типы:", " | ".join(o.strip() for o in opts))
        pg.select_option("select#schema-seite", "text")
        pg.click("[data-schema-type] button")
        pg.wait_for_url(lambda u: "seite=text" in u, timeout=5000)
        check("seite=text" in pg.url, "смена типа кнопкой «Öffnen»")
        # добавить два блока и проверить панель
        pg.select_option("select[name=type]", "text")
        pg.click("button:has-text('Hinzufügen')")
        pg.wait_for_load_state()
        focused = pg.evaluate("document.activeElement && document.activeElement.id")
        check(focused == "schema-panel", "после добавления фокус в панели нового блока")
        check(pg.locator("[data-schema-draft]").count() == 1, "после правки — полоса черновика")
        with pg.context.expect_page() as pop:
            pg.click("a:has-text('Vorschau')")
        pv = pop.value
        pv.wait_for_load_state()
        shown = "aufbau=text" in pv.url and pv.locator("[data-sf-section]").count() >= 1
        check(shown, "превью показывает черновик")
        pv.close()
        pg.click("[data-schema-draft] button[value=save]")
        pg.wait_for_load_state()
        check(pg.locator("[data-schema-draft]").count() == 0, "«Speichern» — черновика нет")
        pg.locator("[data-schema-row] [data-schema-block]").last.click()
        pg.wait_for_load_state()
        check(
            pg.locator("[data-schema-panel] button[value=toggle]").count() == 1,
            "панель блока с «Ausblenden»",
        )
        small = pg.evaluate(
            """() => [...document.querySelectorAll('main a, main button, main select, main summary')].filter(e=>{const r=e.getBoundingClientRect(); return r.width && r.height && (r.height<24||r.width<24)}).map(e=>e.innerText.trim().slice(0,30))"""
        )
        check(not small, f"нет целей меньше 24 px: {small[:5]}")
        over = pg.evaluate("document.documentElement.scrollWidth - innerWidth")
        check(over <= 0, f"нет горизонтального вылета ({over})")
        pg.screenshot(path=f"{OUT}/r1_{w}.png", full_page=True)
        pg.click("[data-schema-panel] button[value=toggle]")
        pg.wait_for_load_state()
        check(pg.locator("[data-schema-hidden]").count() == 1, "скрытый блок — в «Ausgeblendet»")
        pg.click("[data-schema-panel] a:has-text('Entfernen')")
        pg.wait_for_load_state()
        check(pg.locator("[data-schema-confirm]").count() == 1, "удаление — отдельным шагом")
        pg.click("button[value=delete]")
        pg.wait_for_load_state()
        check(pg.locator("[data-schema-hidden]").count() == 0, "блок удалён")
        pg.click("[data-schema-draft] button[value=save]")
        pg.wait_for_load_state()
        check(pg.locator("[data-schema-draft]").count() == 0, "удаление сохранено")
        check(not errs, "без JS-ошибок: " + "; ".join(errs[:2]))
        ctx.close()
print(f"\n{ok}/{ok + len(fail)}")
sys.exit(1 if fail else 0)
