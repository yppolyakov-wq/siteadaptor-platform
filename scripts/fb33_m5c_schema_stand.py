"""FB-33 стопка 11 (M5c-1…M5c-3): стенд строк схемы «Seitenaufbau» — номер, одна ссылка ⚙ на
строку, «⋯» у каждой строки, ⠿ только на широком экране, «＋ Block» под выбранным и в конце,
окно нового блока (1440/390, de/ru, с JS и без).

Что проверяет (план `docs/fb33-stack11-plan-2026-11-23.md` §2 C0–C2, §8.1–§8.2):
- строки блоков — `<ol>`, номера 1…n по порядку, в каждой строке одна ссылка вне «⋯» (⚙ с
  `data-schema-gear`), нет двух ссылок на один адрес в Tab-обходе строк (стопы = строки + «⋯»),
  повторяющихся id нет, без горизонтальной прокрутки;
- ⠿: на 390 и без JS скрыт; на 1440 с JS виден; сужение окна 1440 → 390 его прячет (matchMedia);
- «⋯» строки (с JS): открывается, Esc закрывает и возвращает фокус на `summary`; «Nach unten» —
  без окна, фокус на «⋯» перенесённой строки, текст «ist jetzt Nummer n» приходит в живую
  область не раньше 200 мс после фокуса; без JS — плашка `data-schema-moved`;
- «＋ Block» под выбранным (без JS — колонка; с JS — после «Fertig», `zuletzt=`): тип «Text» →
  новый блок встаёт сразу за рядом выбранного (номер +1), окно нового блока открыто, сообщение
  о вставке (с JS — описание окна `aria-describedby`), фокус — в окне; «Fertig»/Esc → фокус на ⚙
  нового блока; «＋ Block» в конце → новый блок последним;
- ru: сообщения не по-немецки.

Запуск (демо-киты в стенд-БД, вход `<kit>@example.com` / `demo-12345678`):
    DB_NAME=<стенд-БД> python manage.py runserver 0.0.0.0:8044 --settings=config.settings.stand --noreload
    STAND_URL=http://ptx.siteadaptor.de:8044 \\
        uv run --no-project --with playwright python scripts/fb33_m5c_schema_stand.py <папка> [kit …]
Правки живут только в черновике сессии (каждый проход — новый вход). Итог: «N ✓, M ✗».
"""

from __future__ import annotations

import sys
from urllib.parse import parse_qs, urlparse

import standlib as sl

OUT = sys.argv[1] if len(sys.argv) > 1 else "/tmp/fb33_m5c_shots"
KITS = tuple(sys.argv[2:]) or ("shop", "friseur", "restaurant", "hotel", "retreat")
PORT = urlparse(sl.BASE_URL).port or 80
DEMO_PASSWORD = "demo-12345678"
DLG = "dialog.ui-bwin"
SEITE = "home"
GERMAN = ("eingefügt", "ist jetzt Nummer")

ROWS_JS = """() => {
  const ol = document.querySelector('ol[data-schema-lines]');
  const boxes = [...document.querySelectorAll('[data-schema-rowbox]')];
  const rows = boxes.map(b => {
    const gear = b.querySelector(':scope > a[data-schema-gear]');
    const outside = [...b.querySelectorAll('a')].filter(a => !a.closest('details'));
    const num = b.querySelector(':scope > .schema-num');
    const grip = b.querySelector('.schema-grip');
    const more = b.querySelector(':scope > details[data-schema-more] > summary');
    return {ref: gear ? gear.getAttribute('data-schema-gear') : null,
      links: outside.length, num: num ? +num.textContent : null,
      grip: grip ? grip.getClientRects().length > 0 : null,
      more: more ? more.id : null, h: Math.round(b.getBoundingClientRect().height)};
  });
  const ids = [...document.querySelectorAll('[id]')].map(e => e.id);
  return {ol: !!ol, rows, dupIds: ids.length - new Set(ids).size,
    adds: [...document.querySelectorAll('details[data-schema-add]')].map(d => d.getAttribute('data-schema-add')),
    overflow: document.documentElement.scrollWidth - window.innerWidth};
}"""

INSTRUMENT = """
window.__m5c = {focusAt: null, liveAt: null, live: ''};
document.addEventListener('focusin', e => {
  if (e.target && e.target.id && e.target.id.indexOf('schema-more-') === 0 && window.__m5c.focusAt === null)
    window.__m5c.focusAt = performance.now();
}, true);
document.addEventListener('DOMContentLoaded', () => {
  const live = document.querySelector('[data-schema-live]');
  if (!live) return;
  new MutationObserver(() => {
    if (live.textContent && window.__m5c.liveAt === null) {
      window.__m5c.liveAt = performance.now(); window.__m5c.live = live.textContent;
    }
  }).observe(live, {childList: true, characterData: true, subtree: true});
});
"""


#: кит → slug тенанта (поддомен и вход `<slug>@example.com`), где они расходятся
HOSTS = {"restaurant": "restaurant-demo"}


def base_of(slug):
    return f"http://{HOSTS.get(slug, slug)}.siteadaptor.de:{PORT}"


def aufbau(slug, extra=""):
    return f"{base_of(slug)}/dashboard/site/aufbau/?seite={SEITE}{extra}"


def rows(pg):
    return pg.evaluate(ROWS_JS)


def focus_info(pg):
    return pg.evaluate(
        "() => { const a = document.activeElement; if (!a) return {}; "
        "return {id: a.id, gear: a.getAttribute('data-schema-gear'), tag: a.tagName, "
        "href: a.getAttribute('href'), inDlg: !!a.closest('dialog')}; }"
    )


def tab_walk(pg, first_ref):
    """Tab-обход строк: от ⚙ первой строки до выхода из `<ol>` — стопы и их адреса."""
    pg.focus(f'a[data-schema-gear="{first_ref}"]')
    stops = []
    for _i in range(80):
        info = pg.evaluate(
            "() => { const a = document.activeElement; "
            "const inOl = !!(a && a.closest('ol[data-schema-lines]')); "
            "return {inOl, tag: a ? a.tagName : '', href: a ? a.getAttribute('href') : null, "
            "ref: a ? (a.getAttribute('data-schema-gear') || a.id) : ''}; }"
        )
        if not info["inOl"]:
            break
        stops.append(info)
        pg.keyboard.press("Tab")
    return stops


def check_markup(rep, pg, t, w, js):
    m = rows(pg)
    rep.check(m["ol"], f"{t}: строки блоков — <ol>", code="ol")
    rs = [r for r in m["rows"] if r["ref"]]
    rep.check(len(rs) >= 2, f"{t}: строк ≥ 2 ({len(rs)})", code="rows")
    nums = [r["num"] for r in rs if r["num"] is not None]
    rep.check(nums == list(range(1, len(nums) + 1)), f"{t}: номера 1…n ({nums})", code="nums")
    rep.check(all(r["links"] == 1 for r in rs), f"{t}: в строке одна ссылка", code="one-link")
    rep.check(m["dupIds"] == 0, f"{t}: id без повторов ({m['dupIds']})", code="dup-ids")
    rep.check(m["overflow"] <= 0, f"{t}: без гор. прокрутки ({m['overflow']})", code="overflow")
    rep.check(all(r["h"] >= 44 for r in rs), f"{t}: строки ≥ 44 px", code="row-44")
    grips = [r["grip"] for r in rs if r["grip"] is not None]
    want = js and w >= 768
    rep.check(
        bool(grips) and all(g == want for g in grips),
        f"{t}: ⠿ {'виден' if want else 'скрыт'}",
        code="grip",
    )
    return rs


def check_tab(rep, pg, t, rs):
    stops = tab_walk(pg, rs[0]["ref"])
    hrefs = [s["href"] for s in stops if s["href"]]
    rep.check(
        len(hrefs) == len(set(hrefs)), f"{t}: Tab — нет двух ссылок на один адрес", code="tab-dup"
    )
    gears = [s for s in stops if s["tag"] == "A"]
    mores = [s for s in stops if s["tag"] == "SUMMARY"]
    want_more = sum(1 for r in rs if r["more"])
    rep.check(
        len(gears) == len(rs) and len(mores) == want_more,
        f"{t}: Tab-стопы = строки ({len(gears)}/{len(rs)}) + «⋯» ({len(mores)}/{want_more})",
        code="tab-stops",
    )


def check_more_js(rep, pg, t, rs, lang):
    """«⋯» строки: Esc, затем «Nach unten» — фокус на «⋯» и номер в живой области ≥ 200 мс."""
    row = next((r for r in rs[:-1] if r["more"]), None)
    if row is None:
        rep.note(f"{t}: нет строки с «⋯» — проверка пропущена")
        return
    summ = f"#{row['more']}"
    press(pg, summ)
    opened = pg.evaluate(f"() => document.querySelector('{summ}').parentElement.open")
    pg.keyboard.press("Escape")
    st = pg.evaluate(
        f"() => ({{open: document.querySelector('{summ}').parentElement.open, "
        f"focus: document.activeElement === document.querySelector('{summ}')}})"
    )
    rep.check(
        opened and not st["open"] and st["focus"],
        f"{t}: «⋯» Esc закрывает, фокус на ⋯",
        code="more-esc",
    )
    # ревью a11y (HIGH): открытое меню — над «⋯»/⠿ следующих строк (щелчок по последнему пункту
    # попадает в него, а не в строку ниже)
    press(pg, summ)
    hit = pg.evaluate(
        f"""() => {{ const d = document.querySelector('{summ}').parentElement;
        const items = d.querySelectorAll(':scope > div :is(button, a)');
        const last = items[items.length - 1]; if (!last) return null;
        const r = last.getBoundingClientRect();
        const el = document.elementFromPoint(r.left + r.width / 2, r.top + r.height / 2);
        return !!el && (el === last || last.contains(el)); }}"""
    )
    rep.check(hit is True, f"{t}: открытое «⋯» не перекрыто соседними строками", code="more-z")
    pg.keyboard.press("Escape")
    # ревью silent (HIGH): без текста сервера живая область молчит (не «Übernommen.»)
    pg.evaluate("() => { document.querySelector('[data-schema-live]').textContent = ''; }")
    pg.evaluate("(r) => window.aufbauMoved(r, '')", row["ref"])
    pg.wait_for_timeout(450)
    quiet = pg.evaluate("() => document.querySelector('[data-schema-live]').textContent")
    rep.check(quiet == "", f"{t}: отказ не озвучен успехом ({quiet!r})", code="moved-quiet")
    down = pg.query_selector(f"{summ} ~ div button[value=down]")
    if down is None:
        rep.note(f"{t}: у строки нет «Nach unten»")
        return
    press(pg, summ)
    with pg.expect_navigation():
        press(pg, f"{summ} ~ div button[value=down]")
    sl.settle(pg, True)
    pg.wait_for_timeout(700)
    q = parse_qs(urlparse(pg.url).query)
    rep.check(
        "block" not in q and not pg.query_selector(f"{DLG}[open]"),
        f"{t}: окно не открылось",
        code="more-nowin",
    )
    fi = focus_info(pg)
    rep.check(
        fi.get("id") == row["more"], f"{t}: фокус на «⋯» перенесённой ({fi})", code="more-focus"
    )
    timing = pg.evaluate("() => window.__m5c")
    gap = (timing["liveAt"] or 0) - (timing["focusAt"] or 0)
    rep.check(
        timing["liveAt"] is not None and timing["focusAt"] is not None and gap >= 200,
        f"{t}: номер в живой области через {round(gap)} мс после фокуса",
        code="more-live",
    )
    if lang == "ru":
        rep.check(
            not any(g in timing["live"] for g in GERMAN), f"{t}: текст по-русски", code="ru-live"
        )


def check_more_nojs(rep, pg, t, rs, lang):
    row = next((r for r in rs[:-1] if r["more"]), None)
    if row is None or pg.query_selector(f"#{row['more']} ~ div button[value=down]") is None:
        rep.note(f"{t}: нет «Nach unten» — проверка пропущена")
        return
    press(pg, f"#{row['more']}")
    with pg.expect_navigation():
        press(pg, f"#{row['more']} ~ div button[value=down]")
    said = pg.query_selector("[data-schema-moved]")
    text = said.inner_text() if said else ""
    rep.check(
        bool(text), f"{t}: без JS — плашка «ist jetzt Nummer» ({text[:50]})", code="moved-plaque"
    )
    rep.check(
        urlparse(pg.url).fragment == row["more"], f"{t}: якорь на «⋯» строки", code="moved-frag"
    )
    if lang == "ru":
        rep.check(not any(g in text for g in GERMAN), f"{t}: плашка по-русски", code="ru-moved")


def insert(rep, pg, t, js, lang, rs, where):
    """«＋ Block» (`where`: sel | end) → тип «Text»: позиция, окно нового блока, фокус, «Fertig»."""
    target = rs[1]
    if where == "sel":
        if js:
            pg.goto(aufbau(slug_of(pg), f"&zuletzt={target['ref']}"))
        else:
            pg.goto(aufbau(slug_of(pg), f"&block={target['ref']}"))
        sl.settle(pg, js)
    before = rows(pg)["rows"]
    if where not in rows(pg)["adds"]:
        rep.check(False, f"{t}: «＋ Block» {where} есть", code=f"add-{where}")
        return
    # клавиатурой (как владелец с клавиатуры; без JS панель теперь под схемой — C4)
    press(pg, f"#schema-add-{where}")
    with pg.expect_navigation():
        press(pg, f'details[data-schema-add="{where}"] button[name=type][value=text]')
    if js:
        pg.wait_for_selector(f"{DLG}[open]", timeout=10000)
        sl.settle(pg, True)
        pg.wait_for_timeout(400)
    else:
        pg.wait_for_load_state()
    new = parse_qs(urlparse(pg.url).query).get("block", [""])[0]
    rep.check(bool(new), f"{t}: {where}: адрес нового блока", code=f"add-{where}-url")
    after = rows(pg)["rows"]
    order = [r["ref"] for r in after if r["ref"]]
    if where == "sel":
        line_last = max(i for i, r in enumerate(order) if r == target["ref"])
        ok = new in order and order.index(new) == line_last + 1
    else:
        ok = bool(order) and order[-1] == new
    rep.check(
        ok,
        f"{t}: {where}: новый блок на месте ({len(before)}→{len(after)})",
        code=f"add-{where}-pos",
    )
    if js:
        st = pg.evaluate(
            "() => { const d = document.querySelector('dialog.ui-bwin[open]'); if (!d) return {};"
            "const id = d.getAttribute('aria-describedby'); const s = id && document.getElementById(id);"
            "const a = document.activeElement;"
            "return {desc: s ? s.textContent : '', inDlg: !!(a && d.contains(a)), tag: a ? a.tagName : '',"
            "title: (document.getElementById('schema-panel-title') || {}).textContent || ''}; }"
        )
        rep.check(
            bool(st.get("desc")),
            f"{t}: {where}: описание окна — сообщение о вставке",
            code="add-desc",
        )
        rep.check(
            st.get("inDlg") and st.get("tag") in ("INPUT", "SELECT", "TEXTAREA", "H2", "BUTTON"),
            f"{t}: {where}: фокус в окне ({st.get('tag')})",
            code="add-focus",
        )
        text = st.get("desc", "")
        pg.keyboard.press("Escape")
        pg.wait_for_url(lambda u: "block=" not in u, timeout=20000)
        pg.wait_for_load_state()
        sl.settle(pg, True)
        try:
            pg.wait_for_function(
                "(r) => document.activeElement && document.activeElement.getAttribute('data-schema-gear') === r",
                arg=new,
                timeout=3000,
            )
            back = True
        except Exception:  # noqa: BLE001 — стенд: итог проверки, не сбой
            back = False
        rep.check(
            back,
            f"{t}: {where}: Esc/«Fertig» → фокус на ⚙ нового ({focus_info(pg)})",
            code="add-back",
        )
        if where == "sel":
            rep.check(
                "sel" in rows(pg)["adds"],
                f"{t}: «＋» под блоком остаётся после «Fertig»",
                code="add-stays",
            )
    else:
        said = pg.query_selector("[data-schema-inserted]")
        text = said.inner_text() if said else ""
        rep.check(
            bool(text),
            f"{t}: {where}: без JS — сообщение в колонке нового блока",
            code="add-plaque",
        )
    if lang == "ru":
        rep.check(
            not any(g in text for g in GERMAN),
            f"{t}: {where}: сообщение по-русски ({text[:40]})",
            code="ru-add",
        )


def press(pg, selector):
    pg.focus(selector)
    pg.keyboard.press("Enter")


def guarded(rep, t, fn, *args):
    try:
        fn(*args)
    except Exception as exc:  # noqa: BLE001 — стенд: сбой сценария — ✗ с причиной, обход идёт дальше
        rep.check(
            False, f"{t}: {fn.__name__} — сбой {type(exc).__name__}: {str(exc)[:160]}", code="crash"
        )


def slug_of(pg):
    return urlparse(pg.url).hostname.split(".")[0]


def main():
    rep = sl.Report()
    with sl.launch() as browser:
        for slug in KITS:
            for w, h, lang, js in sl.matrix():
                pg = sl.open_page(browser, w, h, js=js, lang=lang)
                if js:
                    pg.add_init_script(INSTRUMENT)
                t = f"{slug} {w} {lang} {'js' if js else 'nojs'}"
                if not rep.check(
                    sl.login(
                        pg, base_of(slug), f"{HOSTS.get(slug, slug)}@example.com", DEMO_PASSWORD
                    ),
                    f"{t}: вход",
                ):
                    pg.context.close()
                    continue
                pg.goto(aufbau(slug))
                sl.settle(pg, js, rep)
                rs = check_markup(rep, pg, t, w, js)
                sl.shot(pg, OUT, f"m5c_{slug}_{w}_{lang}_{'js' if js else 'nojs'}")
                if len(rs) >= 2:
                    if js:
                        guarded(rep, t, check_tab, rep, pg, t, rs)
                        if w >= 768:
                            pg.set_viewport_size({"width": 390, "height": 844})
                            pg.wait_for_timeout(200)
                            narrow = [r["grip"] for r in rows(pg)["rows"] if r["grip"] is not None]
                            rep.check(
                                narrow and not any(narrow),
                                f"{t}: сужение → ⠿ скрыт",
                                code="grip-narrow",
                            )
                            pg.set_viewport_size({"width": w, "height": h})
                            pg.wait_for_timeout(200)
                        guarded(rep, t, check_more_js, rep, pg, t, rs, lang)
                    else:
                        guarded(rep, t, check_more_nojs, rep, pg, t, rs, lang)
                    pg.goto(aufbau(slug))
                    sl.settle(pg, js)
                    rs = rows(pg)["rows"]
                    guarded(rep, t, insert, rep, pg, t, js, lang, rs, "sel")
                    pg.goto(aufbau(slug))
                    sl.settle(pg, js)
                    guarded(rep, t, insert, rep, pg, t, js, lang, rows(pg)["rows"], "end")
                rep.check(
                    not pg.js_errors, f"{t}: без ошибок JS ({pg.js_errors[:2]})", code="js-errors"
                )
                pg.context.close()
    rep.finish()


if __name__ == "__main__":
    main()
