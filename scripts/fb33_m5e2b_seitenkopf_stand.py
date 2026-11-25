"""FB-33 стопка 15 M5e-2b: «Seitenkopf», вариант A (артборд M5eSeitenkopf).

План — `docs/fb33-stack15-plan-2026-11-25.md` §0.2 M5eSeitenkopf, §2 «M5e-2b», §5.3 (строка
M5e-2b), §14.2 Y3/Y9. Киты `friseur` («Leistungen») и `shop» (каталог «Produkte» и одна своя
категория). Окно ★-строки на 1440/390, de/ru, с JS и без:

- на «Texte» — «Überschrift (H1)» и «Einleitung» (видимые метки), у «Leistungen» — радио
  «Ausrichtung» «Links»/«Mittig» в `fieldset`/`legend`, цели ≥ 44 px; у каталога радио нет;
- на «Seite» — полей шапки нет, пустого `fieldset` нет;
- у категории — одна ссылка «In der Kategorie bearbeiten →» на «Texte», ≥ 44 px;
- окно без горизонтальной прокрутки, `a11y_check` по окну (цели 44);
- 320×568 и 720×450 (200 %); проход только клавиатурой (вкладка «Texte» → H1 → Einleitung →
  радио → «Übernehmen», видимый фокус, Esc);
- без JS: «Mittig» → «Übernehmen» → в черновике выбранное радио; витрина: H1 каталога после
  «Speichern» (кэш страниц), затем прежний текст возвращается тем же окном.

Запуск:

    DB_NAME=<стенд-БД> DB_CONN_MAX_AGE=0 python manage.py runserver 0.0.0.0:8082 \\
        --settings=config.settings.stand --noreload
    STAND_URL=http://friseur.siteadaptor.de:8082 \\
        uv run --no-project --with playwright python scripts/fb33_m5e2b_seitenkopf_stand.py <папка>

Итог: «N ✓, M ✗». Не входит в CI.
"""

import sys
from urllib.parse import urlparse

import standlib as sl

PORT = urlparse(sl.BASE_URL).port or 80
PASSWORD = "demo-12345678"  # seed_demo_tenants.DEMO_PASSWORD
DLG = "dialog.ui-bwin"
FORM = "#bw-form-fields"
CATEGORY_SLUG = "obst-gemuese"
#: (кит, страница, есть радио, ссылка категории)
TARGETS = (
    ("friseur", "services", True, False),
    ("shop", "catalog", False, False),
    ("shop", f"category@catalog:{CATEGORY_SLUG}", False, True),
)
LAB = {
    "de": {"h1": "Überschrift (H1)", "intro": "Einleitung", "align": "Ausrichtung",
           "left": "Links", "center": "Mittig", "cat": "In der Kategorie bearbeiten →"},
    "ru": {"h1": "Заголовок (H1)", "intro": "Вступление", "align": "Выравнивание",
           "left": "Слева", "center": "По центру", "cat": ""},
}  # fmt: skip
GERMAN_IN_RU = ("Überschrift (H1)", "Mittig", "In der Kategorie bearbeiten")

MODEL_JS = """() => {
  const vis = el => !!(el && (el.offsetWidth || el.offsetHeight || el.getClientRects().length));
  const tab = k => document.querySelector('[data-window-tab="' + k + '"]');
  const texte = tab('texte'), seite = tab('seite');
  const lab = (root, id) => { const l = root && root.querySelector('label[for="' + id + '"]');
    return l ? l.innerText.trim() : ''; };
  const radios = texte ? [...texte.querySelectorAll('input[type=radio][name=f_align]')] : [];
  const group = texte && texte.querySelector('fieldset[data-schema-align]');
  const inCat = [...document.querySelectorAll('a[href*="/categories/"][href$="/edit/"]')].filter(vis);
  const catTab = inCat.filter(a => a.closest('[data-window-tab="texte"]'));
  const win = document.querySelector('dialog.ui-bwin[open]') || document.querySelector('[data-schema-panel]');
  const emptyFs = seite ? [...seite.querySelectorAll('fieldset')]
    .filter(f => !f.querySelector('input,select,textarea,button')).length : 0;
  return {
    hasTexte: !!texte, h1: lab(texte, 'schema-f-title'), intro: lab(texte, 'schema-f-intro'),
    legend: group ? group.querySelector('legend').innerText.trim() : '',
    radios: radios.map(r => ({v: r.value, checked: r.checked,
      label: (r.closest('label') || {}).innerText || '',
      h: Math.round((r.closest('label') || r).getBoundingClientRect().height)})),
    seiteHasTitle: !!(seite && seite.querySelector('#schema-f-title')),
    emptyFs,
    catTab: catTab.length,
    catLink: inCat.map(a => ({text: a.innerText.trim(), h: Math.round(a.getBoundingClientRect().height)})),
    winOver: win ? win.scrollWidth - win.clientWidth : 0,
    text: win ? win.innerText : '',
  };
}"""


def base(slug):
    return f"http://{slug}.{sl.BASE_DOMAIN}:{PORT}"


def aufbau(pg, slug, seite, query=""):
    pg.goto(f"{base(slug)}/dashboard/site/aufbau/?seite={seite}{query}")
    pg.wait_for_load_state()


def star_ref(pg) -> str:
    """ref ★-строки — из разметки (вторая строка схемы, правило `site_schema.page_row_ref`)."""
    return pg.evaluate(
        "() => { const ul = document.querySelector('[data-schema-blocks]');"
        " const li = ul && ul.children[1]; const a = li && li.querySelector(':scope > a[data-schema-block]');"
        " return a ? a.getAttribute('data-schema-block') : ''; }"
    )


def open_texte(pg, slug, seite, js) -> bool:
    aufbau(pg, slug, seite)
    ref = star_ref(pg)
    if not ref:
        return False
    pg.click(f'[data-schema-blocks] a[data-schema-block="{ref}"]')
    try:
        if js:
            pg.wait_for_selector(f"{DLG}[open]", timeout=10000)
        else:
            pg.wait_for_load_state()
        sel = '[data-window-tab-link="texte"]'
        if pg.query_selector(sel) is not None:
            if js:
                pg.click(f"{DLG}[open] {sel}")
                pg.wait_for_selector('[data-window-tab="texte"]:not([hidden])', timeout=10000)
            else:
                with pg.expect_navigation():
                    pg.click(sel)
    except Exception:  # noqa: BLE001 — стенд сообщает ✗, а не падает
        return False
    sl.settle(pg, js)
    return pg.query_selector('[data-window-tab="texte"]') is not None


def check_window(rep, pg, t, lang, js, radios, cat):
    m = pg.evaluate(MODEL_JS)
    lab = LAB[lang]
    if not rep.check(m["hasTexte"], f"{t}: вкладка «Texte» есть", code="texte"):
        return
    if cat:
        rep.check(
            len(m["catLink"]) == 1 and m["catTab"] == 1,
            f"{t}: одна ссылка категории, на «Texte» ({m['catLink']})",
            code="cat",
        )
        if m["catLink"]:
            link = m["catLink"][0]
            rep.check(link["h"] >= 44, f"{t}: ссылка ≥ 44 px ({link['h']})", code="cat44")
            if lab["cat"]:
                rep.check(link["text"] == lab["cat"], f"{t}: текст «{link['text']}»", code="cat-t")
        rep.check(not m["h1"], f"{t}: своих полей шапки у категории нет", code="cat-h1")
    else:
        rep.check(m["h1"] == lab["h1"], f"{t}: метка H1 «{m['h1']}»", code="h1")
        rep.check(m["intro"] == lab["intro"], f"{t}: метка «{m['intro']}»", code="intro")
        rep.check(not m["seiteHasTitle"], f"{t}: на «Seite» полей шапки нет", code="seite")
        rep.check(m["emptyFs"] == 0, f"{t}: на «Seite» нет пустого fieldset", code="fs")
    if radios:
        rep.check(m["legend"] == lab["align"], f"{t}: легенда «{m['legend']}»", code="legend")
        names = [r["label"].strip() for r in m["radios"]]
        rep.check(names == [lab["left"], lab["center"]], f"{t}: радио {names}", code="radio")
        rep.check(all(r["h"] >= 44 for r in m["radios"]), f"{t}: радио ≥ 44 px", code="r44")
    elif not cat:
        rep.check(not m["radios"], f"{t}: у каталога выравнивания нет", code="noalign")
    if lang == "ru":
        bad = [w for w in GERMAN_IN_RU if w in m["text"]]
        rep.check(not bad, f"{t}: нет немецких подписей ({bad})", code="ru")
    rep.check(m["winOver"] <= 0, f"{t}: окно без гор. прокрутки ({m['winOver']}px)", code="win")
    over = sl.overflow(pg)
    rep.check(over <= 0, f"{t}: без гор. скролла ({over}px)", code="overflow")
    if js and radios:
        cover(rep, pg, t)
    if js:
        tab_focus(rep, pg, t)
    scope = f'{DLG}[open] [data-window-tab="texte"]' if js else '[data-window-tab="texte"]'
    sl.a11y_check(rep, pg, t, scope=scope, minimum=44)


COVER_JS = """() => {
  const r = document.querySelector('dialog.ui-bwin[open] #schema-f-align-center');
  if (!r) return null;
  r.focus();
  const box = (r.closest('label') || r).getBoundingClientRect();
  const panel = r.closest('[data-schema-panel]').getBoundingClientRect();
  const bar = document.querySelector('dialog.ui-bwin[open] [data-window-actions]');
  const b = bar ? bar.getBoundingClientRect() : null;
  const hit = document.elementFromPoint(box.left + 4, box.top + box.height / 2);
  return {inPanel: box.top >= panel.top - 1 && box.bottom <= panel.bottom + 1,
          underBar: !!(b && box.bottom > b.top && box.top < b.bottom),
          own: !!(hit && (hit === r || r.closest('label').contains(hit)))};
}"""


def cover(rep, pg, t):
    """Ревью 1 (a11y): последнее радио в фокусе видно — не под нижней полосой окна."""
    m = pg.evaluate(COVER_JS)
    ok = m is not None and m["inPanel"] and not m["underBar"] and m["own"]
    rep.check(ok, f"{t}: радио «Mittig» в фокусе не перекрыто ({m})", code="cover")


def tab_focus(rep, pg, t):
    """Ревью 1 (a11y): после «Texte» → «Seite» → «Texte» фокус — на разделе вкладки или его
    заголовке (не потерян на body)."""
    try:
        pg.click(f'{DLG}[open] [data-window-tab-link="seite"]')
        pg.wait_for_selector('[data-window-tab="seite"]:not([hidden])', timeout=5000)
        pg.click(f'{DLG}[open] [data-window-tab-link="texte"]')
        pg.wait_for_selector('[data-window-tab="texte"]:not([hidden])', timeout=5000)
    except Exception:  # noqa: BLE001 — стенд сообщает ✗, а не падает
        rep.check(False, f"{t}: переключение вкладок", code="tabs")
        return
    at = pg.evaluate(
        "() => { const a = document.activeElement; return a ? {tag: a.tagName,"
        " tab: !!a.closest('[data-window-tab-link], [role=tab], [data-window-tab]')} : null; }"
    )
    rep.check(bool(at and at["tab"]), f"{t}: фокус после смены вкладок ({at})", code="tabfocus")


def keyboard_pass(rep, pg, out):
    if not open_texte(pg, "friseur", "services", True):
        rep.check(False, "клавиатура: окно открыто")
        return
    pg.focus(f'{DLG}[open] [data-window-tab-link="texte"]')
    seen = []
    for _ in range(16):
        pg.keyboard.press("Tab")
        info = pg.evaluate(
            """() => { const a = document.activeElement; const s = getComputedStyle(a);
              return {name: a.getAttribute('name') || a.tagName, type: a.type || '',
                ring: s.outlineStyle !== 'none' || s.boxShadow !== 'none',
                inDlg: !!a.closest('dialog.ui-bwin[open]')}; }"""
        )
        seen.append(info)
        if info["name"] == "op":
            break
    names = [s["name"] for s in seen]
    rep.check(
        "f_title" in names and "f_intro" in names and "f_align" in names,
        f"клавиатура: H1 → Einleitung → радио ({names})",
    )
    rep.check(all(s["ring"] for s in seen), "клавиатура: видимый фокус", code="ring")
    rep.check(all(s["inDlg"] for s in seen), "клавиатура: фокус в окне (без выхода)", code="trap")
    sl.shot(pg, out, "keyboard_services")
    pg.keyboard.press("Escape")
    pg.wait_for_timeout(400)
    rep.check(pg.query_selector(f"{DLG}[open]") is None, "клавиатура: Esc закрывает окно")


def nojs_radio(rep, pg, out):
    """Без JS: «Mittig» → «Übernehmen» → окно показывает выбранное; черновик отбрасывается."""
    if not open_texte(pg, "friseur", "services", False):
        rep.check(False, "без JS радио: окно открыто")
        return
    pg.check("#schema-f-align-center")
    with pg.expect_navigation():
        pg.click(f"{FORM} button[name=op][value=update]:not(.sr-only)")
    open_texte(pg, "friseur", "services", False)
    checked = pg.is_checked("#schema-f-align-center")
    rep.check(checked, "без JS: «Mittig» применено «Übernehmen»", code="nojs-radio")
    sl.shot(pg, out, "nojs_radio_mittig")
    discard(pg, "friseur", "services")


def discard(pg, slug, seite):
    aufbau(pg, slug, seite)
    btn = pg.query_selector("button[name=op][value=discard]")
    if btn is not None:
        with pg.expect_navigation():
            btn.click()


def save(pg, slug, seite):
    aufbau(pg, slug, seite)
    btn = pg.query_selector("button[name=op][value=save]")
    if btn is None:
        return False
    with pg.expect_navigation():
        btn.click()
    return True


def storefront_h1(pg) -> str:
    pg.goto(f"{base('shop')}/sortiment/")
    pg.wait_for_load_state()
    h1 = pg.query_selector("main h1") or pg.query_selector("h1")
    return h1.inner_text().strip() if h1 else ""


def storefront(rep, pg, out):
    """H1 каталога после «Speichern» (кэш страниц): прогрев, правка окном, сохранение, витрина;
    затем прежний текст возвращается тем же окном."""
    before = storefront_h1(pg)
    if not open_texte(pg, "shop", "catalog", False):
        rep.check(False, "витрина: окно каталога открыто")
        return
    old = pg.input_value("#schema-f-title")
    pg.fill("#schema-f-title", "Frisch vom Markt")
    with pg.expect_navigation():
        pg.click(f"{FORM} button[name=op][value=update]:not(.sr-only)")
    rep.check(save(pg, "shop", "catalog"), "витрина: «Speichern»")
    after = storefront_h1(pg)
    rep.check(
        after.startswith("Frisch vom Markt"), f"витрина: H1 «{after}» (было «{before}»)", code="sf"
    )
    sl.shot(pg, out, "storefront_catalog_h1")
    open_texte(pg, "shop", "catalog", False)
    pg.fill("#schema-f-title", old)
    with pg.expect_navigation():
        pg.click(f"{FORM} button[name=op][value=update]:not(.sr-only)")
    save(pg, "shop", "catalog")
    back = storefront_h1(pg)
    rep.check(back == before, f"витрина: прежний H1 вернулся («{back}»)", code="sf-back")


def main(out):
    rep = sl.Report()
    with sl.launch() as browser:
        for js in sl.JS_MODES:
            for lang in sl.LANGS:
                tag = f"{lang} {'js' if js else 'nojs'}"
                for slug in ("friseur", "shop"):
                    pg = sl.open_page(browser, 1440, 900, js=js, lang=lang, url=base(slug))
                    if not rep.check(
                        sl.login(pg, base(slug), f"{slug}@example.com", PASSWORD),
                        f"{tag} {slug}: вход",
                    ):
                        pg.context.close()
                        continue
                    for w, h in sl.SIZES:
                        pg.set_viewport_size({"width": w, "height": h})
                        for t_slug, seite, radios, cat in TARGETS:
                            if t_slug != slug:
                                continue
                            t = f"{w} {tag} {seite}"
                            if rep.check(open_texte(pg, slug, seite, js), f"{t}: окно открыто"):
                                check_window(rep, pg, t, lang, js, radios, cat)
                                sl.shot(pg, out, t.replace(" ", "_").replace(":", "_"))
                    if slug == "friseur" and lang == "de" and js:
                        keyboard_pass(rep, pg, out)
                        for w, h, name in ((320, 568, "320"), (720, 450, "200 %")):
                            pg.set_viewport_size({"width": w, "height": h})
                            t = f"{name} ({w}×{h}) services"
                            if rep.check(open_texte(pg, slug, "services", True), f"{t}: окно"):
                                m = pg.evaluate(MODEL_JS)
                                rep.check(m["winOver"] <= 0, f"{t}: без гор. прокрутки окна")
                                sl.a11y_check(rep, pg, t, scope=f"{DLG}[open]", minimum=44)
                                sl.shot(pg, out, t.replace(" ", "_").replace("%", ""))
                    if slug == "friseur" and lang == "de" and not js:
                        nojs_radio(rep, pg, out)
                    if slug == "shop" and lang == "de" and not js:
                        storefront(rep, pg, out)
                    rep.check(not pg.js_errors, f"{tag} {slug}: без ошибок JS ({pg.js_errors[:2]})")
                    pg.context.close()
    rep.finish("M5e-2b Seitenkopf")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "/tmp/fb33_m5e2b_stand")
