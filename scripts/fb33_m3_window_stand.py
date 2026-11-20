"""FB-33 M3: стенд окна блока в «Seitenaufbau» (1440 и 390): вкладки, фокус, Texte, Fertig/Abbrechen;
M3-2 — модальное окно (<dialog>, Esc/×, вкладки APG, геометрия, 44 px, сбой сети, без JS).

Запуск (как aufbau_stand.py):
    uv run python scripts/text_pages_stand.py --setup        # один раз (тенант ptx, owner@ptx.test)
    python manage.py runserver 0.0.0.0:8000 --settings=config.settings.stand
    uv run --no-project --with playwright python scripts/fb33_m3_window_stand.py <папка для скриншотов>
Chromium — /opt/pw-browsers/chromium (playwright install не запускать). Итог: «N ✓, 0 ✗».
Сервер на другом порту — `STAND_URL=http://ptx.siteadaptor.de:<порт>`. Firefox/Safari — вручную.
FB-33 M2i-5: вкладка «Felder» формы заявки — нужен модуль заявок у ptx
(`uv run python scripts/text_pages_stand.py --jobs`, один раз).
"""

# ruff: noqa: B023 — вложенные помощники вызываются в той же итерации цикла (pg, ref текущего размера)
import os
import sys
from urllib.parse import parse_qs, urlparse

from playwright.sync_api import sync_playwright

OUT = sys.argv[1]
U = os.environ.get("STAND_URL", "http://ptx.siteadaptor.de:8000")  # другой порт — STAND_URL
ok, fail = 0, []


def check(c, label):
    global ok
    ok += bool(c)
    print(("  ✓ " if c else "  ✗ ") + label)
    if not c:
        fail.append(label)


DLG = "dialog.ui-bwin"


def busy_done(pg):
    pg.wait_for_function(
        "!+document.documentElement.getAttribute('data-schema-busy')", timeout=15000
    )


def closed(pg):
    pg.wait_for_url(lambda u: "block=" not in u, timeout=20000)
    pg.wait_for_load_state()


def m32(pg, w, ref):
    """FB-33 M3-2: модальное окно блока."""
    page = U + "/dashboard/site/aufbau/?seite=text"
    open_url = f"{page}&block={ref}"
    pg.goto(open_url)
    # мерить после анимации открытия (160 мс) и шрифтов
    pg.wait_for_function("document.fonts.status === 'loaded' && !document.getAnimations().length")
    info = pg.evaluate(
        """(sel) => { const d = document.querySelector(sel); if (!d) return null;
        const r = d.getBoundingClientRect(), h = d.querySelector('#schema-panel-title');
        return {open: d.open, modal: d.matches(':modal'), am: d.getAttribute('aria-modal'),
          lb: d.getAttribute('aria-labelledby'), h2: !!h, panel: !!d.querySelector('#schema-panel[data-schema-panel]'),
          active: document.activeElement && document.activeElement.id,
          w: r.width, h: r.height, left: r.left, cw: document.documentElement.clientWidth,
          iw: innerWidth, ih: innerHeight, vw: (() => { const f = document.createElement('div');
            f.style.cssText = 'position:fixed;inset:0;visibility:hidden'; document.body.appendChild(f);
            const v = f.getBoundingClientRect().width; f.remove(); return v; })(), sw: document.documentElement.scrollWidth,
          inGrid: !!document.querySelector('[data-site-schema] [data-schema-panel]'),
          dialogs: document.querySelectorAll('dialog.ui-bwin').length} }""",
        DLG,
    )
    check(
        info and info["open"] and info["modal"], f"окно открыто модально ({info and info['modal']})"
    )
    check(
        info["am"] == "true" and info["lb"] == "schema-panel-title" and info["h2"],
        "aria-modal, aria-labelledby → заголовок блока",
    )
    check(
        info["panel"] and not info["inGrid"] and info["dialogs"] == 1,
        "панель перенесена в окно, одна",
    )
    check(info["active"] == "schema-panel-title", f"фокус на заголовке окна ({info['active']})")
    inert = pg.evaluate(
        """() => { const a = document.querySelector('[data-schema-map] a[data-schema-block]');
        a.focus(); return document.activeElement !== a; }"""
    )
    check(inert, "фон под окном недоступен (inert)")
    if w > 500:
        # по центру видимой области (поле полосы прокрутки страницы — не часть её)
        mid = info["left"] + info["w"] / 2 - info["vw"] / 2
        check(
            abs(info["w"] - 760) <= 2 and abs(mid) <= 2,
            f"1440: 760 px по центру ({info['w']}, {mid:+.1f})",
        )
        check(pg.locator(f"{DLG} [data-bwin-close]").is_visible(), "× видна")
    else:
        check(
            info["w"] == info["iw"] and info["h"] == info["ih"] and info["sw"] <= info["iw"],
            f"390: окно во весь экран ({info['w']}×{info['h']}, scrollWidth {info['sw']})",
        )
        check(
            not pg.locator(f"{DLG} [data-bwin-close]").is_visible(),
            "390: × скрыта, «Fertig» сверху",
        )
    small = pg.evaluate(
        """(sel) => [...document.querySelectorAll(sel + ' :is(a,button,summary,select,input,textarea,[role=tab])')]
          .filter(e => e.getClientRects().length && getComputedStyle(e).visibility !== 'hidden')
          .filter(e => !(e.tagName === 'A' && getComputedStyle(e).display === 'inline'))
          .map(e => (e.type === 'radio' || e.type === 'checkbox') ? (e.closest('label') || e) : e)
          .filter(e => e.getBoundingClientRect().height < 44)
          .map(e => e.tagName + ':' + (e.textContent || e.name || '').trim().slice(0, 12) + ':'
            + e.getBoundingClientRect().height.toFixed(2))""",
        DLG,
    )
    check(not small, f"цели в окне не ниже 44 px ({small[:4]})")
    y = pg.evaluate("() => { window.scrollTo(0, 400); return window.scrollY; }")
    check(y == 0, f"страница под окном не прокручивается ({y})")
    pg.wait_for_timeout(300)
    pg.screenshot(path=f"{OUT}/m32_open_{w}.png")
    # вкладки по APG: роли, стрелки, Home/End, адрес и F5
    roles = pg.evaluate(
        """(sel) => { const t = [...document.querySelectorAll(sel + ' [role=tab]')];
        return {n: t.length, list: !!document.querySelector(sel + ' [role=tablist][aria-label]'),
          sel: t.filter(a => a.getAttribute('aria-selected') === 'true').length,
          zero: t.filter(a => a.tabIndex === 0).length,
          ctl: t.every(a => { const p = document.getElementById(a.getAttribute('aria-controls'));
            return p && p.getAttribute('role') === 'tabpanel' && p.getAttribute('aria-labelledby') === a.id; })} }""",
        DLG,
    )
    check(
        roles["n"] == 2
        and roles["list"]
        and roles["sel"] == 1
        and roles["zero"] == 1
        and roles["ctl"],
        f"роли tablist/tab/tabpanel, одна выбранная в порядке Tab ({roles})",
    )
    pg.focus(f"{DLG} [role=tab][aria-selected=true]")
    first = pg.evaluate("document.activeElement.getAttribute('data-window-tab-link')")
    pg.keyboard.press("End")
    last = pg.evaluate("document.activeElement.getAttribute('data-window-tab-link')")
    shown = pg.locator(f"{DLG} [data-window-tab={last}]").is_visible()
    check(
        last != first and shown and f"tab={last}" in pg.url,
        f"End — последняя вкладка, адрес помнит ({last})",
    )
    pg.keyboard.press("Home")
    check(
        pg.evaluate("document.activeElement.getAttribute('aria-selected')") == "true"
        and pg.locator(f"{DLG} [data-window-tab={first}]").is_visible(),
        "Home — первая вкладка",
    )
    pg.keyboard.press("ArrowRight")
    pg.reload()
    pg.wait_for_load_state()
    after = pg.evaluate(
        "(sel) => document.querySelector(sel + ' [role=tab][aria-selected=true]')?.getAttribute('data-window-tab-link')",
        DLG,
    )
    check(after == last, f"F5 — та же вкладка ({after})")
    tabs_in_forms = pg.evaluate(
        """([sel, key]) => [...document.querySelectorAll(sel + ' [data-schema-panel] form')]
          .every(f => f.querySelector('input[name=tab]')?.value === key)""",
        [DLG, last],
    )
    check(tabs_in_forms, "формы панели несут выбранную вкладку")
    # ревью a11y: фокус на панели вкладки виден; панель в окне — не второй landmark
    pg.focus(f"{DLG} [role=tab][aria-selected=true]")
    pg.keyboard.press("Tab")
    ring = pg.evaluate(
        "[document.activeElement.getAttribute('role'), getComputedStyle(document.activeElement).outlineStyle].join(' ')"
    )
    check(ring == "tabpanel solid", f"Tab из вкладок — в панель, фокус виден ({ring})")
    grp = pg.evaluate(
        "(sel) => { const a = document.querySelector(sel + ' [data-schema-panel]');"
        " return [a.getAttribute('role'), a.hasAttribute('aria-labelledby')]; }",
        DLG,
    )
    check(grp == ["group", False], f"панель в окне — group без имени ({grp})")
    # ревью M5: «Fertig» кнопкой, затем Esc — один POST
    posts0 = []
    pg.on("request", lambda r: posts0.append(r.post_data or "") if r.method == "POST" else None)
    pg.evaluate(
        "(sel) => { document.querySelector(sel + ' [data-window-actions] button[value=window_done]').click();"
        " document.querySelector(sel).dispatchEvent(new Event('cancel', {cancelable: true})); }",
        DLG,
    )
    closed(pg)
    n = sum("op=window_done" in d for d in posts0)
    check(n == 1, f"«Fertig» кнопкой + Esc — один POST ({n})")
    # набрал текст → Esc: текст в черновике, окно закрыто, фокус на строке блока
    pg.goto(open_url + "&tab=texte")
    posts = []
    pg.on("request", lambda r: posts.append(r.post_data or "") if r.method == "POST" else None)
    pg.fill(f"{DLG} [data-schema-fields] input[name=f_title]", f"Esc {w}")
    pg.keyboard.press("Escape")
    pg.keyboard.press("Escape")  # двойной Esc — один «window_done»
    closed(pg)
    check(
        sum("op=window_done" in d for d in posts) == 1,
        f"двойной Esc — один POST ({sum('op=window_done' in d for d in posts)})",
    )
    focus = pg.evaluate(
        "document.activeElement && document.activeElement.getAttribute('data-schema-block')"
    )
    check(focus == ref, f"после закрытия фокус на строке блока ({focus})")
    check(pg.locator(DLG).count() == 0, "окно закрыто")
    pg.goto(open_url + "&tab=texte")
    got = pg.locator(f"{DLG} [data-schema-fields] input[name=f_title]").input_value()
    check(got == f"Esc {w}", f"набранное до Esc — в черновике ({got})")
    # × — то же, что «Fertig» (только на компьютере)
    if w > 500:
        pg.click(f"{DLG} [data-bwin-close]")
        closed(pg)
        check("block=" not in pg.url, "× закрыл окно")
    # Esc при открытом «⋯» — закрывает только меню
    pg.goto(open_url)
    pg.click(f"{DLG} details[data-schema-more] summary")
    pg.keyboard.press("Escape")
    still = pg.evaluate(
        "(sel) => [document.querySelector(sel)?.open, document.querySelector(sel + ' details[data-schema-more]').open]",
        DLG,
    )
    check(
        still == [True, False] and "block=" in pg.url,
        f"Esc при «⋯» — закрыл меню, окно осталось ({still})",
    )
    # Esc в подтверждении удаления — назад в окно блока
    pg.goto(open_url + "&entfernen=1")
    check(
        pg.locator(f"{DLG} [data-schema-confirm]").is_visible(), "подтверждение удаления — в окне"
    )
    pg.keyboard.press("Escape")
    pg.wait_for_url(lambda u: "entfernen" not in u, timeout=10000)
    pg.wait_for_load_state()
    check(
        pg.locator(DLG).count() == 1 and pg.locator(f"{DLG} [data-schema-confirm]").count() == 0,
        "Esc в подтверждении — снова окно блока",
    )
    # переключатель → Esc раньше 350 мс: выбор уходит до «Fertig»
    pg.goto(page)
    pg.click("[data-schema-add] summary")
    pg.select_option("select[name=type]", "list")
    pg.click("form:has(select[name=type]) button")
    pg.wait_for_load_state()
    lref = parse_qs(urlparse(pg.url).query)["block"][0]
    pick = pg.evaluate(
        """(sel) => [...document.querySelectorAll(sel + ' input[type=radio][name=f_out]')]
          .find(r => !r.checked).value""",
        DLG,
    )
    pg.click(f'{DLG} label:has(input[name=f_out][value="{pick}"])')
    pg.keyboard.press("Escape")
    closed(pg)
    pg.goto(f"{page}&block={lref}")
    now = pg.evaluate(
        "(sel) => document.querySelector(sel + ' input[name=f_out]:checked')?.value", DLG
    )
    check(now == pick, f"переключатель → Esc: выбор сохранён ({now})")
    # сбой сети: правка и закрытие не дошли — окно остаётся, ошибка в окне
    pg.goto(open_url + "&tab=texte")
    pg.route(
        "**/dashboard/site/aufbau/**",
        lambda r: r.abort("aborted") if r.request.method == "POST" else r.continue_(),
    )
    pg.fill(f"{DLG} [data-schema-fields] input[name=f_title]", f"Offline {w}")
    pg.keyboard.press("Escape")
    alert = pg.locator(f"{DLG} [role=alert]")
    alert.first.wait_for(state="visible", timeout=25000)
    check(
        alert.first.is_visible() and pg.locator(DLG).evaluate("d => d.open"),
        "сбой сети — окно открыто, ошибка внутри",
    )
    pg.unroute("**/dashboard/site/aufbau/**")
    m32_review(pg, page, lref, open_url)
    # уборка: блок «Liste» удаляем подтверждением
    pg.goto(f"{page}&block={lref}&entfernen=1")
    pg.click(f"{DLG} [data-schema-confirm] button[value=delete]")
    pg.wait_for_load_state()


def _patched(pg, route, how):
    """Настоящий ответ сервера на правку, изменённый: отказ или панель без окна. POST правки
    уходит на сервер, страница после его редиректа читается отдельно, браузеру — 200 с
    изменённой страницей. Напрямую на 127.0.0.1 с тем же Host: у `route.fetch` и
    `request` нет `--host-resolver-rules` браузера (редирект fetch маршрут не видит)."""
    req = route.request
    if req.method != "POST" or req.resource_type != "fetch":
        route.continue_()
        return
    parts = urlparse(req.url)
    local = f"http://127.0.0.1:{parts.port}"
    headers = req.all_headers()
    headers["host"] = parts.netloc
    resp = route.fetch(url=local + parts.path + "?" + parts.query, headers=headers, max_redirects=0)
    page = pg.context.request.get(
        local + resp.headers["location"],
        headers={"host": parts.netloc, "cookie": headers.get("cookie", "")},
    )
    html = page.text()
    if how == "refuse":
        at = html.index("data-schema-messages")
        end = html.index(">", at) + 1
        html = html[:end] + '<div role="alert">Stand: abgelehnt</div>' + html[end:]
    else:
        html = html.replace('value="window_done"', 'value="x_window_done"')
    route.fulfill(status=200, content_type="text/html; charset=utf-8", body=html)


def _pick_other(pg):
    return pg.evaluate(
        """(sel) => [...document.querySelectorAll(sel + ' input[type=radio][name=f_out]')]
          .find(r => !r.checked).value""",
        DLG,
    )


def m32_review(pg, page, lref, open_url):
    """Ревью M3-2 (silent-failure-hunter): окно не закрывается «мимо» и не умирает молча."""
    route = "**/dashboard/site/aufbau/**"
    # H3: отказ сервера на правку → Esc не отправляет «Fertig», отказ виден в окне
    pg.goto(f"{page}&block={lref}")
    posts = []
    pg.on("request", lambda r: posts.append(r.post_data or "") if r.method == "POST" else None)
    pg.route(route, lambda r: _patched(pg, r, "refuse"))
    pick = _pick_other(pg)
    pg.click(f'{DLG} label:has(input[name=f_out][value="{pick}"])')
    pg.keyboard.press("Escape")
    busy_done(pg)
    pg.wait_for_timeout(800)
    alert = pg.locator(f"{DLG} [role=alert]", has_text="Stand: abgelehnt")
    check(
        pg.locator(DLG).count() == 1
        and alert.count() == 1
        and not any("op=window_done" in d for d in posts),
        "отказ сервера — Esc не закрывает, отказ виден в окне",
    )
    pg.unroute(route)
    # ревью code-reviewer: отказ уже показан — второй Esc подряд закрывает окно («Fertig»)
    with pg.expect_navigation():
        pg.keyboard.press("Escape")
    pg.wait_for_load_state()
    check(
        any("op=window_done" in d for d in posts) and pg.locator(DLG).count() == 0,
        "второй Esc после показанного отказа — «Fertig», окно закрыто",
    )
    # H1 (dress): ответ сервера — панель без окна → окно закрыто, панель снова в сетке
    pg.goto(f"{page}&block={lref}")
    pg.route(route, lambda r: _patched(pg, r, "nowindow"))
    pick = _pick_other(pg)
    pg.click(f'{DLG} label:has(input[name=f_out][value="{pick}"])')
    busy_done(pg)
    pg.wait_for_timeout(500)
    state = pg.evaluate(
        "() => [document.querySelectorAll('dialog.ui-bwin').length,"
        " !!document.querySelector('[data-site-schema] [data-schema-panel]'),"
        " document.documentElement.classList.contains('ui-bwin-lock')]"
    )
    check(
        state == [0, True, False], f"панель без «Fertig» — окно закрыто, панель в сетке ({state})"
    )
    pg.unroute(route)
    # H1 (done): закрывать нечем — Esc не молчит: окно закрыто, ошибка видна
    pg.goto(f"{page}&block={lref}")
    pg.evaluate(
        "(sel) => document.querySelectorAll(sel + ' button[value=window_done]').forEach(b => b.remove())",
        DLG,
    )
    pg.keyboard.press("Escape")
    pg.wait_for_timeout(300)
    check(
        pg.locator(DLG).count() == 0
        and pg.locator("[data-schema-messages] [role=alert]").count() >= 1,
        "Esc без «Fertig» в панели — окно закрыто, ошибка на экране",
    )
    # H2: showModal бросил — панель остаётся колонкой, прокрутка не заперта
    ctx = pg.context
    pg2 = ctx.new_page()
    pg2.add_init_script(
        "HTMLDialogElement.prototype.showModal = function () { throw new Error('stand'); };"
    )
    pg2.goto(open_url)
    state = pg2.evaluate(
        "() => [document.querySelectorAll('dialog.ui-bwin').length,"
        " !!document.querySelector('[data-site-schema] [data-schema-panel]'),"
        " document.documentElement.classList.contains('ui-bwin-lock')]"
    )
    check(
        state == [0, True, False],
        f"showModal упал — панель колонкой, без замка прокрутки ({state})",
    )
    pg2.close()


def add_question(pg, w):
    pg.fill(f"{DLG} input[name=f_new_label]", f"Stand-Frage {w}")
    pg.click(f"{DLG} [data-form-add]")
    # отправка ждёт правку в пути (blur поля) и перезагружает страницу — ждём сам вопрос
    pg.wait_for_selector(
        f"{DLG} [data-form-question] input[value='Stand-Frage {w}']", timeout=15000
    )
    pg.wait_for_function("!document.getAnimations().length")


def felder(pg, w):
    """FB-33 M2i-5: вкладка «Felder» у формы «Anfrage» — режим поля, свой вопрос, Abbrechen
    откатывает, Fertig + Speichern — витрина /anfrage/ спрашивает вопрос."""
    page = U + "/dashboard/site/aufbau/?seite=anfrage"
    open_url = f"{page}&block=form&tab=felder"
    pg.goto(page)
    if pg.locator("button[name=op][value=discard]").count():
        pg.click("button[name=op][value=discard]")  # прежний черновик стенда
        pg.wait_for_load_state()
    pg.goto(open_url)
    pg.wait_for_function("!document.getAnimations().length")
    form = pg.locator(f"{DLG} [data-form-felder]")
    check(form.count() == 1 and form.is_visible(), f"{w}: «Felder» в окне формы заявки")
    groups = pg.locator(f"{DLG} [data-form-felder] fieldset[data-form-field] > legend")
    check(groups.count() >= 6, f"{w}: группы режимов с legend ({groups.count()})")
    check(
        pg.locator(f"{DLG} [data-form-field=title] input[type=radio]").count() == 0
        and "🔒" in pg.locator(f"{DLG} [data-form-field=title]").inner_text(),
        f"{w}: «Was brauchen Sie?» закреплено (🔒): "
        + pg.locator(f"{DLG} [data-form-field=title]").inner_text().replace("\n", " "),
    )
    small = pg.evaluate(
        """(sel) => [...document.querySelectorAll(sel + ' [data-form-felder] label:has(input[type=radio]),'
           + sel + ' [data-form-felder] button:not(.sr-only)')]
           .filter(e => e.offsetParent).filter(e => e.getBoundingClientRect().height < 43.5).length""",
        DLG,
    )
    check(small == 0, f"{w}: цели ≥ 44 px ({small} меньше)")
    sw = pg.evaluate("[document.documentElement.scrollWidth, innerWidth]")
    check(sw[0] <= sw[1], f"{w}: без горизонтальной прокрутки ({sw})")
    radio = f"{DLG} [data-form-field=description] input[value=req]"
    before = pg.locator(f"{DLG} [data-form-field=description] input:checked").get_attribute("value")
    pg.locator(radio).check()
    pg.wait_for_timeout(500)
    busy_done(pg)
    add_question(pg, w)
    labels = pg.locator(f"{DLG} [data-form-question] input[name$=_label]")
    added = [labels.nth(i).input_value() for i in range(labels.count())]
    check(f"Stand-Frage {w}" in added, f"{w}: вопрос добавлен в черновик ({added})")
    check(pg.locator(radio).is_checked(), f"{w}: режим «Pflicht» пережил добавление вопроса")
    pg.screenshot(path=f"{OUT}/m2i5_felder_{w}.png", full_page=False)
    pg.click(f"{DLG} [data-window-actions] button[value=revert]")
    closed(pg)
    pg.goto(open_url)
    pg.wait_for_function("!document.getAnimations().length")
    labels = pg.locator(f"{DLG} [data-form-question] input[name$=_label]")
    back = [labels.nth(i).input_value() for i in range(labels.count())]
    now = pg.locator(f"{DLG} [data-form-field=description] input:checked").get_attribute("value")
    check(
        f"Stand-Frage {w}" not in back and now == before,
        f"{w}: Abbrechen откатил вопрос и режим ({now} == {before})",
    )
    add_question(pg, w)
    pg.click(f"{DLG} [data-window-actions] button[value=window_done]")
    closed(pg)
    pg.click("button[name=op][value=save]")
    pg.wait_for_load_state()
    pg.goto(U + "/anfrage/")
    check(f"Stand-Frage {w}" in pg.content(), f"{w}: Speichern → /anfrage/ спрашивает вопрос")
    pg.screenshot(path=f"{OUT}/m2i5_anfrage_{w}.png", full_page=True)
    # уборка стенда: вопрос снова убрать
    pg.goto(open_url)
    pg.wait_for_function("!document.getAnimations().length")
    box = pg.locator(f"{DLG} [data-form-question]:has(input[value='Stand-Frage {w}'])")
    box.locator("button[value^='del:']").click()
    pg.wait_for_selector(
        f"{DLG} [data-form-question] input[value='Stand-Frage {w}']", state="detached"
    )
    pg.wait_for_function("!document.getAnimations().length")
    pg.click(f"{DLG} [data-window-actions] button[value=window_done]")
    closed(pg)
    pg.click("button[name=op][value=save]")
    pg.wait_for_load_state()
    pg.goto(U + "/anfrage/")
    check(f"Stand-Frage {w}" not in pg.content(), f"{w}: уборка — вопрос снят")


def nojs(b):
    """Без скриптов окна нет — прежняя панель колонкой."""
    for w, h in ((1440, 900), (390, 844)):
        ctx = b.new_context(viewport={"width": w, "height": h}, java_script_enabled=False)
        pg = ctx.new_page()
        pg.goto(U + "/accounts/login/")
        pg.fill("input[name=login]", "owner@ptx.test")
        pg.fill("input[name=password]", "Stand-Passwort-123")
        pg.click("button[type=submit]")
        pg.wait_for_load_state()
        pg.goto(U + "/dashboard/site/aufbau/?seite=text&block=__page")
        html = pg.content()
        check(
            '<dialog class="ui-bwin' not in html
            and pg.locator("[data-site-schema] aside#schema-panel").count() == 1
            and pg.locator("[role=tab]").count() == 0,
            f"{w}: без JS — окна и ролей вкладок нет, панель в сетке",
        )
        pg.screenshot(path=f"{OUT}/m32_nojs_{w}.png")
        pg.goto(U + "/dashboard/site/aufbau/?seite=anfrage&block=form&tab=felder")
        check(
            pg.locator("[data-site-schema] [data-form-felder]").count() == 1
            and pg.locator("[data-form-felder] button[data-schema-apply]").is_visible(),
            f"{w}: без JS — «Felder» в панели, «Übernehmen» видна",
        )
        pg.screenshot(path=f"{OUT}/m2i5_nojs_{w}.png")
        ctx.close()


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
        check(focused == "schema-tabbtn-texte", f"фокус — на вкладке ({focused})")
        pg.keyboard.press("ArrowLeft")  # M3-2: вкладки по APG — стрелками, фокус с клавиатуры
        pg.keyboard.press("ArrowRight")
        ring = pg.evaluate(
            "[document.activeElement.getAttribute('data-window-tab-link'),"
            " getComputedStyle(document.activeElement).outlineStyle,"
            " getComputedStyle(document.activeElement).outlineWidth].join(' ')"
        )
        check(ring == "texte solid 2px", f"у вкладки виден фокус ({ring})")
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
        pg.wait_for_timeout(300)  # анимация открытия
        pg.screenshot(path=f"{OUT}/m3_window_{w}.png", full_page=False)
        pg.click("[data-window-tab-link=wie]")
        pg.wait_for_load_state()
        check(pg.locator("[data-schema-width]").is_visible(), "«Wie anordnen»: ширина на месте")
        # FB-33 M3-1b: «Fertig» закрывает (правка остаётся), «Abbrechen» — блок как при открытии
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
        m32(pg, w, ref)
        felder(pg, w)
        ctx.close()
    nojs(b)
    b.close()
print(f"{ok} ✓, {len(fail)} ✗")
sys.exit(1 if fail else 0)
