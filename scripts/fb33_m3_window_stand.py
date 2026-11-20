"""FB-33 M3: стенд окна блока в «Seitenaufbau» (1440 и 390): вкладки, фокус, Texte, Fertig/Abbrechen.

Запуск (как aufbau_stand.py):
    uv run python scripts/text_pages_stand.py --setup        # один раз (тенант ptx, owner@ptx.test)
    python manage.py runserver 0.0.0.0:8000 --settings=config.settings.stand
    uv run --no-project --with playwright python scripts/fb33_m3_window_stand.py <папка для скриншотов>
Chromium — /opt/pw-browsers/chromium (playwright install не запускать). Итог: «N ✓, 0 ✗».
"""

# ruff: noqa: B023 — вложенные помощники вызываются в той же итерации цикла (pg, ref текущего размера)
import sys

from playwright.sync_api import sync_playwright

OUT = sys.argv[1]
U = "http://ptx.siteadaptor.de:8000"
ok, fail = 0, []


def check(c, label):
    global ok
    ok += bool(c)
    print(("  ✓ " if c else "  ✗ ") + label)
    if not c:
        fail.append(label)


with sync_playwright() as p:
    b = p.chromium.launch(
        executable_path="/opt/pw-browsers/chromium",
        args=["--host-resolver-rules=MAP *.siteadaptor.de 127.0.0.1"],
    )
    for w, h in ((1440, 900), (390, 844)):
        print(f"— {w}px")
        ctx = b.new_context(viewport={"width": w, "height": h}, device_scale_factor=1)
        pg = ctx.new_page()
        pg.goto(U + "/accounts/login/")
        pg.fill("input[name=login]", "owner@ptx.test")
        pg.fill("input[name=password]", "Stand-Passwort-123")
        pg.click("button[type=submit]")
        pg.wait_for_load_state()
        pg.goto(U + "/dashboard/site/aufbau/?seite=text")
        pg.click("[data-schema-add] summary") if w > 500 else None
        if w <= 500:
            done = pg.locator("[data-schema-done]")
            if done.count() and done.first.is_visible():
                done.first.click()
                pg.wait_for_load_state()
            pg.click("[data-schema-add] summary")
        pg.select_option("select[name=type]", "text")
        pg.click("form:has(select[name=type]) button")
        pg.wait_for_load_state()
        tabs = pg.locator("[data-window-tab-link]")
        check(tabs.count() == 2, f"у текста две вкладки ({tabs.count()})")
        wie = pg.locator("[data-window-tab=wie]")
        check(wie.is_visible(), "открыта «Wie anordnen»: вид и ширина")
        check(not pg.locator("[data-window-tab=texte]").is_visible(), "«Texte» скрыта")
        small = pg.evaluate(
            "[...document.querySelectorAll('[data-window-tab-link]')]"
            ".filter(a => a.getBoundingClientRect().height < 44).length"
        )
        check(small == 0, f"вкладки не ниже 44 px ({small})")
        pg.click("[data-window-tab-link=texte]")
        pg.wait_for_load_state()
        check(pg.locator("[data-window-tab=texte]").is_visible(), "клик открыл «Texte»")
        check("tab=texte" in pg.url, "адрес помнит вкладку")
        focused = pg.evaluate("document.activeElement && document.activeElement.id")
        check(focused == "schema-tab-texte", f"фокус — во вкладке ({focused})")
        pg.keyboard.press("Shift+Tab")  # из вкладки — назад на её ссылку
        ring = pg.evaluate(
            "[document.activeElement.getAttribute('data-window-tab-link'),"
            " getComputedStyle(document.activeElement).outlineStyle,"
            " getComputedStyle(document.activeElement).outlineWidth].join(' ')"
        )
        check(ring == "texte solid 2px", f"у ссылки вкладки виден фокус ({ring})")
        pg.fill("[data-schema-fields] input[name=f_title]", f"M3 Fenster {w}")
        pg.evaluate("document.activeElement && document.activeElement.blur()")
        pg.wait_for_function(
            "!+document.documentElement.getAttribute('data-schema-busy')", timeout=10000
        )
        pg.wait_for_load_state()
        check(
            pg.locator("[data-window-tab=texte]").is_visible(),
            "после автосохранения открыта та же вкладка",
        )
        check(
            pg.locator("[data-schema-fields] input[name=f_title]").input_value()
            == f"M3 Fenster {w}",
            "текст в черновике",
        )
        over = pg.evaluate("document.documentElement.scrollWidth - window.innerWidth")
        check(over <= 0, f"без горизонтального вылета ({over})")
        pg.screenshot(path=f"{OUT}/m3_window_{w}.png", full_page=False)
        pg.click("[data-window-tab-link=wie]")
        pg.wait_for_load_state()
        check(pg.locator("[data-schema-width]").is_visible(), "«Wie anordnen»: ширина на месте")
        # FB-33 M3-1b: «Fertig» закрывает (правка остаётся), «Abbrechen» — блок как при открытии
        from urllib.parse import parse_qs, urlparse

        ref = parse_qs(urlparse(pg.url).query)["block"][0]
        pg.click("[data-window-actions] button[value=window_done]")
        pg.wait_for_load_state()
        check("block=" not in pg.url, "«Fertig» закрыл окно")
        pg.goto(U + f"/dashboard/site/aufbau/?seite=text&block={ref}&tab=texte")
        pg.fill("[data-schema-fields] input[name=f_title]", "Nicht behalten")
        pg.evaluate("document.activeElement && document.activeElement.blur()")
        pg.wait_for_function(
            "!+document.documentElement.getAttribute('data-schema-busy')", timeout=10000
        )
        pg.click("[data-window-actions] button[value=revert]")
        pg.wait_for_load_state()
        check("block=" not in pg.url, "«Abbrechen» закрыл окно")
        check(pg.locator("[data-schema-messages], [role=status]").count() > 0, "есть сообщение")
        pg.goto(U + f"/dashboard/site/aufbau/?seite=text&block={ref}&tab=texte")
        back = pg.locator("[data-schema-fields] input[name=f_title]").input_value()
        check(back == f"M3 Fenster {w}", f"«Abbrechen» вернул текст на момент открытия ({back})")
        # правка ещё в пути (без blur) — «Abbrechen» ждёт её и всё равно откатывает
        pg.fill("[data-schema-fields] input[name=f_title]", "Auch nicht")
        pg.click("[data-window-actions] button[value=revert]")
        # отправка «Abbrechen» ждёт правку в пути — ждём, пока окно закроется
        pg.wait_for_url(lambda u: "block=" not in u, timeout=10000)
        pg.wait_for_load_state()
        pg.goto(U + f"/dashboard/site/aufbau/?seite=text&block={ref}&tab=texte")
        back = pg.locator("[data-schema-fields] input[name=f_title]").input_value()
        check(back == f"M3 Fenster {w}", f"откат и при правке в пути ({back})")

        # ревью M3-1b: повторное открытие окна — снимок с момента ВТОРОГО открытия
        def edit(text):
            pg.fill("[data-schema-fields] input[name=f_title]", text)
            pg.evaluate("document.activeElement && document.activeElement.blur()")
            pg.wait_for_function(
                "!+document.documentElement.getAttribute('data-schema-busy')", timeout=10000
            )

        open_url = U + f"/dashboard/site/aufbau/?seite=text&block={ref}&tab=texte"
        pg.goto(open_url)
        edit(f"Erst {w}")
        pg.goto(open_url)  # окно закрыли ссылкой и открыли снова — новый токен
        edit(f"Zweit {w}")
        pg.click("[data-window-actions] button[value=revert]")
        pg.wait_for_url(lambda u: "block=" not in u, timeout=10000)
        pg.goto(open_url)
        back = pg.locator("[data-schema-fields] input[name=f_title]").input_value()
        check(back == f"Erst {w}", f"Abbrechen — к моменту второго открытия ({back})")
        # без правок в этом окне — честное «нечего», не «zurückgenommen»
        pg.click("[data-window-actions] button[value=revert]")
        pg.wait_for_url(lambda u: "block=" not in u, timeout=10000)
        note = pg.locator("[data-schema-messages]").inner_text()
        check(
            ("Nichts zurückzunehmen" in note or "Nothing to undo" in note) and "undone" not in note,
            f"Abbrechen без снимка — предупреждение ({note[:50]})",
        )

        # ревью 2, п.1: правка из списка «Blöcke» (без окна, без токена) — Abbrechen её не трогает
        def blocks_toggle():
            with pg.expect_navigation():
                _toggle()

        def _toggle():
            pg.evaluate(
                """(ref) => {
                  const csrf = document.querySelector('input[name=csrfmiddlewaretoken]').value;
                  const f = document.createElement('form');
                  f.method = 'post'; f.action = '/dashboard/site/aufbau/';
                  for (const [k, v] of [['csrfmiddlewaretoken', csrf], ['seite', 'text'],
                      ['ref', ref], ['zurueck', 'seiten'], ['op', 'toggle']]) {
                    const i = document.createElement('input'); i.type = 'hidden';
                    i.name = k; i.value = v; f.appendChild(i);
                  }
                  document.body.appendChild(f); HTMLFormElement.prototype.submit.call(f);
                }""",
                ref,
            )

        pg.goto(U + "/dashboard/site/aufbau/?seite=text")
        blocks_toggle()
        pg.goto(open_url)
        pg.click("[data-window-actions] button[value=revert]")
        pg.wait_for_url(lambda u: "block=" not in u, timeout=10000)
        note = pg.locator("[data-schema-messages]").inner_text()
        pg.goto(open_url)
        hidden = pg.locator("#schema-panel").inner_text()
        check(
            ("Nichts zurückzunehmen" in note or "Nothing to undo" in note)
            and ("Ausgeblendet" in hidden or "Hidden" in hidden),
            f"правка из «Blöcke» осталась, Abbrechen — «нечего» ({note[:60]!r} / {hidden[:120]!r})",
        )
        pg.goto(U + "/dashboard/site/aufbau/?seite=text")
        blocks_toggle()  # вернуть показ

        # ревью 2, п.2: F5 — то же открытие: правка → F5 → правка → Abbrechen → как до первой
        pg.goto(U + "/dashboard/site/aufbau/?seite=text")
        pg.click(f'a[data-schema-block="{ref}"]')
        pg.wait_for_load_state()
        check("wopen=" in pg.url, "ссылка на блок несёт токен открытия")
        if pg.locator("[data-window-tab-link=texte]").is_visible():
            pg.click("[data-window-tab-link=texte]")
            pg.wait_for_load_state()
        before = pg.locator("[data-schema-fields] input[name=f_title]").input_value()
        edit(f"F5 eins {w}")
        pg.reload()
        pg.wait_for_load_state()
        edit(f"F5 zwei {w}")
        pg.click("[data-window-actions] button[value=revert]")
        pg.wait_for_url(lambda u: "block=" not in u, timeout=10000)
        pg.goto(open_url)
        back = pg.locator("[data-schema-fields] input[name=f_title]").input_value()
        check(back == before, f"правка → F5 → правка → Abbrechen: как при открытии ({back})")
        ctx.close()
    b.close()
print(f"{ok} ✓, {len(fail)} ✗")
sys.exit(1 if fail else 0)
