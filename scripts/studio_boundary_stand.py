"""FB-27 R8: браузерный стенд границы «Студия ↔ Seitenaufbau» (1440 и 390 px).

    python manage.py runserver 0.0.0.0:8000 --settings=config.settings.stand
    uv run --with playwright==1.55.0 python scripts/studio_boundary_stand.py <папка>

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
STRUCT = (
    "[name^='order_'], [name^='enabled_'], [name^='delete_cb_'], [name^='width_cb_'], "
    "[name^='newline_cb_'], .blk-up, .blk-down, "
    "#bld-action-bar [data-ab=up], #bld-action-bar [data-ab=down], "
    "#bld-action-bar [data-ab=vis], #bld-action-bar [data-ab=del]"
)
VISIBLE = (
    "els => els.filter(e => { const r = e.getBoundingClientRect(); "
    "return r.width > 0 && r.height > 0 && getComputedStyle(e).visibility !== 'hidden'; }).length"
)
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
        print(f"--- {w}px")
        # в «Seitenaufbau» добавляем свой блок на главную — Студия должна его показать
        pg.goto(U + "/dashboard/site/aufbau/?seite=home")
        close_sheet(pg)
        pg.click("[data-schema-add] summary")
        pg.select_option("select[name=type]", "text")
        pg.click("form:has(select[name=type]) button")
        pg.wait_for_load_state()
        pg.fill("[data-schema-fields] input[name=f_title]", "Stand Grenze")
        # правка в панели уходит в черновик сама (без «Übernehmen») — ждём, пока доедет
        pg.evaluate("document.activeElement && document.activeElement.blur()")
        pg.wait_for_function("!+document.documentElement.getAttribute('data-schema-busy')")
        pg.wait_for_load_state()
        close_sheet(pg)
        pg.click("[data-schema-draft] button[value=save]")
        pg.wait_for_load_state()
        pg.goto(U + "/dashboard/site/home/")
        pg.wait_for_load_state("networkidle")
        n = pg.eval_on_selector_all(STRUCT, VISIBLE)
        total = pg.locator(STRUCT).count()
        check(total > 0 and n == 0, f"контролы структуры в Студии не видны ({n} из {total})")
        check(
            pg.locator("[data-stu-struct-hint] a").count() == 1,
            "в Студии есть ссылка «Aufbau ändern»",
        )
        frame = next((f for f in pg.frames if f != pg.main_frame and "preview" in f.url), None)
        if frame is not None:
            try:
                frame.wait_for_selector("[data-sf-section]", timeout=8000)
                seen = frame.eval_on_selector_all("[data-sf-ins],[data-sf-drag]", VISIBLE)
                check(seen == 0, f"на холсте нет «+» вставки и ручек перетаскивания ({seen})")
            except Exception as exc:  # noqa: BLE001
                check(False, f"холст Студии не загрузился: {exc}")
        else:
            check(False, "кадр предпросмотра Студии не найден")
        pg.screenshot(path=f"{OUT}/r8_studio_{w}.png", full_page=False)
        # «Speichern» нетронутой формы: без сообщения о структуре, блок на месте
        before = pg.evaluate(
            "fetch('/dashboard/site/aufbau/?seite=home').then(r => r.text())"
            ".then(t => (t.match(/data-schema-block=/g) || []).length)"
        )
        with pg.expect_navigation(wait_until="load", timeout=30000):
            pg.evaluate("document.getElementById('home-form').requestSubmit()")
        pg.wait_for_load_state("networkidle")
        body = pg.content()
        check(
            "hier wurden nur die Inhalte gespeichert" not in body, "нетронутая форма: без сообщения"
        )
        after = pg.evaluate(
            "fetch('/dashboard/site/aufbau/?seite=home').then(r => r.text())"
            ".then(t => (t.match(/data-schema-block=/g) || []).length)"
        )
        check(before == after, f"«Speichern» Студии не изменил состав главной ({before} → {after})")
        # уборка: убрать блок стенда в «Seitenaufbau»
        pg.goto(U + "/dashboard/site/aufbau/?seite=home")
        close_sheet(pg)
        pg.locator("[data-schema-block]").filter(has_text="Stand Grenze").first.click()
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
