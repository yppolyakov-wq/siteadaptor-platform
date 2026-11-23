"""FB-33 стопка 10 (M5b-2): стенд «★-строка страницы, метка заголовка, главный список, Студия»
(1440/390, de/ru, с JS и без; телефон 390×844, 844×390, 320×700).

Что проверяет (по плану `docs/fb33-stack10-plan-2026-11-22.md` §8.2 a11y и §8.6):
- ★-строка («Seitentitel und Seite» / «Einstellungen der Seite») — первой после «Kopfzeile & Menü»,
  ≥ 44 px, в имени нет «★», после названия — «feste Position»; клик → окно на вкладке «Seite»:
  `fieldset/legend` «Überschrift der Seite» (поля заголовка у HEAD_HOSTS), затем `h4`
  «Einstellungen dieser Seitenart»;
- метка «Überschrift der Seite · in ★ bearbeiten»: ≥ 44 px, подчёркнута, не строка (нет
  `data-schema-block`/перетаскивания), клик → окно ★ на «Seite», после закрытия фокус на ★-строке;
- старая ссылка `?block=__title` → 302 на ★-строку, вкладка «Seite» (с JS и без);
- с JS: правка заголовка уходит по `change` без «Übernehmen», «Fertig» — в черновик, «Abbrechen»
  откатывает; Esc и «Fertig» → фокус на ★-строке; бросок над меткой и над ★ запроса не шлёт;
- главный список: имя по содержимому + «Hauptliste», в окне плашка и фраза «нельзя скрыть»;
- без JS: на «Seite» Enter в заголовке сохраняет только форму заголовка;
- телефон: нет горизонтальной прокрутки, «Fertig» кликабелен, активное поле не под нижним краем;
- Студия: строка главного списка с плашкой «Hauptliste», ссылка «Wie die Liste aussieht: in ★ …»
  (при несохранённой правке — `confirm`, без правок — окно ★ на «Seite»);
- ru: нет немецких подписей новой работы.

Запуск (тенант ptx — `scripts/text_pages_stand.py --setup --jobs`; демо-киты friseur и shop — в
стенд-БД копией `seed_demo_tenants`, вход `<kit>@example.com` / `demo-12345678`):
    DB_NAME=<стенд-БД> python manage.py runserver 0.0.0.0:8044 --settings=config.settings.stand --noreload
    STAND_URL=http://ptx.siteadaptor.de:8044 \\
        uv run --no-project --with playwright python scripts/fb33_m5b2_page_row_stand.py <папка>
Правки живут только в черновике сессии (ничего не сохраняется в схему). Итог: «N ✓, M ✗».
Не входит в CI (там нет браузера). Ссылка на ★-строку берётся из разметки (правило — в
`site_schema.page_row_ref`, литерал строки в стендах запрещён замком).
"""

from __future__ import annotations

import sys
from urllib.parse import urlparse

import standlib as sl

OUT = sys.argv[1] if len(sys.argv) > 1 else "/tmp/fb33_m5b2_shots"
PORT = urlparse(sl.BASE_URL).port or 80
DEMO_PASSWORD = "demo-12345678"
DLG = "dialog.ui-bwin"
OLD_TITLE_REF = "__title"  # снятая строка: адрес держим, чтобы доказать 302

#: подписи новой работы: de → ru (по `locale/ru/LC_MESSAGES/django.po`)
LAB = {
    "de": {
        "title": "Seitentitel und Seite",
        "page": "Einstellungen der Seite",
        "legend": "Überschrift der Seite",
        "kind": "Einstellungen dieser Seitenart",
        "fixed": "feste Position",
        "main": "Hauptliste",
        "main_note": "Die Hauptliste lässt sich nicht ausblenden oder entfernen.",
        "edit": "bearbeiten",
        "list_link": "Wie die Liste aussieht",
    },
    "ru": {
        "title": "Заголовок и страница",
        "page": "Настройки страницы",
        "legend": "Заголовок на странице",
        "kind": "Настройки этого типа страниц",
        "fixed": "закреплённое место",
        "main": "Основной список",
        "main_note": "Основной список нельзя скрыть или удалить.",
        "edit": "изменить",
        "list_link": "Как выглядит список",
    },
}
GERMAN_IN_RU = ("Seitentitel und Seite", "Überschrift der Seite", "Hauptliste", "feste Position")

#: slug демо-кита → (почта, пароль); у ptx — учётка стенда
HEAD = "title"  # у страницы поля заголовка (HEAD_HOSTS): ★ называется «Seitentitel und Seite»
TARGETS = (
    # slug, seite, имя ★, метка заголовка есть, имя главного списка de/ru
    ("friseur", "services", HEAD, True, ("Leistungen", "Услуги")),
    ("shop", "catalog", "page", False, ("Produkte", "Товары")),
    ("shop", "category", "page", False, ("Produkte", "Товары")),
    ("shop", "promos", HEAD, True, ("Aktionen", "Акции")),
    ("ptx", "anfrage", HEAD, None, None),
    ("shop", "product", "page", False, None),
)

MARKUP_JS = """() => {
  const acc = el => { const c = el.cloneNode(true);
    c.querySelectorAll('[aria-hidden=true]').forEach(n => n.remove());
    return c.textContent.replace(/\\s+/g, ' ').trim(); };
  const ul = document.querySelector('[data-schema-blocks]');
  const lis = ul ? [...ul.children] : [];
  const star = lis[1] ? lis[1].querySelector(':scope > a[data-schema-block]') : null;
  const out = {top: lis[0] ? lis[0].innerText.replace(/\\s+/g, ' ') : '', hasStar: !!star};
  if (star) {
    const r = star.getBoundingClientRect();
    out.ref = star.getAttribute('data-schema-block');
    out.h = Math.round(r.height);
    out.visible = star.innerText.replace(/\\s+/g, ' ').trim();
    out.name = acc(star);
    out.pinnedAttr = !!star.closest('[data-schema-pinned],[data-schema-drag]');
    out.grip = !!star.querySelector('.schema-grip');
    out.starAria = !![...star.querySelectorAll('span[aria-hidden=true]')].find(s => s.textContent.includes('★'));
  }
  const hints = [...document.querySelectorAll('[data-schema-title-hint]')];
  out.hints = hints.length;
  if (hints[0]) {
    const h = hints[0], a = h.querySelector('a');
    out.hint = {
      lih: Math.round(h.getBoundingClientRect().height),
      ah: Math.round(a.getBoundingClientRect().height),
      deco: getComputedStyle(a).textDecorationLine,
      name: acc(a), visible: a.innerText.replace(/\\s+/g, ' ').trim(), text: acc(h),
      href: a.getAttribute('href'),
      // FB-33 M5c-2: метка — абзацем в пункте ряда `<ol>` (вне `ul[data-schema-row]`)
      direct: h.parentElement === ul || !!h.closest('ol[data-schema-lines] > li'),
      inRow: !!h.closest('[data-schema-row]'),
      movable: !!h.closest('[data-schema-drag],[data-schema-pinned]') || !!h.querySelector('[data-schema-block]'),
      after: lis.indexOf(h),
    };
  }
  // FB-33 M5c-2: строка блока — `data-schema-rowbox` с одной ссылкой ⚙ (подпись — текст строки)
  out.rows = [...document.querySelectorAll('a[data-schema-block]')].map(a => {
    const box = a.closest('[data-schema-rowbox]') || a;
    return {ref: a.getAttribute('data-schema-block'), text: box.innerText.replace(/\\s+/g, ' ').trim()}; });
  out.overflow = document.documentElement.scrollWidth - window.innerWidth;
  return out; }"""

WINDOW_JS = """() => {
  const root = document.querySelector('dialog.ui-bwin[open]') || document.querySelector('[data-site-schema]');
  const txt = e => e.textContent.replace(/\\s+/g, ' ').trim();
  const legends = [...root.querySelectorAll('fieldset > legend')].map(txt);
  const lg = [...root.querySelectorAll('fieldset > legend')].find(l => txt(l) === arguments_[0]);
  const h4 = [...root.querySelectorAll('h4')].find(h => txt(h) === arguments_[1]);
  const after = lg && h4 ? !!(lg.compareDocumentPosition(h4) & Node.DOCUMENT_POSITION_FOLLOWING) : null;
  const title = root.querySelector('[name=f_title]');
  const ids = [...root.querySelectorAll('[id]')].map(e => e.id);
  const tabs = root.querySelectorAll('[data-window-tabs] li').length;
  const active = root.querySelector('[data-window-tab]:not([hidden])');
  const h5 = [...root.querySelectorAll('h5')].length;
  return {legends, legend: !!lg, h4: !!h4, order: after, title: !!title,
    intro: !!root.querySelector('[name=f_intro]'), align: !!root.querySelector('[name=f_align]'),
    tabs, active: active ? active.getAttribute('data-window-tab') : null,
    h4text: h4 ? txt(h4) : null, dupIds: ids.length - new Set(ids).size, h5,
    h4Empty: h4 ? !(h4.nextElementSibling || h4.parentElement.nextElementSibling) : null}; }""".replace(
    "arguments_", "args"
)


def base_of(slug):
    return f"http://{slug}.siteadaptor.de:{PORT}"


def creds(slug):
    return (sl.EMAIL, sl.PASSWORD) if slug == "ptx" else (f"{slug}@example.com", DEMO_PASSWORD)


def aufbau(slug, seite, extra=""):
    return f"{base_of(slug)}/dashboard/site/aufbau/?seite={seite}{extra}"


def focus_ref(pg):
    return pg.evaluate(
        "() => { const a = document.activeElement; "
        "return a ? (a.getAttribute('data-schema-block') || a.tagName) : ''; }"
    )


def open_star(pg, ref, js):
    """Клик по ★-строке: с JS — окно dialog, без — панель той же страницей."""
    pg.click(f'[data-schema-blocks] a[data-schema-block="{ref}"]')
    if js:
        pg.wait_for_selector(f"{DLG}[open]", timeout=10000)
        sl.settle(pg, True)
    else:
        pg.wait_for_load_state()


def after_close_focus(pg, ref):
    pg.wait_for_url(lambda u: "block=" not in u, timeout=20000)
    pg.wait_for_load_state()
    sl.settle(pg, True)
    pg.wait_for_function(
        "(r) => (document.activeElement && document.activeElement.getAttribute('data-schema-block')) === r",
        arg=ref,
        timeout=3000,
    )


def run_markup(rep, pg, tag, lang, js, slug, seite, star_kind, hint, main):
    lab = LAB[lang]
    pg.goto(aufbau(slug, seite))
    sl.settle(pg, js, rep)
    m = pg.evaluate(MARKUP_JS)
    t = f"{tag} {slug}/{seite}"
    rep.check(
        m["hasStar"],
        f"{t}: ★-строка — вторым пунктом списка, после «Kopfzeile & Menü»",
        code="star-first",
    )
    if not m["hasStar"]:
        return None
    want = lab[star_kind]
    rep.check(m["h"] >= 44, f"{t}: ★-строка ≥ 44 px ({m['h']})", code="star-44")
    rep.check(
        "★" in m["visible"] and m["starAria"], f"{t}: ★ виден и скрыт от чтения", code="star-aria"
    )
    rep.check(
        "★" not in m["name"] and m["name"].startswith(want),
        f"{t}: имя без «★» — «{want}» ({m['name'][:60]!r})",
        code="star-name",
    )
    rep.check(
        lab["fixed"] in m["name"] and m["name"].index(want) < m["name"].index(lab["fixed"]),
        f"{t}: после названия — «{lab['fixed']}»",
        code="star-fixed",
    )
    rep.check(
        not m["pinnedAttr"] and not m["grip"],
        f"{t}: у ★-строки нет ручки и перетаскивания",
        code="star-static",
    )
    if lang == "ru":
        bad = [
            g for g in GERMAN_IN_RU if g in " ".join(r["text"] for r in m["rows"]) or g in m["name"]
        ]
        rep.check(not bad, f"{t}: ru — немецких подписей нет ({bad})", code="ru-german")
    if hint is True:
        rep.check(
            m["hints"] == 1 and bool(m.get("hint")),
            f"{t}: метка заголовка — одна ({m['hints']})",
            code="hint-one",
        )
    elif hint is False:
        rep.check(m["hints"] == 0, f"{t}: метки заголовка нет ({m['hints']})", code="hint-none")
    elif m["hints"] == 0:
        rep.note(
            f"{slug}/{seite}: метки заголовка нет (блок «Fotos der Seite» не включён) — клик по метке не проверен"
        )
    h = m.get("hint")
    if h:
        rep.check(h["ah"] >= 44, f"{t}: ссылка метки ≥ 44 px ({h['ah']})", code="hint-44")
        rep.check(
            "underline" in h["deco"],
            f"{t}: ссылка метки подчёркнута ({h['deco']})",
            code="hint-underline",
        )
        rep.check(
            h["direct"] and not h["inRow"] and not h["movable"],
            f"{t}: метка — не строка схемы (вне рядов, не двигается)",
            code="hint-not-row",
        )
        rep.check(
            lab["legend"] in h["text"] and lab["edit"] in h["name"] and want in h["name"],
            f"{t}: имя ссылки содержит видимое «{lab['edit']}» и «{want}» ({h['name'][:70]!r})",
            code="hint-name",
        )
        rep.check(
            f"block={m['ref']}" in h["href"] and "tab=seite" in h["href"],
            f"{t}: ссылка метки — ★, вкладка «Seite»",
            code="hint-href",
        )
        if lang == "ru":
            rep.check(
                not any(g in h["text"] for g in GERMAN_IN_RU),
                f"{t}: ru — метка по-русски ({h['text'][:60]!r})",
                code="ru-german",
            )
    if main:
        name = main[0] if lang == "de" else main[1]
        row = next((r for r in m["rows"] if name in r["text"] and lab["main"] in r["text"]), None)
        rep.check(
            row is not None,
            f"{t}: главный список — «{name}» + «{lab['main']}» ({[r['text'][:30] for r in m['rows'] if lab['main'] in r['text']]})",
            code="main-name",
        )
    rep.check(
        m["overflow"] <= 0, f"{t}: без горизонтальной прокрутки ({m['overflow']})", code="overflow"
    )
    return m


def run_window(rep, pg, tag, lang, js, slug, seite, star_kind, ref, main):
    lab = LAB[lang]
    t = f"{tag} {slug}/{seite}"
    open_star(pg, ref, js)
    rep.check(f"block={ref}" in pg.url, f"{t}: адрес окна — ★-строка", code="win-url")
    w = pg.evaluate(
        "([a, b]) => (" + WINDOW_JS.replace("args", "[a, b]") + ")()", [lab["legend"], lab["kind"]]
    )
    head = star_kind == HEAD
    if head:
        rep.check(w["h4"], f"{t}: «{lab['kind']}» — заголовок h4", code="win-h4")
        rep.check(
            w["legend"],
            f"{t}: fieldset/legend «{lab['legend']}» ({w['legends']})",
            code="win-legend",
        )
        rep.check(
            w["title"] and w["intro"] and w["align"],
            f"{t}: поля Seitentitel/Einleitung/Ausrichtung",
            code="win-fields",
        )
        rep.check(
            w["order"] is True,
            f"{t}: порядок DOM — заголовок страницы, затем «{lab['kind']}»",
            code="win-order",
        )
    else:
        rep.check(
            not w["legend"] and not w["title"],
            f"{t}: у страницы без HEAD_HOSTS полей заголовка нет",
            code="win-nohead",
        )
    rep.check(
        w["active"] == "seite", f"{t}: открыта вкладка «Seite» ({w['active']})", code="win-tab"
    )
    rep.check(w["dupIds"] == 0, f"{t}: в окне нет дублей id ({w['dupIds']})", code="win-dupids")
    if head and w["h4Empty"]:
        rep.check(
            False, f"{t}: заголовок «{lab['kind']}» без содержимого под ним", code="win-h4-empty"
        )
    sl.shot(pg, OUT, f"win_{slug}_{seite}_{tag.replace(' ', '_')}")
    if lang == "ru":
        body = pg.evaluate(
            "() => (document.querySelector('dialog.ui-bwin[open]') || document.querySelector('[data-site-schema]')).innerText"
        )
        bad = [g for g in GERMAN_IN_RU if g in body]
        rep.check(not bad, f"{t}: ru — окно ★ без немецких подписей ({bad})", code="ru-german")
    return w


def run_main_window(rep, pg, tag, lang, js, slug, seite, ref):
    lab = LAB[lang]
    t = f"{tag} {slug}/{seite}"
    pg.goto(aufbau(slug, seite, f"&block={ref}"))
    sl.settle(pg, js, rep)
    note = pg.evaluate(
        "() => { const root = document.querySelector('dialog.ui-bwin[open]') || document;"
        "const n = root.querySelector('[data-schema-main-note]');"
        "return n ? {text: n.textContent.replace(/\\s+/g, ' ').trim(), badge: !!n.querySelector('.ui-badge')} : null; }"
    )
    rep.check(
        note is not None, f"{t}: окно главного списка — плашка «{lab['main']}»", code="main-note"
    )
    if note:
        rep.check(
            lab["main"] in note["text"] and lab["main_note"] in note["text"],
            f"{t}: фраза «{lab['main_note']}»",
            code="main-phrase",
        )
        if lang == "ru":
            rep.check(
                "Hauptliste" not in note["text"], f"{t}: ru — плашка по-русски", code="ru-german"
            )
    links = pg.evaluate(
        "() => [...document.querySelectorAll('[data-schema-page-link]')].map(a => ({"
        "h: Math.round(a.getBoundingClientRect().height), href: a.getAttribute('href'), text: a.innerText.replace(/\\s+/g, ' ')}))"
    )
    # окно списка без своего вида — ссылка в ★; у списка со своим видом ссылки нет
    for ln in links:
        rep.check(
            ln["h"] >= 44 and lab["list_link"] in ln["text"],
            f"{t}: ссылка «{lab['list_link']}: в ★» ≥ 44 px ({ln['h']})",
            code="list-link",
        )


def main_ref_of(m):
    return next((r["ref"] for r in m["rows"] if r["ref"] == "main"), None)


def raw_get(pg, slug, path):
    """GET без перехода по редиректу, с сессией страницы: браузерное правило `*.siteadaptor.de →
    127.0.0.1` до `pg.request` не доходит, поэтому — напрямую на 127.0.0.1 с заголовком Host."""
    import http.client

    cookie = "; ".join(f"{c['name']}={c['value']}" for c in pg.context.cookies(base_of(slug)))
    conn = http.client.HTTPConnection("127.0.0.1", PORT, timeout=20)
    conn.request("GET", path, headers={"Host": f"{slug}.{sl.BASE_DOMAIN}:{PORT}", "Cookie": cookie})
    resp = conn.getresponse()
    status, loc = resp.status, resp.getheader("Location") or ""
    conn.close()
    return status, loc


def old_link(rep, pg, tag, js, slug, seite, ref, lang):
    t = f"{tag} {slug}/{seite}"
    status, loc = raw_get(pg, slug, f"/dashboard/site/aufbau/?seite={seite}&block={OLD_TITLE_REF}")
    rep.check(
        status == 302 and f"block={ref}" in loc and "tab=seite" in loc,
        f"{t}: старая ссылка → 302 на ★, «Seite» ({status} {loc[-60:]})",
        code="old-302",
    )
    pg.goto(aufbau(slug, seite, f"&block={OLD_TITLE_REF}"))
    sl.settle(pg, js, rep)
    if js:
        opened = pg.locator(f"{DLG}[open]").count() == 1
    else:
        title = pg.locator("#schema-panel-title")
        opened = title.count() == 1 and any(
            v in title.inner_text() for v in (LAB[lang]["title"], LAB[lang]["page"])
        )
    rep.check(
        opened and f"block={ref}" in pg.url,
        f"{t}: после редиректа окно ★ открыто ({pg.url[-60:]})",
        code="old-open",
    )
    if js and opened:
        pg.keyboard.press("Escape")
        try:
            after_close_focus(pg, ref)
            got = True
        except Exception:  # noqa: BLE001
            got = False
        rep.check(
            got,
            f"{t}: окно по старой ссылке закрыто → фокус на ★-строке ({focus_ref(pg)})",
            code="focus-redirect",
        )


def js_behaviour(rep, pg, tag, lang, slug, seite, ref, hint, head):
    """Только с JS: правка по change, «Fertig»/«Abbrechen», фокус, метка, бросок."""
    t = f"{tag} {slug}/{seite}"
    star_sel = f'[data-schema-blocks] > :is(li, div):has(> a[data-schema-block="{ref}"])'
    # Esc → фокус на ★ (окно открыто адресом)
    pg.goto(aufbau(slug, seite, f"&block={ref}"))
    sl.settle(pg, True, rep)
    pg.wait_for_selector(f"{DLG}[open]", timeout=10000)
    pg.keyboard.press("Escape")
    try:
        after_close_focus(pg, ref)
        got = True
    except Exception:  # noqa: BLE001 — таймаут Playwright = фокус не на ★
        got = False
    rep.check(got, f"{t}: Esc → фокус на ★-строке ({focus_ref(pg)})", code="focus-esc")
    # окно открыто кликом по ★ в списке (адрес с #schema-panel): как у любой строки (база 54c5961 —
    # так же), фокус остаётся на панели, не на строке — наблюдение, не ✗
    pg.goto(aufbau(slug, seite))
    sl.settle(pg, True, rep)
    open_star(pg, ref, True)
    pg.keyboard.press("Escape")
    pg.wait_for_url(lambda u: "block=" not in u, timeout=20000)
    pg.wait_for_load_state()
    pg.wait_for_timeout(500)
    if focus_ref(pg) != ref:
        rep.note(
            f"клик по ★ в списке → Esc: фокус на {focus_ref(pg)!r}, не на ★-строке (адрес закрытия с #schema-panel; у обычных строк на базе так же)"
        )
    if head:
        # правка по change, «Fertig» → черновик, «Abbrechen» откатывает
        pg.goto(aufbau(slug, seite, f"&block={ref}&tab=seite"))
        sl.settle(pg, True, rep)
        field = pg.locator(f"{DLG} [name=f_title]")
        before = field.input_value()
        applies = pg.locator(f"{DLG} button[name=op][value=update]")
        vis = [a.is_visible() for a in applies.all()]
        if any(vis):
            rep.note(
                "с JS у формы заголовка «Übernehmen» остаётся видимой (на базе 54c5961 так же; формы других окон её прячут) — не ✗"
            )
        field.fill("E2E Titel A")
        with pg.expect_request(lambda r: r.method == "POST", timeout=8000) as req:
            pg.keyboard.press("Tab")
        rep.check(
            req.value is not None, f"{t}: правка заголовка ушла по change", code="title-change"
        )
        pg.wait_for_function(
            "!+document.documentElement.getAttribute('data-schema-busy')", timeout=15000
        )
        pg.click(f"{DLG} [data-window-actions] button[value=window_done]")
        try:
            after_close_focus(pg, ref)
            got = True
        except Exception:  # noqa: BLE001
            got = False
        rep.check(got, f"{t}: «Fertig» → фокус на ★-строке ({focus_ref(pg)})", code="focus-done")
        rep.check(
            pg.locator("[data-schema-draft-note]").count() == 1,
            f"{t}: после «Fertig» — полоса черновика",
            code="draft-note",
        )
        pg.goto(aufbau(slug, seite, f"&block={ref}&tab=seite"))
        sl.settle(pg, True, rep)
        rep.check(
            pg.locator(f"{DLG} [name=f_title]").input_value() == "E2E Titel A",
            f"{t}: «Fertig» — заголовок в черновике",
            code="title-draft",
        )
        pg.locator(f"{DLG} [name=f_title]").fill("E2E Titel B")
        with pg.expect_request(lambda r: r.method == "POST", timeout=8000):
            pg.keyboard.press("Tab")
        pg.wait_for_function(
            "!+document.documentElement.getAttribute('data-schema-busy')", timeout=15000
        )
        pg.click(f"{DLG} [data-window-actions] button[value=revert]")
        pg.wait_for_timeout(1500)
        pg.goto(aufbau(slug, seite, f"&block={ref}&tab=seite"))
        sl.settle(pg, True, rep)
        back = pg.locator(f"{DLG} [name=f_title]").input_value()
        rep.check(
            back == "E2E Titel A",
            f"{t}: «Abbrechen» откатил правку B к A ({back!r}; до правок было {before!r})",
            code="title-revert",
        )
    if hint:
        pg.goto(aufbau(slug, seite))
        sl.settle(pg, True, rep)
        pg.click("[data-schema-title-hint] a")
        pg.wait_for_selector(f"{DLG}[open]", timeout=10000)
        sl.settle(pg, True)
        rep.check(
            f"block={ref}" in pg.url
            and "tab=seite" in pg.url
            and pg.locator(f"{DLG} [name=f_title]").count() == 1,
            f"{t}: метка → окно ★ на «Seite»",
            code="hint-click",
        )
        pg.keyboard.press("Escape")
        try:
            after_close_focus(pg, ref)
            got = True
        except Exception:  # noqa: BLE001
            got = False
        rep.check(
            got,
            f"{t}: окно из метки закрыто → фокус на ★-строке ({focus_ref(pg)})",
            code="focus-hint",
        )
    # бросок над меткой и над ★ — не цель
    pg.goto(aufbau(slug, seite))
    sl.settle(pg, True, rep)
    movable = pg.locator("[data-schema-drag]")
    if movable.count() < 2:
        rep.note(f"{slug}/{seite}: двигаемых блоков < 2 — бросок не проверен")
        return
    src = movable.first
    order0 = pg.evaluate(
        "() => [...document.querySelectorAll('[data-schema-block]')].map(a => a.getAttribute('data-schema-block')).join()"
    )
    posts = []
    pg.on("request", lambda r: posts.append(r.url) if r.method == "POST" else None)
    targets = [("★-строкой", star_sel)]
    if hint:
        targets.append(("меткой", "[data-schema-title-hint]"))
    for what, sel in targets:
        n0 = len(posts)
        src.drag_to(pg.locator(sel).first)
        pg.wait_for_timeout(600)
        busy = pg.evaluate("document.documentElement.getAttribute('data-schema-busy')")
        order1 = pg.evaluate(
            "() => [...document.querySelectorAll('[data-schema-block]')].map(a => a.getAttribute('data-schema-block')).join()"
        )
        rep.check(
            len(posts) == n0 and busy in (None, "0") and order1 == order0,
            f"{t}: бросок над {what} — запроса нет, busy={busy}, порядок прежний",
            code="drop-none",
        )
    # контроль: бросок на соседний двигаемый блок запрос шлёт (иначе проверка выше ничего не стоит)
    n0 = len(posts)
    # на телефоне с черновиком низ экрана занят полосой черновика (M5c-5) — цель в середину
    movable.nth(1).evaluate("e => e.scrollIntoView({block: 'center'})")
    movable.first.drag_to(movable.nth(1))
    pg.wait_for_timeout(1200)
    rep.check(
        len(posts) > n0, f"{t}: контроль — бросок на соседний блок шлёт запрос", code="drop-control"
    )


def nojs_behaviour(rep, pg, tag, slug, seite, ref, head, lang):
    t = f"{tag} {slug}/{seite}"
    if head:
        pg.goto(aufbau(slug, seite, f"&block={ref}&tab=seite"))
        # вторая форма окна («Einstellungen dieser Seitenart»): изменим её поле, но не отправим
        other = pg.locator(
            "[data-window-part] form:not(:has([name=f_title])) input[type=radio]:not(:checked)"
        )
        if other.count():
            other.first.evaluate("e => { e.checked = true; }")
        field = pg.locator("[name=f_title]").first
        orig = field.input_value()
        field.fill("E2E Titel Enter")
        posts = []
        pg.on("request", lambda r: posts.append(r.post_data or "") if r.method == "POST" else None)
        with pg.expect_navigation():
            field.press("Enter")
        pg.wait_for_load_state()
        saved = pg.locator("[name=f_title]").first.input_value()
        rep.check(
            saved == "E2E Titel Enter",
            f"{t}: без JS Enter в заголовке сохранил заголовок ({orig!r} → {saved!r})",
            code="nojs-enter",
        )
        rep.check(
            len(posts) == 1 and "f_title=" in posts[0] and "setting=" not in posts[0],
            f"{t}: Enter ушёл одним POST только формы заголовка ({len(posts)} POST, setting= {'есть' if any('setting=' in x for x in posts) else 'нет'})",
            code="nojs-only-title",
        )
    pg.goto(aufbau(slug, seite, f"&block={ref}"))
    tabs = pg.locator("[data-window-tabs] li")
    if tabs.count() >= 2:
        link = pg.locator("[data-window-tabs] li a").first
        link.click()
        pg.wait_for_load_state()
        hint = pg.locator("[data-window-hint]")
        rep.check(
            hint.count() >= 1 and hint.first.is_visible(),
            f"{t}: без JS переход по вкладке — подсказка data-window-hint видна",
            code="nojs-hint",
        )
    else:
        rep.note(
            f"{slug}/{seite}: у окна ★ одна вкладка — подсказка о вкладках (data-window-hint) не показывается, не проверена"
        )


def phone_geometry(rep, b, w, h, lang):
    """JS, окно ★: прокрутки вбок нет, «Fertig» кликабелен, активное поле не под нижним краем."""
    for slug, seite, head in (("friseur", "services", True), ("shop", "catalog", False)):
        page = sl.open_page(b, w, h, js=True, lang=lang, url=base_of(slug))
        em, pw = creds(slug)
        t = f"{w}x{h} {lang} {slug}/{seite}"
        if not rep.check(sl.login(page, base_of(slug), em, pw), f"{t}: вход", code="login"):
            page.context.close()
            continue
        page.goto(aufbau(slug, seite))
        sl.settle(page, True, rep)
        ref = page.evaluate(MARKUP_JS)["ref"]
        open_star(page, ref, True)
        sl.settle(page, True, rep)
        dlg = page.evaluate(
            "() => { const d = document.querySelector('dialog.ui-bwin[open]');"
            "return {doc: document.documentElement.scrollWidth - document.documentElement.clientWidth,"
            "dlg: d.scrollWidth - d.clientWidth}; }"
        )
        rep.check(
            dlg["doc"] <= 0 and dlg["dlg"] <= 0,
            f"{t}: нет горизонтального скролла (страница {dlg['doc']}, окно {dlg['dlg']})",
            code="phone-overflow",
        )
        done = page.locator(f"{DLG} [data-window-actions] button[value=window_done]")
        done.scroll_into_view_if_needed()
        box = done.bounding_box()
        hit = page.evaluate(
            "([x, y]) => { const e = document.elementFromPoint(x, y);"
            "return !!(e && e.closest('button[value=window_done]')); }",
            [box["x"] + box["width"] / 2, box["y"] + box["height"] / 2],
        )
        inside = (
            box["y"] >= 0
            and box["y"] + box["height"] <= h + 0.5
            and box["x"] >= 0
            and box["x"] + box["width"] <= w + 0.5
        )
        rep.check(
            done.is_visible() and hit and inside and box["height"] >= 44,
            f"{t}: «Fertig» видим и кликабелен ({box['height']:.0f} px, в экране {inside})",
            code="phone-done",
        )
        if head:
            field = page.locator(f"{DLG} [name=f_title]")
            field.click()
            fb = field.bounding_box()
            rep.check(
                fb["y"] >= 0 and fb["y"] + fb["height"] <= h + 0.5,
                f"{t}: активное поле заголовка в экране (низ {fb['y'] + fb['height']:.0f} ≤ {h})",
                code="phone-field",
            )
            area = page.locator(f"{DLG} [name=f_intro]")
            area.click()
            ab = area.bounding_box()
            rep.check(
                ab["y"] >= 0 and ab["y"] + ab["height"] <= h + 0.5 or ab["y"] + 44 <= h,
                f"{t}: активное поле «Einleitung» не под нижним краем (верх {ab['y']:.0f}, высота {h})",
                code="phone-field",
            )
        sl.shot(page, OUT, f"phone_{w}x{h}_{lang}_{slug}_{seite}")
        rep.check(
            not page.js_errors, f"{t}: без ошибок JS ({page.js_errors[:1]})", code="js-errors"
        )
        page.context.close()


def studio(rep, b, w, h, lang, js):
    lab = LAB[lang]
    slug = "friseur"
    tag = f"studio {w} {lang} {'js' if js else 'nojs'}"
    page = sl.open_page(b, w, h, js=js, lang=lang, url=base_of(slug))
    em, pw = creds(slug)
    if not rep.check(sl.login(page, base_of(slug), em, pw), f"{tag}: вход", code="login"):
        page.context.close()
        return
    url = f"{base_of(slug)}/dashboard/site/home/?page=/termin/"
    page.goto(url)
    row = page.locator("[data-pb-main-row]")
    if not js:
        rep.note("Студия без JS: панель блоков не показывается — не проверена")
        page.context.close()
        return
    page.wait_for_selector("[data-pb-main-row]", timeout=30000)
    sl.settle(page, True, rep)
    name = "Leistungen" if lang == "de" else "Услуги"
    text = row.first.inner_text().replace("\n", " ")
    rep.check(
        name in text and lab["main"] in text,
        f"{tag}: строка главного списка — «{name}» + плашка «{lab['main']}» ({text[:60]!r})",
        code="studio-main",
    )
    link = page.locator("[data-pb-main-page-link]")
    rep.check(
        link.count() == 1 and lab["list_link"] in link.inner_text(),
        f"{tag}: ссылка «{lab['list_link']}: в ★ …»",
        code="studio-link",
    )
    if lang == "ru":
        rep.check(
            not any(g in row.first.inner_text() for g in GERMAN_IN_RU),
            f"{tag}: ru — строка главного списка по-русски",
            code="ru-german",
        )
    # без правок — переход в окно ★ на «Seite»
    with page.expect_navigation(
        url=lambda u: "/dashboard/site/aufbau/" in u and "oeffnen" not in u
    ):
        link.click()
    page.wait_for_selector(f"{DLG}[open]", timeout=10000)
    rep.check(
        "tab=seite" in page.url and page.locator(f"{DLG} [name=f_title]").count() == 1,
        f"{tag}: без правок ссылка ведёт в окно ★ на «Seite»",
        code="studio-open",
    )
    # несохранённая правка Студии → confirm; «Abbrechen» — остаёмся, «OK» — идём
    page.goto(url)
    page.wait_for_selector("[data-pb-main-row]", timeout=30000)
    sl.settle(page, True, rep)
    page.evaluate(
        """() => { const f = document.getElementById('home-form');
        const i = f.querySelector('input[type=text]:not([type=hidden])');
        i.value = i.value + ' '; i.dispatchEvent(new Event('input', {bubbles: true})); }"""
    )
    page.wait_for_function("!document.getElementById('bld-save-dot').hidden", timeout=10000)
    asked = []

    def dismiss(d):
        asked.append(d.message)
        d.dismiss()

    page.once("dialog", dismiss)
    page.locator("[data-pb-main-page-link]").click()
    page.wait_for_timeout(600)
    rep.check(
        len(asked) == 1 and "/site/home/" in page.url,
        f"{tag}: правка Студии → предупреждение, «Abbrechen» — остаёмся ({asked})",
        code="studio-leave",
    )
    page.once("dialog", lambda d: d.accept())
    with page.expect_navigation(
        url=lambda u: "/dashboard/site/aufbau/" in u and "oeffnen" not in u
    ):
        page.locator("[data-pb-main-page-link]").click()
    rep.check("tab=seite" in page.url, f"{tag}: «OK» — окно ★ на «Seite»", code="studio-leave-ok")
    sl.shot(page, OUT, f"studio_{w}_{lang}")
    rep.check(not page.js_errors, f"{tag}: без ошибок JS ({page.js_errors[:1]})", code="js-errors")
    page.context.close()


def main():
    rep = sl.Report()
    with sl.launch() as b:
        for w, h, lang, js in sl.matrix():
            tag = f"{w} {lang} {'js' if js else 'nojs'}"
            print(f"— {tag}")
            sessions = {}
            for slug, seite, star_kind, hint, main_names in TARGETS:
                if slug not in sessions:
                    page = sl.open_page(b, w, h, js=js, lang=lang, url=base_of(slug))
                    em, pw = creds(slug)
                    try:
                        entered = sl.login(page, base_of(slug), em, pw)
                    except Exception as exc:  # noqa: BLE001 — нет тенанта в стенд-БД
                        rep.note(f"{tag} {slug}: вход не открылся ({type(exc).__name__}) — пропуск")
                        page.context.close()
                        sessions[slug] = None
                        continue
                    if not rep.check(entered, f"{tag} {slug}: вход", code="login"):
                        page.context.close()
                        continue
                    sessions[slug] = page
                pg = sessions.get(slug)
                if pg is None:
                    continue
                m = run_markup(rep, pg, tag, lang, js, slug, seite, star_kind, hint, main_names)
                if not m:
                    continue
                ref = m["ref"]
                run_window(rep, pg, tag, lang, js, slug, seite, star_kind, ref, main_names)
                if main_names and main_ref_of(m):
                    run_main_window(rep, pg, tag, lang, js, slug, seite, main_ref_of(m))
                old_link(rep, pg, tag, js, slug, seite, ref, lang)
                if (
                    js
                    and (w, lang) in ((1440, "de"), (390, "ru"))
                    and seite in ("services", "catalog", "promos")
                ):
                    js_behaviour(
                        rep, pg, tag, lang, slug, seite, ref, bool(hint), star_kind == HEAD
                    )
                if (
                    not js
                    and w == 1440
                    and slug in ("friseur", "shop")
                    and seite in ("services", "catalog")
                ):
                    nojs_behaviour(rep, pg, tag, slug, seite, ref, star_kind == HEAD, lang)
                rep.check(
                    not pg.js_errors,
                    f"{tag} {slug}/{seite}: без ошибок JS ({pg.js_errors[:1]})",
                    code="js-errors",
                )
                pg.js_errors.clear()
            for pg in filter(None, sessions.values()):
                pg.context.close()
        print("— телефон (окно ★)")
        for w, h in ((390, 844), (844, 390), (320, 700)):
            for lang in sl.LANGS:
                phone_geometry(rep, b, w, h, lang)
        print("— Студия")
        for lang in sl.LANGS:
            studio(rep, b, 1440, 900, lang, True)
        rep.note(
            "Студия на 390 px: панель блоков свёрнута (строка главного списка скрыта) — не проверена"
        )
        studio(rep, b, 1440, 900, "de", False)
    rep.finish()


if __name__ == "__main__":
    main()
