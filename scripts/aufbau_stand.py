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
        # R3: два блока по ½ встают в один ряд
        for kind in ("text", "image"):
            pg.select_option("select[name=type]", kind)
            pg.click("button:has-text('Hinzufügen')")
            pg.wait_for_load_state()
            pg.click("[data-schema-width] button[value=w12]")
            pg.wait_for_load_state()
        pair = pg.locator("[data-schema-row]").filter(has=pg.locator("[data-schema-block]")).last
        n = pair.locator("[data-schema-block]").count()
        check(n == 2, f"два блока по ½ — в одном ряду схемы ({n})")
        if w >= 1024:
            boxes = [x.bounding_box() for x in pair.locator("[data-schema-block]").all()]
            check(abs(boxes[0]["y"] - boxes[1]["y"]) < 4, "на компьютере они стоят рядом")
        else:
            boxes = [x.bounding_box() for x in pair.locator("[data-schema-block]").all()]
            check(boxes[1]["y"] > boxes[0]["y"] + 20, "на телефоне — друг под другом")
        # R3b: текст блока правится в панели и доезжает до витрины после «Speichern»
        pair.locator("[data-schema-block]").first.click()
        pg.wait_for_load_state()
        pg.fill("[data-schema-fields] input[name=f_title]", "Stand R3b Titel")
        pg.click("[data-schema-fields] button[value=update]")
        pg.wait_for_load_state()
        shown = pg.locator("[data-schema-fields] input[name=f_title]").input_value()
        check(shown == "Stand R3b Titel", "текст из панели остался в черновике")
        pg.screenshot(path=f"{OUT}/r3_{w}.png", full_page=True)
        pg.click("[data-schema-draft] button[value=save]")
        pg.wait_for_load_state()
        site = ctx.new_page()
        site.goto(U + "/ueber-uns/")
        check("Stand R3b Titel" in site.content(), "после «Speichern» текст на витрине")
        two = site.evaluate(
            """() => { const r = [...document.querySelectorAll('main [data-sf-section], [data-sf-section]:not([data-sf-section=header]):not([data-sf-section=footer])')].slice(-2).map(e => e.getBoundingClientRect()); return r.length === 2 ? [r[0].top, r[1].top, r[0].left, r[1].left] : null; }"""
        )
        if w >= 1024:
            check(
                two and abs(two[0] - two[1]) < 4 and two[3] > two[2], "на витрине блоки стоят рядом"
            )
        else:
            check(two and two[1] > two[0] + 20, "на витрине (телефон) — друг под другом")
        site.close()
        # убрать за собой: удалить оба блока
        for _i in range(2):
            pg.goto(U + "/dashboard/site/aufbau/?seite=text")
            pg.locator("[data-schema-row] [data-schema-block]").last.click()
            pg.wait_for_load_state()
            pg.click("[data-schema-panel] a:has-text('Entfernen')")
            pg.wait_for_load_state()
            pg.click("button[value=delete]")
            pg.wait_for_load_state()
        pg.click("[data-schema-draft] button[value=save]")
        pg.wait_for_load_state()
        pg.goto(U + "/dashboard/site/aufbau/?seite=text")
        pg.select_option("select[name=type]", "text")
        pg.click("button:has-text('Hinzufügen')")
        pg.wait_for_load_state()
        pg.click("[data-schema-draft] button[value=discard]")
        pg.wait_for_load_state()
        check(not errs, "без JS-ошибок: " + "; ".join(errs[:2]))
        ctx.close()
print(f"\n{ok}/{ok + len(fail)}")
sys.exit(1 if fail else 0)
