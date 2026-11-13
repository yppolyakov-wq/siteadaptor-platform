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


def close_sheet(pg):
    """На телефоне панель блока — лист снизу; до кнопок шапки и схемы — «Fertig»."""
    done = pg.locator("[data-schema-done]")
    if done.count() and done.first.is_visible():
        done.first.click()
        pg.wait_for_load_state()


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
        check(
            not pg.locator("[data-schema-type] button").is_visible(),
            "со скриптами страница открывается по выбору — кнопки «Öffnen» нет",
        )
        opts = pg.locator("select#schema-seite option").all_inner_texts()
        print("    типы:", " | ".join(o.strip() for o in opts))
        pg.select_option("select#schema-seite", "text")
        pg.wait_for_url(lambda u: "seite=text" in u, timeout=5000)
        check("seite=text" in pg.url, "смена страницы по выбору в списке")
        # добавить два блока и проверить панель
        close_sheet(pg)
        pg.click("[data-schema-add] summary")
        pg.select_option("select[name=type]", "text")
        pg.click("form:has(select[name=type]) button")
        pg.wait_for_load_state()
        focused = pg.evaluate("document.activeElement && document.activeElement.id")
        check(focused == "schema-panel", "после добавления фокус в панели нового блока")
        check(pg.locator("[data-schema-draft]").count() == 1, "после правки — полоса черновика")
        close_sheet(pg)
        with pg.context.expect_page() as pop:
            pg.click("a:has-text('Vorschau')")
        pv = pop.value
        pv.wait_for_load_state()
        shown = "aufbau=text" in pv.url and pv.locator("[data-sf-section]").count() >= 1
        check(shown, "превью показывает черновик")
        pv.close()
        close_sheet(pg)
        pg.click("[data-schema-draft] button[value=save]")
        pg.wait_for_load_state()
        check(pg.locator("[data-schema-draft]").count() == 0, "«Speichern» — черновика нет")
        close_sheet(pg)
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
        pg.click("[data-schema-more] summary")
        pg.click("[data-schema-panel] button[value=toggle]")
        pg.wait_for_load_state()
        check(pg.locator("[data-schema-hidden]").count() == 1, "скрытый блок — в «Ausgeblendet»")
        pg.click("[data-schema-more] summary")
        pg.click("[data-schema-panel] a:has-text('Entfernen')")
        pg.wait_for_load_state()
        check(pg.locator("[data-schema-confirm]").count() == 1, "удаление — отдельным шагом")
        pg.click("button[value=delete]")
        pg.wait_for_load_state()
        check(pg.locator("[data-schema-hidden]").count() == 0, "блок удалён")
        close_sheet(pg)
        pg.click("[data-schema-draft] button[value=save]")
        pg.wait_for_load_state()
        check(pg.locator("[data-schema-draft]").count() == 0, "удаление сохранено")
        # R3: два блока по ½ встают в один ряд
        for kind in ("text", "image"):
            close_sheet(pg)
            pg.click("[data-schema-add] summary")
            pg.select_option("select[name=type]", kind)
            pg.click("form:has(select[name=type]) button")
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
        close_sheet(pg)
        pair.locator("[data-schema-block]").first.click()
        pg.wait_for_load_state()
        pg.fill("[data-schema-fields] input[name=f_title]", "Stand R3b Titel")
        pg.click("[data-schema-fields] button[value=update]")
        pg.wait_for_load_state()
        shown = pg.locator("[data-schema-fields] input[name=f_title]").input_value()
        check(shown == "Stand R3b Titel", "текст из панели остался в черновике")
        pg.screenshot(path=f"{OUT}/r3_{w}.png", full_page=True)
        close_sheet(pg)
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
            close_sheet(pg)
            pg.locator("[data-schema-row] [data-schema-block]").last.click()
            pg.wait_for_load_state()
            pg.click("[data-schema-more] summary")
            pg.click("[data-schema-panel] a:has-text('Entfernen')")
            pg.wait_for_load_state()
            pg.click("button[value=delete]")
            pg.wait_for_load_state()
        close_sheet(pg)
        pg.click("[data-schema-draft] button[value=save]")
        pg.wait_for_load_state()
        pg.goto(U + "/dashboard/site/aufbau/?seite=text")
        close_sheet(pg)
        pg.click("[data-schema-add] summary")
        pg.select_option("select[name=type]", "text")
        pg.click("form:has(select[name=type]) button")
        pg.wait_for_load_state()
        close_sheet(pg)
        pg.click("[data-schema-draft] button[value=discard]")
        pg.wait_for_load_state()
        # R3b-2: блок «Liste» — что показать, какие и как; после «Speichern» на витрине
        close_sheet(pg)
        pg.click("[data-schema-add] summary")
        pg.select_option("select[name=type]", "list")
        pg.click("form:has(select[name=type]) button")
        pg.wait_for_load_state()
        check(pg.locator("[data-schema-list] fieldset").count() == 3, "у списка три группы полей")
        pg.select_option("[data-schema-list] select[name=f_source]", "products")
        pg.click("[data-schema-list] button[value=update]")
        pg.wait_for_load_state()
        check(
            pg.locator("[data-schema-which-mode=kategorie]").count() == 1
            and pg.locator("[data-schema-list] select[name=f_only]").count() == 1
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
        # R5: ручной состав — две позиции, вторая поднята наверх (V2: способ «Einzeln»)
        check(
            pg.locator("[data-schema-which-mode]").count() >= 2,
            "способ «Welche» — кнопки Regel · Kategorie · Einzeln",
        )
        pg.click("[data-schema-which-mode=einzeln]")
        pg.wait_for_load_state()
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
        close_sheet(pg)
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
        close_sheet(pg)
        pg.locator("[data-schema-row] [data-schema-block]").last.click()
        pg.wait_for_load_state()
        pg.click("[data-schema-more] summary")
        pg.click("[data-schema-panel] a:has-text('Entfernen')")
        pg.wait_for_load_state()
        pg.click("button[value=delete]")
        pg.wait_for_load_state()
        close_sheet(pg)
        pg.click("[data-schema-draft] button[value=save]")
        pg.wait_for_load_state()
        # R4: настройки типа страницы — в панели «★ Hauptliste» и на строке настроек
        pg.goto(U + "/dashboard/site/aufbau/?seite=catalog")
        close_sheet(pg)
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
        close_sheet(pg)
        pg.click("[data-schema-draft] button[value=discard]")
        pg.wait_for_load_state()
        pg.goto(U + "/dashboard/site/aufbau/?seite=text")
        close_sheet(pg)
        pg.click("[data-schema-block=__page]")
        pg.wait_for_load_state()
        check(
            pg.locator("[data-schema-setting=text_width]").count() == 1,
            "у текстовой страницы — строка «Einstellungen der Seite»",
        )
        # R6: готовая строка «Text + Kontakt» и блок «Textseite»
        pg.goto(U + "/dashboard/site/aufbau/?seite=text")
        check(pg.locator("select[name=type] optgroup").count() >= 3, "меню «+ Block» группами")
        before = pg.locator("[data-schema-row] [data-schema-block]").count()
        close_sheet(pg)
        pg.click("[data-schema-add] summary")
        pg.select_option("[data-schema-add-row] select", "text_contact")
        pg.click("[data-schema-add-row] button")
        pg.wait_for_load_state()
        rows = pg.locator("[data-schema-row]")
        last_row = rows.nth(rows.count() - 1).locator("[data-schema-block]").count()
        check(last_row == 2, f"готовая строка — два блока в одном ряду ({last_row})")
        close_sheet(pg)
        pg.click("[data-schema-add] summary")
        pg.select_option("select[name=type]", "textpage")
        pg.click("form:has(select[name=type]) button")
        pg.wait_for_load_state()
        pages = pg.locator("select[name=f_page] option").count()
        check(pages >= 2, f"панель «Textseite» предлагает страницы ({pages - 1})")
        check(pg.locator("[data-schema-source]").count() == 1, "ссылка на источник текста")
        pg.select_option("select[name=f_page]", index=1)
        pg.select_option("select[name=f_mode]", "teaser")
        pg.click("[data-schema-fields] button[value=update]")
        pg.wait_for_load_state()
        over = pg.evaluate("document.documentElement.scrollWidth - window.innerWidth")
        check(over <= 0, f"R6: без горизонтального вылета ({over})")
        pg.screenshot(path=f"{OUT}/r6_{w}.png", full_page=True)
        close_sheet(pg)
        pg.click("[data-schema-draft] button[value=save]")
        pg.wait_for_load_state()
        site = ctx.new_page()
        site.goto(U + "/ueber-uns/")
        check(site.locator("[data-block-textpage]").count() == 1, "текст страницы — на витрине")
        check(
            site.locator("[data-block-textpage] a:has-text('Weiterlesen')").count() == 1,
            "начало текста со ссылкой «Weiterlesen»",
        )
        over = site.evaluate("document.documentElement.scrollWidth - window.innerWidth")
        check(over <= 0, f"витрина с новыми блоками без вылета ({over})")
        site.screenshot(path=f"{OUT}/r6_site_{w}.png", full_page=True)
        site.close()
        for _i in range(pg.locator("[data-schema-row] [data-schema-block]").count() - before):
            pg.goto(U + "/dashboard/site/aufbau/?seite=text")
            close_sheet(pg)
            pg.locator("[data-schema-row] [data-schema-block]").last.click()
            pg.wait_for_load_state()
            pg.click("[data-schema-more] summary")
            pg.click("[data-schema-panel] a:has-text('Entfernen')")
            pg.wait_for_load_state()
            pg.click("button[value=delete]")
            pg.wait_for_load_state()
        close_sheet(pg)
        pg.click("[data-schema-draft] button[value=save]")
        pg.wait_for_load_state()
        # R7: своя схема категории заменяет блоки каталога на её странице
        pg.goto(U + "/dashboard/site/aufbau/")
        cats = pg.eval_on_selector_all(
            "select#schema-seite option",
            "els => els.map(e => e.value).filter(v => v.startsWith('category@'))",
        )
        check(len(cats) >= 1, f"категории — отдельными строками в выборе страницы ({len(cats)})")
        if cats:
            code = cats[0]
            slug = code.split(":", 1)[1]
            pg.goto(U + "/dashboard/site/aufbau/?seite=catalog")
            close_sheet(pg)
            pg.click("[data-schema-add] summary")
            pg.select_option("select[name=type]", "text")
            pg.click("form:has(select[name=type]) button")
            pg.wait_for_load_state()
            pg.fill("[data-schema-fields] input[name=f_title]", "Stand Katalogblock")
            pg.click("[data-schema-fields] button[value=update]")
            pg.wait_for_load_state()
            close_sheet(pg)
            pg.click("[data-schema-draft] button[value=save]")
            pg.wait_for_load_state()
            site = ctx.new_page()
            site.goto(U + f"/sortiment/{slug}/")
            check(
                "Stand Katalogblock" in site.content(), "категория без своей схемы — блок каталога"
            )
            pg.goto(U + f"/dashboard/site/aufbau/?seite={code}")
            check(
                pg.locator("[data-schema-category=catalog]").count() == 1,
                "строка категории: «zeigt die Blöcke des Katalogs»",
            )
            close_sheet(pg)
            pg.click("[data-schema-add] summary")
            pg.select_option("select[name=type]", "text")
            pg.click("form:has(select[name=type]) button")
            pg.wait_for_load_state()
            pg.fill("[data-schema-fields] input[name=f_title]", "Stand Kategorieblock")
            pg.click("[data-schema-fields] button[value=update]")
            pg.wait_for_load_state()
            check(
                pg.locator("[data-schema-category=own]").count() == 1,
                "после своего блока — «eigener Aufbau»",
            )
            over = pg.evaluate("document.documentElement.scrollWidth - window.innerWidth")
            check(over <= 0, f"R7: без горизонтального вылета ({over})")
            pg.screenshot(path=f"{OUT}/r7_{w}.png", full_page=True)
            close_sheet(pg)
            pg.click("[data-schema-draft] button[value=save]")
            pg.wait_for_load_state()
            site.goto(U + f"/sortiment/{slug}/")
            html = site.content()
            check(
                "Stand Kategorieblock" in html and "Stand Katalogblock" not in html,
                "своя схема категории заменила блок каталога",
            )
            site.goto(U + "/sortiment/")
            check("Stand Katalogblock" in site.content(), "в каталоге блок каталога остался")
            site.close()
            pg.goto(U + f"/dashboard/site/aufbau/?seite={code}")
            pg.click("[data-schema-category] summary")
            pg.click("[data-schema-category] button[value=reset]")
            pg.wait_for_load_state()
            close_sheet(pg)
            pg.click("[data-schema-draft] button[value=save]")
            pg.wait_for_load_state()
            check(
                pg.locator("[data-schema-category=catalog]").count() == 1,
                "«Eigene Blöcke entfernen» вернул блоки каталога",
            )
            pg.goto(U + "/dashboard/site/aufbau/?seite=catalog")
            close_sheet(pg)
            pg.locator("[data-schema-row] [data-schema-block]").last.click()
            pg.wait_for_load_state()
            pg.click("[data-schema-more] summary")
            pg.click("[data-schema-panel] a:has-text('Entfernen')")
            pg.wait_for_load_state()
            pg.click("button[value=delete]")
            pg.wait_for_load_state()
            close_sheet(pg)
            pg.click("[data-schema-draft] button[value=save]")
            pg.wait_for_load_state()
        check(not errs, "без JS-ошибок: " + "; ".join(errs[:2]))
        ctx.close()
print(f"\n{ok}/{ok + len(fail)}")
sys.exit(1 if fail else 0)
