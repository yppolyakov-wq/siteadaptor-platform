"""FB-33 стопка 14 E7 (M5d-8): «Woher» окна «Inhalt» — списком полей.

План — `docs/fb33-stack14-plan-2026-11-24.md` §2 «E7», §5.3, правки a11y §10 (H2, M1–M3, L3).
Окно строки раздела из нескольких полей: «Produktinformationen» у типа «Produkt» (еда —
вложенный список «Kennzeichnung», розница — «Marke & Zustand» через запятую) и у одного товара
(«ausgefüllt/leer» словом, значок `aria-hidden`), «Ort» у типа «Veranstaltung» и у одного
события, «Ausstattung» у типа «Unterkunft». Проверки: `<ul role=list aria-labelledby>` на
вводную фразу, dt/dd не `inline`; 1440 — две колонки, 390 — одна; «›» в тексте списка нет;
без горизонтальной прокрутки; `a11y_check` по части окна. Крайние размеры (с JS, de) —
320×568, 720×450 (200 %) и 360×225 (400 %): без горизонтальной прокрутки окна;
слово в 60 символов на 320 и 390 — тоже.

Запуск (демо-киты стенд-БД: restaurant-demo, shop, retreat, hotel; вход `<kit>@example.com`):

    DB_NAME=<стенд-БД> DB_CONN_MAX_AGE=0 python manage.py runserver 0.0.0.0:8147 \\
        --settings=config.settings.stand --noreload
    STAND_URL=http://shop.siteadaptor.de:8147 \\
        uv run --no-project --with playwright python scripts/fb33_e7_woher_stand.py <папка>

Стенд только открывает окна и читает разметку. Итог: «N ✓, M ✗». Не входит в CI.
"""

import re
import sys
from urllib.parse import urlparse

import standlib as sl

PORT = urlparse(sl.BASE_URL).port or 80
PASSWORD = "demo-12345678"  # seed_demo_tenants.DEMO_PASSWORD
DLG = "dialog.ui-bwin"
#: слаг кита → адрес списка объектов и шаблон адреса формы объекта
OBJECT_LISTS = {
    "product": ("/catalog/products/", r"/catalog/products/([0-9a-f-]{36})/edit/"),
    "event": ("/dashboard/events/", r"/dashboard/events/([0-9a-f-]{36})/"),
}
#: (кит, страница, строка, вложенный список, строка объекта)
CASES = (
    ("restaurant-demo", "product", "info", True, False),
    ("restaurant-demo", "@product", "info", False, True),
    ("shop", "product", "info", False, False),
    ("retreat", "event", "venue", False, False),
    ("retreat", "@event", "venue", False, True),
    ("hotel", "stay", "amenities", False, False),
)
LIST_JS = """() => {
  const root = document.querySelector('[data-inhalt-woher-list]');
  if (!root) return null;
  const row = root.querySelector('[data-inhalt-woher-row]');
  const dt = row.querySelector('dt'), dd = row.querySelector('dd');
  const ul = dd.querySelector(':scope > ul');
  const intro = ul && document.getElementById(ul.getAttribute('aria-labelledby') || '');
  const items = [...ul.children].map(li => ({
    text: li.innerText, display: getComputedStyle(li).display,
    icons: [...li.querySelectorAll(':scope > span')].map(s => s.getAttribute('aria-hidden')),
  }));
  const a = dt.getBoundingClientRect(), b = dd.getBoundingClientRect();
  return {
    role: ul && ul.getAttribute('role'), introOk: !!(intro && intro.tagName === 'P'),
    introText: intro ? intro.innerText : '', items,
    nested: dd.querySelectorAll('ul ul').length,
    nestedRole: [...dd.querySelectorAll('ul ul')].every(u => u.getAttribute('role') === 'list'),
    dtDisplay: getComputedStyle(dt).display, ddDisplay: getComputedStyle(dd).display,
    sideBySide: b.left > a.right - 1 && b.top < a.bottom, stacked: b.top >= a.bottom - 1,
    text: dd.innerText,
    ids: document.querySelectorAll('#inhalt-woher-intro').length,
    winOver: (() => { const w = document.querySelector('dialog.ui-bwin[open]')
      || document.querySelector('[data-schema-panel]');
      return w ? w.scrollWidth - w.clientWidth : 0; })(),
  };
}"""
_CODES: dict = {}


def base_of(slug):
    return f"http://{slug}.{sl.BASE_DOMAIN}:{PORT}"


def resolve(pg, slug, seite):
    """`@вид` — первый объект кита из списка кабинета; None — не нашли."""
    if not seite.startswith("@"):
        return seite
    kind = seite[1:]
    if (slug, kind) not in _CODES:
        path, pattern = OBJECT_LISTS[kind]
        resp = pg.goto(base_of(slug) + path)
        found = re.search(pattern, pg.content()) if resp is not None and resp.status < 400 else None
        _CODES[(slug, kind)] = f"{kind}@{kind}:{found.group(1).replace('-', '')}" if found else None
    return _CODES[(slug, kind)]


def open_window(pg, slug, code, ref, js) -> bool:
    pg.goto(f"{base_of(slug)}/dashboard/site/aufbau/?seite={code}")
    sel = f'a[data-schema-block="{ref}"]'
    if pg.query_selector(sel) is None:
        return False
    pg.click(sel)
    if js:
        try:
            pg.wait_for_selector(f"{DLG}[open]", timeout=10000)
        except Exception:  # noqa: BLE001 — стенд сообщает ✗, а не падает
            return False
    pg.wait_for_load_state()
    sl.settle(pg, js)
    return True


def check_list(rep, pg, t, w, nested, is_object, lang):
    m = pg.evaluate(LIST_JS)
    if not rep.check(m is not None, f"{t}: список «Woher» есть", code="list"):
        return
    rep.check(m["role"] == "list" and m["introOk"], f"{t}: ul role=list, aria-labelledby → <p>")
    rep.check(m["ids"] == 1, f"{t}: id вводной фразы один ({m['ids']})", code="id")
    rep.check(
        m["dtDisplay"] != "inline" and m["ddDisplay"] != "inline",
        f"{t}: dt/dd не inline ({m['dtDisplay']}, {m['ddDisplay']})",
    )
    rep.check(
        all(i["display"] == "list-item" or i["display"] == "block" for i in m["items"]),
        f"{t}: li — блок ({[i['display'] for i in m['items']]})",
    )
    # у типа товара группа одной вкладки — один пункт («Marke & Zustand» через запятую)
    rep.check(len(m["items"]) >= 1, f"{t}: пункты есть ({len(m['items'])})")
    rep.check(
        (m["nested"] >= 1 and m["nestedRole"]) if nested else m["nested"] == 0,
        f"{t}: вложенный список {'есть' if nested else 'нет'} ({m['nested']})",
    )
    rep.check("›" not in m["text"], f"{t}: без «›» в тексте")
    if w >= 1440:
        rep.check(m["sideBySide"], f"{t}: 1440 — dt и dd в две колонки")
    else:
        rep.check(m["stacked"], f"{t}: 390 — одна колонка")
    if is_object:
        words = ("ausgefüllt", "leer") if lang == "de" else ("заполнено", "пусто")
        rep.check(
            all(i["text"].rstrip().endswith(words) for i in m["items"]),
            f"{t}: состояние словом у каждого пункта ({[i['text'][-14:] for i in m['items']]})",
            code="state",
        )
        rep.check(
            all(all(h == "true" for h in i["icons"]) and i["icons"] for i in m["items"]),
            f"{t}: значок aria-hidden ({[i['icons'] for i in m['items']]})",
            code="icon",
        )
        rep.check(
            re.search(r"\d+ \S+ \d+", m["introText"]) is not None,
            f"{t}: итог «N von M» ({m['introText']})",
        )
    rep.check(m["winOver"] <= 0, f"{t}: окно без гор. прокрутки ({m['winOver']}px)", code="win")


def run_kit(rep, pg, out, slug, lang, js):
    """Все случаи кита на одной странице (вход один раз — у входа лимит запросов)."""
    for seite, ref, nested, is_object in [c[1:] for c in CASES if c[0] == slug]:
        code = resolve(pg, slug, seite)
        if code is None:
            rep.note(f"{slug} {seite}: объекта нет — случай пропущен")
            continue
        for w, h in sl.SIZES:
            pg.set_viewport_size({"width": w, "height": h})
            t = f"{w} {lang} {'js' if js else 'nojs'} {slug} {seite}/{ref}"
            if not rep.check(open_window(pg, slug, code, ref, js), f"{t}: окно открыто"):
                continue
            check_list(rep, pg, t, w, nested, is_object, lang)
            over = sl.overflow(pg)
            rep.check(over <= 0, f"{t}: без гор. скролла ({over}px)", code="overflow")
            scope = f"{DLG}[open]" if js else "[data-inhalt-woher-list]"
            sl.a11y_check(rep, pg, t, scope=scope, minimum=44)
            sl.shot(pg, out, t.replace(" ", "_").replace("/", "-"))
        if js and lang == "de" and (nested or (is_object and slug == "restaurant-demo")):
            run_extremes(rep, pg, out, slug, code, ref)


#: ревью a11y M2: зум — меньшим вьюпортом (1440×900 при 200 % ≈ 720×450, при 400 % ≈ 360×225)
EXTREMES = ((320, 568, "320"), (720, 450, "200 %"), (360, 225, "400 %"))
#: ревью a11y M1: слово без пробелов в 60 символов — колонка не раздувается
LONG_WORD_JS = """() => { const li = document.querySelector('[data-inhalt-woher-item]');
  if (!li) return false; li.append(' ' + 'Ä'.repeat(60)); return true; }"""


def doc_over_without_window(pg, slug, code):
    """Ширина кабинета без окна на том же вьюпорте — старый долг отличаем от среза."""
    pg.goto(f"{base_of(slug)}/dashboard/site/aufbau/?seite={code}")
    sl.settle(pg, True)
    return sl.overflow(pg)


def run_extremes(rep, pg, out, slug, code, ref):
    """Крайние размеры (с JS, de): 320×568, 720×450 (200 %), 360×225 (400 %) — окно без
    горизонтальной прокрутки; документ — как без окна (иначе ✗). Длинное слово на 320 и 390."""
    for w, h, name in EXTREMES:
        pg.set_viewport_size({"width": w, "height": h})
        t = f"{name} ({w}×{h}) {slug} {code.split('@')[0]}/{ref}"
        if not open_window(pg, slug, code, ref, True):
            rep.check(False, f"{t}: окно открыто")
            continue
        m = pg.evaluate(LIST_JS)
        over = sl.overflow(pg)
        sl.shot(pg, out, t.replace(" ", "_").replace("/", "-").replace("%", ""))
        rep.check(
            m is not None and m["winOver"] <= 0,
            f"{t}: окно без гор. прокрутки ({m and m['winOver']})",
            code="extreme",
        )
        if over > 0:
            base = doc_over_without_window(pg, slug, code)
            if rep.check(base >= over, f"{t}: документ {over}px — как без окна ({base}px)"):
                rep.note(f"{name} ({w}×{h}): кабинет шире экрана на {base}px и без окна")
    for w, h in ((320, 568), (390, 844)):
        pg.set_viewport_size({"width": w, "height": h})
        t = f"{w} длинное слово {slug} {code.split('@')[0]}/{ref}"
        if not open_window(pg, slug, code, ref, True):
            rep.check(False, f"{t}: окно открыто")
            continue
        pg.evaluate(LONG_WORD_JS)
        m = pg.evaluate(LIST_JS)
        over = sl.overflow(pg)
        rep.check(
            m is not None and m["winOver"] <= 0 and over <= 0,
            f"{t}: без гор. прокрутки (окно {m and m['winOver']}, документ {over})",
            code="long-word",
        )
        sl.shot(pg, out, t.replace(" ", "_").replace("/", "-"))


def main(out):
    rep = sl.Report()
    kits = list(dict.fromkeys(c[0] for c in CASES))
    with sl.launch() as browser:
        for js in sl.JS_MODES:
            for lang in sl.LANGS:
                for slug in kits:
                    pg = sl.open_page(browser, 1440, 900, js=js, lang=lang, url=base_of(slug))
                    tag = f"{lang} {'js' if js else 'nojs'} {slug}"
                    if rep.check(
                        sl.login(pg, base_of(slug), f"{slug}@example.com", PASSWORD),
                        f"{tag}: вход",
                    ):
                        run_kit(rep, pg, out, slug, lang, js)
                    rep.check(not pg.js_errors, f"{tag}: без ошибок JS ({pg.js_errors[:2]})")
                    pg.context.close()
    rep.finish("E7 Woher")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "/tmp/fb33_e7_stand")
