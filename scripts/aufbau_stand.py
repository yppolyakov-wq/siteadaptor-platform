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
        # R3b-2: блок «Liste» — что показать, какие и как; после «Speichern» на витрине
        pg.select_option("select[name=type]", "list")
        pg.click("button:has-text('Hinzufügen')")
        pg.wait_for_load_state()
        check(pg.locator("[data-schema-list] fieldset").count() == 3, "у списка три группы полей")
        pg.select_option("[data-schema-list] select[name=f_source]", "products")
        pg.click("[data-schema-list] button[value=update]")
        pg.wait_for_load_state()
        check(
            pg.locator("[data-schema-list] select[name=f_category]").count() == 1
            and pg.locator("[data-schema-list] select[name=f_type]").count() == 0,
            "после смены источника — поля товаров, без полей акций",
        )
        pg.fill("[data-schema-list] input[name=f_title]", "Stand Liste")
        pg.fill("[data-schema-list] input[name=f_limit]", "3")
        pg.select_option("[data-schema-list] select[name=f_cols]", "3")
        pg.click("[data-schema-list] button[value=update]")
        pg.wait_for_load_state()
        note = pg.locator("[data-schema-result]").inner_text()
        empty = "erscheint nicht" in note
        check(bool(note.strip()), f"панель говорит, что покажет блок: {note.strip()[:60]}")
        over = pg.evaluate("document.documentElement.scrollWidth - window.innerWidth")
        check(over <= 0, f"панель списка без горизонтального вылета ({over})")
        pg.screenshot(path=f"{OUT}/r3list_{w}.png", full_page=True)
        # R5: ручной состав — две позиции, вторая поднята наверх
        offers = pg.locator("[data-schema-pick-offers] button")
        check(
            offers.count() >= 2, f"панель предлагает позиции для ручного выбора ({offers.count()})"
        )
        for _i in range(2):
            pg.locator("[data-schema-pick-offers] button").first.click()
            pg.wait_for_load_state()
        names = pg.locator("[data-schema-pick-item] span.flex-1").all_inner_texts()
        check(len(names) == 2, f"выбрано две позиции ({len(names)})")
        pg.locator("[data-schema-pick-item]").nth(1).locator("button[value^='up:']").click()
        pg.wait_for_load_state()
        after = pg.locator("[data-schema-pick-item] span.flex-1").all_inner_texts()
        want = [n.split(". ", 1)[1].strip() for n in reversed(names)]
        got = [n.split(". ", 1)[1].strip() for n in after]
        check(got == want, f"порядок поменялся: {got}")
        check(
            pg.locator("[data-schema-list] select[name=f_sort]").count() == 0,
            "при ручном составе поля правила скрыты",
        )
        small = pg.eval_on_selector_all(
            "[data-schema-pick] button",
            "els => els.filter(e => { const r = e.getBoundingClientRect(); return r.width < 24 || r.height < 24; }).length",
        )
        check(small == 0, f"кнопки ручного выбора не меньше 24 px ({small})")
        pg.screenshot(path=f"{OUT}/r5_{w}.png", full_page=True)
        pick_order = got
        pg.click("[data-schema-draft] button[value=save]")
        pg.wait_for_load_state()
        site = ctx.new_page()
        site.goto(U + "/ueber-uns/")
        if empty:
            check("Stand Liste" not in site.content(), "пустой список на витрине не выводится")
        else:
            check("Stand Liste" in site.content(), "список с заголовком — на витрине")
            html = site.content()
            pos = [html.find(n) for n in pick_order]
            check(
                all(p > 0 for p in pos) and pos == sorted(pos),
                f"на витрине выбранные позиции в порядке владельца ({pos})",
            )
        site.screenshot(path=f"{OUT}/r3list_site_{w}.png", full_page=True)
        site.close()
        pg.goto(U + "/dashboard/site/aufbau/?seite=text")
        pg.locator("[data-schema-row] [data-schema-block]").last.click()
        pg.wait_for_load_state()
        pg.click("[data-schema-panel] a:has-text('Entfernen')")
        pg.wait_for_load_state()
        pg.click("button[value=delete]")
        pg.wait_for_load_state()
        pg.click("[data-schema-draft] button[value=save]")
        pg.wait_for_load_state()
        # R4: настройки типа страницы — в панели «★ Hauptliste» и на строке настроек
        pg.goto(U + "/dashboard/site/aufbau/?seite=catalog")
        pg.locator("[data-schema-block]").filter(has_text="Hauptliste").first.click()
        pg.wait_for_load_state()
        n = pg.locator("[data-schema-setting]").count()
        check(n >= 4, f"у каталога настройки типа в панели основного списка ({n})")
        over = pg.evaluate("document.documentElement.scrollWidth - window.innerWidth")
        check(over <= 0, f"панель настроек без горизонтального вылета ({over})")
        pg.screenshot(path=f"{OUT}/r4_{w}.png", full_page=True)
        pg.click("[data-schema-setting-box=catalog_filters] summary")
        form = pg.locator("[data-schema-setting=catalog_filters]")
        form.locator("input[value='0']").check()
        form.locator("button[type=submit]").click()
        pg.wait_for_load_state()
        check(pg.locator("[data-schema-draft]").count() == 1, "настройка ушла в черновик")
        check(
            pg.locator("[data-schema-setting-box=catalog_filters][open]").count() == 1,
            "изменённая настройка осталась раскрытой",
        )
        pg.screenshot(path=f"{OUT}/r4_{w}.png", full_page=True)
        pg.click("[data-schema-draft] button[value=discard]")
        pg.wait_for_load_state()
        pg.goto(U + "/dashboard/site/aufbau/?seite=text")
        pg.click("[data-schema-block=__page]")
        pg.wait_for_load_state()
        check(
            pg.locator("[data-schema-setting=text_width]").count() == 1,
            "у текстовой страницы — строка «Einstellungen der Seite»",
        )
        check(not errs, "без JS-ошибок: " + "; ".join(errs[:2]))
        ctx.close()
print(f"\n{ok}/{ok + len(fail)}")
sys.exit(1 if fail else 0)
