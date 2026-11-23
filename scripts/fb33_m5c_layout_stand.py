"""FB-33 стопка 11 (M5c-4, M5c-5): стенд полос схемы и раскладки «Seitenaufbau» — ссылки полос
шапки и подвала, полоса черновика на телефоне, схема одной колонкой при окне-диалоге, панель
без JS под схемой.

Что проверяет (план `docs/fb33-stack11-plan-2026-11-23.md` §2 C3/C4, §8.1 L, §8.2 A3):
- полосы (1440/390, de/ru, с JS и без): «Menü bearbeiten», «Design», «Fußzeile bearbeiten» —
  ссылки на свои экраны, подчёркнуты, цель ≥ 44 px; «Fußzeile bearbeiten» открывает «Menü» на
  вкладке «Fußzeile» (кнопка вкладки выбрана, её панель видна);
- черновик: без черновика полосы нет; с черновиком — 390×844 полоса прибита к низу (над
  таб-баром), 844×390 и 320×256 — в потоке шапки; Tab по всем стопам `#main`: прямоугольник
  фокуса не заходит под полосу; конец схемы («Fußzeile») докручивается выше полосы;
- 1440 с JS: окно блока открыто — схема одной колонкой ≤ 760 px по центру (`data-schema-solo`),
  после Esc — снова две колонки, флага нет;
- без JS 1024, 1279 и 390: панель выбранного блока — под схемой, в потоке (не лист поверх),
  переход `#schema-panel` показывает её, «Fertig» сверху виден; с JS 1024 — в окне её нет;
- 390×844 с JS: полоса вплотную над таб-баром; 320×568 со шрифтом 200 % — полоса в потоке.

Запуск (демо-киты в стенд-БД, вход `<kit>@example.com` / `demo-12345678`):
    DB_NAME=<стенд-БД> python manage.py runserver 0.0.0.0:8044 --settings=config.settings.stand --noreload
    STAND_URL=http://ptx.siteadaptor.de:8044 \\
        uv run --no-project --with playwright python scripts/fb33_m5c_layout_stand.py <папка> [kit …]
Правки живут только в черновике сессии (каждый проход — новый вход). Итог: «N ✓, M ✗».
"""

from __future__ import annotations

import sys
from urllib.parse import parse_qs, urlparse

import standlib as sl

OUT = sys.argv[1] if len(sys.argv) > 1 else "/tmp/fb33_m5c_layout_shots"
KITS = tuple(sys.argv[2:]) or ("shop", "friseur", "restaurant")
PORT = urlparse(sl.BASE_URL).port or 80
DEMO_PASSWORD = "demo-12345678"
DLG = "dialog.ui-bwin"
SEITE = "home"
#: телефон, телефон боком, 400 % (WCAG 1.4.10)
DRAFT_SIZES = ((390, 844), (844, 390), (320, 256))
HOSTS = {"restaurant": "restaurant-demo"}

STRIPS_JS = """() => {
  const out = {};
  for (const name of ['head', 'foot']) {
    const s = document.querySelector(`[data-schema-strip="${name}"]`);
    out[name] = s ? [...s.querySelectorAll('a')].map(a => {
      const r = a.getBoundingClientRect(); const cs = getComputedStyle(a);
      return {href: a.getAttribute('href'), text: a.textContent.trim(), h: Math.round(r.height),
        underline: cs.textDecorationLine.includes('underline')};
    }) : null;
  }
  return out;
}"""

BAR_JS = """() => {
  const b = document.querySelector('[data-schema-draftbar]');
  if (!b) return null;
  const r = b.getBoundingClientRect(); const cs = getComputedStyle(b);
  return {pos: cs.position, top: r.top, bottom: r.bottom, h: r.height, vh: innerHeight,
    note: !!b.querySelector('[data-schema-draft-note]'), form: !!b.querySelector('form[data-schema-draft]'),
    varH: getComputedStyle(document.documentElement).getPropertyValue('--schema-draft-h').trim(),
    flow: document.documentElement.hasAttribute('data-schema-draft-flow'),
    tabTop: (() => { const n = document.querySelector('nav[data-tabbar]');
      return n && n.getClientRects().length ? n.getBoundingClientRect().top : null; })()};
}"""

DONE_JS = """() => {
  const d = document.querySelector('[data-schema-panel] [data-schema-done]');
  return d ? d.getClientRects().length > 0 && getComputedStyle(d).visibility !== 'hidden' : null;
}"""

FOCUS_JS = """() => {
  const a = document.activeElement;
  if (!a || a === document.body) return {none: true};
  const r = a.getBoundingClientRect();
  const bar = document.querySelector('[data-schema-draftbar]');
  const br = bar ? bar.getBoundingClientRect() : null;
  const fixed = bar && getComputedStyle(bar).position === 'fixed';
  return {inMain: !!a.closest('#main'), inBar: !!(bar && bar.contains(a)),
    tag: a.tagName, label: (a.getAttribute('aria-label') || a.textContent || '').trim().slice(0, 40),
    top: r.top, bottom: r.bottom, h: r.height, barTop: fixed ? br.top : null,
    vis: r.height > 0 && r.width > 0};
}"""

GRID_JS = """() => {
  const g = document.querySelector('[data-site-schema]');
  const m = document.querySelector('[data-schema-map]');
  const gr = g.getBoundingClientRect(); const mr = m.getBoundingClientRect();
  const main = document.getElementById('main').getBoundingClientRect();
  return {solo: g.hasAttribute('data-schema-solo'),
    cols: getComputedStyle(g).gridTemplateColumns.split(' ').length,
    mapW: Math.round(mr.width), left: Math.round(mr.left - main.left), right: Math.round(main.right - mr.right)};
}"""

PANEL_JS = """() => {
  const p = document.querySelector('[data-schema-panel]');
  const m = document.querySelector('[data-schema-map]');
  const pr = p.getBoundingClientRect(); const mr = m.getBoundingClientRect();
  return {pos: getComputedStyle(p).position, below: pr.top >= mr.bottom - 1,
    inView: pr.top < innerHeight && pr.bottom > 0, top: Math.round(pr.top)};
}"""


def base_of(slug):
    return f"http://{HOSTS.get(slug, slug)}.siteadaptor.de:{PORT}"


def aufbau(slug, extra=""):
    return f"{base_of(slug)}/dashboard/site/aufbau/?seite={SEITE}{extra}"


def press(pg, selector):
    pg.focus(selector)
    pg.keyboard.press("Enter")


def gears(pg):
    return pg.eval_on_selector_all(
        "[data-schema-gear]", "els => els.map(e => e.getAttribute('data-schema-gear'))"
    )


def guarded(rep, t, fn, *args):
    try:
        fn(*args)
    except Exception as exc:  # noqa: BLE001 — стенд: сбой сценария — ✗ с причиной, обход идёт дальше
        rep.check(
            False, f"{t}: {fn.__name__} — сбой {type(exc).__name__}: {str(exc)[:160]}", code="crash"
        )


def page_for(rep, browser, slug, w, h, lang, js):
    pg = sl.open_page(browser, w, h, js=js, lang=lang, url=base_of(slug))
    t = f"{slug} {w}×{h} {lang} {'js' if js else 'nojs'}"
    email = f"{HOSTS.get(slug, slug)}@example.com"
    ok = sl.login(pg, base_of(slug), email, DEMO_PASSWORD)
    if not ok:
        # лимит входов allauth (≈30 в минуту с адреса) — переждать и войти ещё раз
        pg.wait_for_timeout(61000)
        ok = sl.login(pg, base_of(slug), email, DEMO_PASSWORD)
    rep.check(ok, f"{t}: вход", code="login")
    return (pg, t) if ok else (None, t)


def check_strips(rep, pg, t, js, slug):
    pg.goto(aufbau(slug))
    sl.settle(pg, js)
    s = pg.evaluate(STRIPS_JS)
    head = s.get("head") or []
    foot = s.get("foot") or []
    paths = [urlparse(a["href"]).path for a in head]
    rep.check(
        paths == ["/dashboard/site/menu/", "/dashboard/design/"],
        f"{t}: шапка — «Menü bearbeiten» и «Design» ({paths})",
        code="strip-head",
    )
    rep.check(
        len(foot) == 1 and foot[0]["href"].endswith("/dashboard/site/menu/?tab=footer"),
        f"{t}: подвал — «Fußzeile bearbeiten» ({[a['href'] for a in foot]})",
        code="strip-foot",
    )
    links = head + foot
    rep.check(
        bool(links) and all(a["h"] >= 44 for a in links),
        f"{t}: ссылки полос ≥ 44 px ({[a['h'] for a in links]})",
        code="strip-44",
    )
    rep.check(
        bool(links) and all(a["underline"] for a in links),
        f"{t}: ссылки полос подчёркнуты",
        code="strip-underline",
    )
    if not foot:
        return
    with pg.expect_navigation():
        press(pg, '[data-schema-strip="foot"] a')
    pg.wait_for_load_state()
    sl.settle(pg, js)
    q = parse_qs(urlparse(pg.url).query)
    st = pg.evaluate(
        "() => { const b = document.getElementById('menu-tab-footer');"
        "const p = document.getElementById('menu-pane-footer');"
        "return {sel: b ? b.getAttribute('aria-selected') : null,"
        "shown: !!(p && !p.hidden && p.getClientRects().length)}; }"
    )
    rep.check(
        q.get("tab") == ["footer"] and st["sel"] == "true" and st["shown"],
        f"{t}: «Fußzeile bearbeiten» → «Menü» на вкладке «Fußzeile» ({st})",
        code="strip-footer-tab",
    )


def make_draft(pg, js, slug):
    """Черновик: «＋ Block» в конце → «Text» (с JS окно нового блока закрыть Esc)."""
    pg.goto(aufbau(slug))
    sl.settle(pg, js)
    press(pg, "#schema-add-end")
    with pg.expect_navigation():
        press(pg, 'details[data-schema-add="end"] button[name=type][value=text]')
    if js:
        pg.wait_for_selector(f"{DLG}[open]", timeout=10000)
        sl.settle(pg, True)
        pg.keyboard.press("Escape")
        pg.wait_for_url(lambda u: "block=" not in u, timeout=20000)
    pg.goto(aufbau(slug))
    sl.settle(pg, js)


def check_draft(rep, pg, t, w, h, js, slug):
    pg.goto(aufbau(slug))
    sl.settle(pg, js)
    rep.check(pg.evaluate(BAR_JS) is None, f"{t}: без черновика полосы нет", code="bar-none")
    make_draft(pg, js, slug)
    bar = pg.evaluate(BAR_JS)
    if not rep.check(bar is not None, f"{t}: с черновиком полоса есть", code="bar-present"):
        return
    rep.check(
        bar["note"] and bar["form"], f"{t}: «Entwurf · n» и кнопки — в полосе", code="bar-both"
    )
    want_fixed = w < 768 and h >= 480
    rep.check(
        (bar["pos"] == "fixed") == want_fixed,
        f"{t}: полоса {'прибита к низу' if want_fixed else 'в потоке'} ({bar['pos']})",
        code="bar-pos",
    )
    if want_fixed:
        # с JS — измеренная высота; без JS — запас правила app.css (5.5rem) не меньше полосы
        var = bar["varH"]
        px = float(var[:-3]) * 16 if var.endswith("rem") else float(var[:-2] or 0)
        ok = px == round(bar["h"] + 0.4999) if js else px >= bar["h"]
        rep.check(
            bar["bottom"] <= bar["vh"] + 0.5 and ok,
            f"{t}: высота полосы в --schema-draft-h ({var} / {bar['h']:.1f})",
            code="bar-var",
        )
        if js and bar["tabTop"] is not None:
            # ревью C3–C4: таб-бар измерен — полоса стоит вплотную над ним (ни щели, ни наезда)
            gap = bar["tabTop"] - bar["bottom"]
            rep.check(
                abs(gap) <= 1, f"{t}: полоса над таб-баром вплотную ({gap:+.1f})", code="bar-tab"
            )
    sl.shot(pg, OUT, f"m5c4_draft_{slug}_{w}x{h}_{'js' if js else 'nojs'}")
    # Tab по всем стопам #main: фокус не под полосой
    pg.evaluate("() => { window.scrollTo(0, 0); document.getElementById('main').focus(); }")
    under, stops, seen = [], 0, set()
    for _i in range(220):
        pg.keyboard.press("Tab")
        f = pg.evaluate(FOCUS_JS)
        if f.get("none"):
            continue
        key = (f["tag"], f["label"], round(f["top"] + pg.evaluate("scrollY")))
        if key in seen and stops > 5:
            break
        seen.add(key)
        if not f["inMain"]:
            if stops > 5:
                break
            continue
        stops += 1
        if f["inBar"] or not f["vis"] or f["barTop"] is None:
            continue
        if f["bottom"] > f["barTop"] + 0.5:
            under.append(f"{f['tag']} «{f['label']}» {f['bottom']:.0f}>{f['barTop']:.0f}")
    rep.check(stops >= 5, f"{t}: Tab-обход ({stops} стопов)", code="tab-walk")
    rep.check(not under, f"{t}: фокус не под полосой ({under[:3]})", code="tab-under")
    # конец схемы докручивается выше полосы
    pg.evaluate("() => window.scrollTo(0, document.documentElement.scrollHeight)")
    pg.wait_for_function(
        "() => Math.abs(scrollY + innerHeight - document.documentElement.scrollHeight) <= 2"
    )
    end = pg.evaluate(
        "() => { const f = document.querySelector('[data-schema-strip=\"foot\"]').getBoundingClientRect();"
        "const b = document.querySelector('[data-schema-draftbar]').getBoundingClientRect();"
        "const fixed = getComputedStyle(document.querySelector('[data-schema-draftbar]')).position === 'fixed';"
        "return {foot: f.bottom, bar: fixed ? b.top : innerHeight}; }"
    )
    rep.check(
        end["foot"] <= end["bar"] + 0.5,
        f"{t}: «Fußzeile» выше полосы в конце страницы ({end})",
        code="bar-end",
    )
    over = pg.evaluate("() => document.documentElement.scrollWidth - innerWidth")
    rep.check(over <= 0, f"{t}: без гор. прокрутки ({over})", code="overflow")


def check_big_font(rep, pg, t, slug):
    """Ревью C3–C4 (WCAG 1.4.10): 320×568, шрифт 200 % — полоса с таб-баром выше 35 % экрана
    уходит в поток шапки."""
    make_draft(pg, True, slug)
    pg.evaluate("() => { document.documentElement.style.fontSize = '200%'; }")
    pg.evaluate("() => window.dispatchEvent(new Event('resize'))")
    try:
        pg.wait_for_function(
            "() => document.documentElement.hasAttribute('data-schema-draft-flow')", timeout=3000
        )
    except Exception:  # noqa: BLE001 — итог — проверка ниже
        pass
    bar = pg.evaluate(BAR_JS)
    rep.check(
        bar is not None and bar["flow"] and bar["pos"] == "static",
        f"{t}: шрифт 200 % — полоса в потоке ({bar and bar['pos']}, flow={bar and bar['flow']})",
        code="bar-flow",
    )
    # гор. прокрутка кабинета при 200 % на 320 — не про полосу (шапка экрана); только пометка
    over = pg.evaluate("() => document.documentElement.scrollWidth - innerWidth")
    if over > 0:
        rep.note(f"{t}: шрифт 200 % — гор. прокрутка страницы {over}px (шапка кабинета, вне среза)")


def check_dialog_done(rep, pg, t, slug):
    """Ревью C3–C4: в окне-диалоге на компьютере верхней «Fertig» нет (как раньше)."""
    refs = gears(pg) or []
    pg.goto(aufbau(slug, f"&block={refs[0]}") if refs else aufbau(slug))
    pg.wait_for_selector(f"{DLG}[open]", timeout=10000)
    sl.settle(pg, True)
    rep.check(pg.evaluate(DONE_JS) is False, f"{t}: в окне верхней «Fertig» нет", code="dlg-done")


def check_solo(rep, pg, t, slug):
    pg.goto(aufbau(slug))
    sl.settle(pg, True)
    before = pg.evaluate(GRID_JS)
    refs = gears(pg)
    if not refs:
        rep.check(False, f"{t}: строки для окна есть", code="solo-rows")
        return
    pg.goto(aufbau(slug, f"&block={refs[0]}"))
    pg.wait_for_selector(f"{DLG}[open]", timeout=10000)
    sl.settle(pg, True)
    during = pg.evaluate(GRID_JS)
    rep.check(
        during["solo"] and during["cols"] == 1 and during["mapW"] <= 760,
        f"{t}: окно открыто — одна колонка ≤ 760 ({during})",
        code="solo-on",
    )
    rep.check(
        abs(during["left"] - during["right"]) <= 2,
        f"{t}: схема по центру ({during['left']}/{during['right']})",
        code="solo-center",
    )
    sl.shot(pg, OUT, f"m5c4_solo_{slug}_1440")
    pg.keyboard.press("Escape")
    pg.wait_for_url(lambda u: "block=" not in u, timeout=20000)
    pg.wait_for_load_state()
    sl.settle(pg, True)
    after = pg.evaluate(GRID_JS)
    rep.check(
        not after["solo"] and after["cols"] == before["cols"] == 2,
        f"{t}: окно закрыто — как было ({before['cols']}→{after['cols']}, solo={after['solo']})",
        code="solo-off",
    )
    # закрытие без перезагрузки (closeWindow напрямую) тоже снимает флаг
    pg.goto(aufbau(slug, f"&block={refs[0]}"))
    pg.wait_for_selector(f"{DLG}[open]", timeout=10000)
    flag = pg.evaluate(
        "() => { window.aufbauWindow.close();"
        "return document.querySelector('[data-site-schema]').hasAttribute('data-schema-solo'); }"
    )
    rep.check(not flag, f"{t}: closeWindow снимает флаг", code="solo-close")


def check_nojs_panel(rep, pg, t, slug):
    pg.goto(aufbau(slug))
    refs = gears(pg)
    if not refs:
        rep.check(False, f"{t}: строки есть", code="panel-rows")
        return
    pg.goto(aufbau(slug, f"&block={refs[0]}#schema-panel"))
    pg.wait_for_load_state()
    st = pg.evaluate(PANEL_JS)
    rep.check(
        st["pos"] == "static" and st["below"],
        f"{t}: без JS панель под схемой, в потоке ({st})",
        code="panel-below",
    )
    rep.check(
        st["inView"], f"{t}: #schema-panel показывает панель ({st['top']})", code="panel-view"
    )
    # ревью C3–C4: до 1280 без JS панель под схемой — «Fertig» сверху виден
    rep.check(pg.evaluate(DONE_JS) is True, f"{t}: без JS «Fertig» панели виден", code="nojs-done")
    sl.shot(pg, OUT, f"m5c4_nojs_panel_{slug}_{pg.viewport_size['width']}")


def main():
    rep = sl.Report()
    with sl.launch() as browser:
        for slug in KITS:
            # полосы: 1440/390, de/ru, без JS и с JS
            for w, h, lang, js in sl.matrix():
                pg, t = page_for(rep, browser, slug, w, h, lang, js)
                if pg is None:
                    continue
                guarded(rep, t, check_strips, rep, pg, t, js, slug)
                rep.check(not pg.js_errors, f"{t}: без ошибок JS ({pg.js_errors[:2]})", code="js")
                pg.context.close()
            # черновик: телефон, боком, 400 %; без JS и с JS
            for js in (False, True):
                for w, h in DRAFT_SIZES:
                    pg, t = page_for(rep, browser, slug, w, h, "de", js)
                    if pg is None:
                        continue
                    guarded(rep, t, check_draft, rep, pg, t, w, h, js, slug)
                    rep.check(
                        not pg.js_errors, f"{t}: без ошибок JS ({pg.js_errors[:2]})", code="js"
                    )
                    pg.context.close()
            # 1440 с JS — одна колонка при окне
            pg, t = page_for(rep, browser, slug, 1440, 900, "de", True)
            if pg is not None:
                guarded(rep, t, check_solo, rep, pg, t, slug)
                rep.check(not pg.js_errors, f"{t}: без ошибок JS ({pg.js_errors[:2]})", code="js")
                pg.context.close()
            # ревью C3–C4: 320×568 с крупным шрифтом; окно-диалог на 1024
            pg, t = page_for(rep, browser, slug, 320, 568, "de", True)
            if pg is not None:
                guarded(rep, t, check_big_font, rep, pg, t, slug)
                pg.context.close()
            pg, t = page_for(rep, browser, slug, 1024, 768, "de", True)
            if pg is not None:
                pg.goto(aufbau(slug))
                sl.settle(pg, True)
                guarded(rep, t, check_dialog_done, rep, pg, t, slug)
                pg.context.close()
            # без JS 1024, 1279 и 390 — панель под схемой
            for w, h in ((1024, 768), (1279, 800), (390, 844)):
                pg, t = page_for(rep, browser, slug, w, h, "de", False)
                if pg is not None:
                    guarded(rep, t, check_nojs_panel, rep, pg, t, slug)
                    pg.context.close()
    rep.finish()


if __name__ == "__main__":
    main()
