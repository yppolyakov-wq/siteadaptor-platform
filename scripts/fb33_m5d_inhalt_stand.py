"""FB-33 стопка 12 (M5d-2 … M5d-5): стенд части окна «Inhalt» — что показывает строка и где
правится её содержимое (1440×900 и 390×844, de и ru, с JS и без).

План — `docs/fb33-stack12-plan-2026-11-23.md` §5 «Стенд», правки a11y §10 (Y1–Y8). Срез P0
(M5d-2) проверяет ядро на окнах G2 — они есть уже сейчас и после P0 обязаны остаться прежними:
- строка открывается кликом: с JS — окно `<dialog>`, без JS — та же часть колонкой в панели;
- порядок частей (Y1): «Dieser Block zeigt» → `<dl>` (у G2 его нет) → ссылка или причина →
  подсказка; «🔒 fest» — один раз и только у закреплённой строки (Y5);
- у окна из одной вкладки нет полосы вкладок и пустого `role=tablist` (Y2);
- ссылка «Inhalt bearbeiten: …» — ≥ 44 px, имя = видимый текст, без `aria-hidden`; причина —
  абзац без ссылки (Y6); «nur hier» — плашкой ПОСЛЕ ссылки (Y3);
- с JS: при открытии фокус — на заголовке окна (не на ссылке); Esc и «Fertig» возвращают фокус
  на строку блока; Tab по окну заходит на ссылку ровно один раз (Y2, Y7);
- нет горизонтальной прокрутки; ru — без немецких подписей части;
- скрытая строка (ожидание `hidden`, ревью M5d-2 a11y H1): окно открыто из «Ausgeblendet» и
  закрыто Esc или «Fertig» без правок — список «Ausgeblendet» раскрыт, фокус на ссылке строки
  (без JS — раскрыт, и адрес ведёт к ссылке строки); общая проверка — `hidden_state`;
- крайние размеры (`run_extremes`, ревью M5d-2 a11y Y7; с JS, de, по первому случаю каждого
  среза): 320×568 — без горизонтальной прокрутки документа и окна; `html{font-size:200%}` на
  1440 и 390 — «Fertig» и × достижимы; 844×390 — окно в пределах экрана, прокручивается,
  ссылка при фокусе видна.

Следующие срезы дописывают свои случаи ПОСЛЕ своего комментария-якоря `# --- cases: … ---`
(кортежи в `CASES_*`), общий обход — `run_case`; чужие куски не трогать.

Запуск (демо-киты friseur, shop, retreat — в стенд-БД, копией `CREATE DATABASE … TEMPLATE
platform_m39_stand`; вход `<kit>@example.com` / `demo-12345678`):
    DB_NAME=<стенд-БД> python manage.py runserver 0.0.0.0:8050 --settings=config.settings.stand --noreload
    STAND_URL=http://ptx.siteadaptor.de:8050 \\
        uv run --no-project --with playwright python scripts/fb33_m5d_inhalt_stand.py <папка>
Стенд только читает и закрывает окна — в схему и в черновик ничего не пишет. Итог: «N ✓, M ✗».
Не входит в CI (там нет браузера).
"""

from __future__ import annotations

import sys
from urllib.parse import urlparse

import standlib as sl

OUT = sys.argv[1] if len(sys.argv) > 1 else "/tmp/fb33_m5d_inhalt_shots"
PORT = urlparse(sl.BASE_URL).port or 80
DEMO_PASSWORD = "demo-12345678"
DLG = "dialog.ui-bwin"
MIN_TARGET = 44
#: сколько раз жать Tab, обходя окно (целей в окне «Inhalt» — до пяти: «⋯», ссылка,
#: «Abbrechen», «Fertig», ×; с запасом на оболочку браузера между кругами)
TAB_PRESSES = 12
#: немецкие подписи части, которых не должно быть в окне на русском
GERMAN_IN_RU = (
    "Dieser Block zeigt",
    "Inhalt bearbeiten",
    "Woher:",
    "Auf der Seite:",
    "nur hier",
    "Er gehört fest",
    "Eigene Blöcke darüber",
)
#: меньше — стенд ничего не проверил (страниц нет у китов): это провал, а не «0 ✗»
MIN_WINDOWS = 4

# Случай: (кит, код страницы, ref строки, ожидания). Ожидания — ключи `expect()`:
#   pinned — строка закреплена («🔒 fest» и фраза про «fest» есть);
#   dl     — есть `<dl>` «Woher / Auf der Seite» (источник `ContentSource`);
#   link   — True: ссылка обязательна; False: её нет (auto); None: ссылка или причина;
#   only_here — плашка «nur hier» после ссылки (строка одного объекта);
#   hidden — строка скрыта (лежит в «Ausgeblendet»): после закрытия окна список раскрыт.

# --- cases: m5d2 ---
CASES_M5D2 = (
    ("friseur", "contact", "form", {"pinned": True, "dl": False, "link": None}),
    ("friseur", "gift", "form", {"pinned": True, "dl": False, "link": None}),
    ("friseur", "loyalty", "programs", {"pinned": True, "dl": False, "link": None}),
    ("friseur", "passes", "plans", {"pinned": True, "dl": False, "link": None}),
    ("friseur", "booking_slots", "slots", {"pinned": True, "dl": False, "link": None}),
    ("retreat", "teachers", "teacherlist", {"pinned": True, "dl": False, "link": None}),
    ("retreat", "event_calendar", "calendar", {"pinned": True, "dl": False, "link": None}),
    ("shop", "contact", "form", {"pinned": True, "dl": False, "link": None}),
    ("shop", "finder", "wizard", {"pinned": True, "dl": False, "link": None}),
)

# --- cases: m5d3 ---
# G3: закреплённый текст страницы («Über uns», «Versand») и «Versandkosten» — без `<dl>`
# (ни «Woher», ни «Auf der Seite» у закреплённой строки нет), ссылка обязательна
_G3 = {"pinned": True, "dl": False, "link": True}
CASES_M5D3 = (
    ("shop", "text", "pagetext", _G3),
    ("shop", "text@versand", "pagetext", _G3),
    ("shop", "text@versand", "costs", _G3),
    ("friseur", "text", "pagetext", _G3),
    ("friseur", "text@versand", "costs", _G3),
    ("retreat", "text@versand", "pagetext", _G3),
    ("retreat", "text@versand", "costs", _G3),
)

# --- cases: m5d4a ---
CASES_M5D4A = ()

# --- cases: m5d4b ---
CASES_M5D4B = ()

# --- cases: m5d4c ---
CASES_M5D4C = ()

# --- cases: m5d4d ---
# событие и тур (общий тип «Veranstaltungen»): поля формы — ссылка на список событий;
# «Gastgeber» — экран; разделы «на месте» — авто, без ссылки
_G1D_FIELD = {"pinned": False, "dl": True, "link": True}
_G1D_AUTO = {"pinned": False, "dl": True, "link": False}
CASES_M5D4D = (
    ("retreat", "event", "for_whom", _G1D_FIELD),
    ("retreat", "event", "idea", _G1D_FIELD),
    ("retreat", "event", "program", _G1D_FIELD),
    ("retreat", "event", "venue", _G1D_FIELD),
    ("retreat", "event", "hosts", _G1D_FIELD),
    ("retreat", "event", "price", _G1D_FIELD),
    ("retreat", "event", "certifications", _G1D_FIELD),
    ("retreat", "event", "groups", _G1D_AUTO),
    ("retreat", "event", "more_dates", _G1D_AUTO),
    ("retreat", "event", "private_tour", _G1D_AUTO),
)

# --- cases: m5d4e ---
# акция, Kombi, запись блога: тип страницы (у Kombi и блога своей схемы объекта нет)
_G1E_SHOWN = {"pinned": False, "dl": True, "link": True}
_G1E_AUTO = {"pinned": False, "dl": True, "link": False}
_G1E_FIXED = {"pinned": True, "dl": True, "link": True}
CASES_M5D4E = (
    ("friseur", "promo", "share", _G1E_AUTO),
    ("friseur", "promo", "card", _G1E_SHOWN),
    ("friseur", "promo", "related", _G1E_AUTO),
    ("restaurant-demo", "combo", "config", _G1E_FIXED),
    ("restaurant-demo", "combo", "examples", _G1E_AUTO),
    ("restaurant-demo", "combo", "related", _G1E_AUTO),
    ("retreat", "blog_post", "article", _G1E_FIXED),
    ("retreat", "blog_post", "more", _G1E_AUTO),
)

# --- cases: m5d5 ---
# G4: «Positionen» корзины и «Bestätigung» — закреплены, «Woher» есть, ссылки нет (авто);
# «Empfehlungen» скрыта по умолчанию — строка в «Ausgeblendet», ссылка на «Sortiment»
_G4_AUTO = {"pinned": True, "dl": True, "link": False}
_G4_RECOMMEND = {"pinned": False, "dl": True, "link": True}
CASES_M5D5 = (
    ("shop", "cart", "items", _G4_AUTO),
    ("shop", "confirmation", "summary", _G4_AUTO),
    ("shop", "confirmation", "recommend", _G4_RECOMMEND),
    ("friseur", "cart", "items", _G4_AUTO),
    ("friseur", "confirmation", "recommend", _G4_RECOMMEND),
    ("retreat", "confirmation", "summary", _G4_AUTO),
    ("retreat", "confirmation", "recommend", _G4_RECOMMEND),
)

# --- cases: end ---
CASE_GROUPS = (
    CASES_M5D2,
    CASES_M5D3,
    CASES_M5D4A,
    CASES_M5D4B,
    CASES_M5D4C,
    CASES_M5D4D,
    CASES_M5D4E,
    CASES_M5D5,
)
CASES = tuple(case for group in CASE_GROUPS for case in group)

PART_JS = """() => {
  const root = document.querySelector('dialog.ui-bwin[open]') || document.querySelector('[data-schema-panel]');
  if (!root) return null;
  const part = root.querySelector('[data-window-part="inhalt"]');
  const txt = e => e.textContent.replace(/\\s+/g, ' ').trim();
  const out = {part: !!part, dialog: root.tagName === 'DIALOG',
    tabs: root.querySelectorAll('[data-window-tabs]').length,
    emptyTablist: [...root.querySelectorAll('[role=tablist]')].filter(t => !t.children.length).length,
    done: !!root.querySelector('button[value="window_done"]'),
    text: txt(root), overflow: document.documentElement.scrollWidth - window.innerWidth,
    inner: root.scrollWidth - root.clientWidth};
  if (!part) return out;
  const order = ['[data-inhalt-summary]', 'dl[data-inhalt-dl]', '[data-inhalt-link],[data-inhalt-reason]',
    '[data-inhalt-hint]'].map(s => part.querySelector(s)).filter(Boolean);
  out.ordered = order.every((el, i) => !i ||
    !!(order[i - 1].compareDocumentPosition(el) & Node.DOCUMENT_POSITION_FOLLOWING));
  out.summary = !!part.querySelector('[data-inhalt-summary]');
  out.hint = !!part.querySelector('[data-inhalt-hint]');
  out.dl = part.querySelectorAll('dl[data-inhalt-dl]').length;
  out.woher = !!part.querySelector('dd[data-inhalt-woher]');
  out.visibility = !!part.querySelector('dd[data-inhalt-visibility]');
  out.fixed = part.querySelectorAll('[data-inhalt-fixed]').length;
  out.fixedHidden = [...part.querySelectorAll('[data-inhalt-fixed]')]
    .every(b => b.getAttribute('aria-hidden') === 'true');
  const a = part.querySelector('a[data-inhalt-link]');
  out.link = !!a;
  if (a) {
    out.linkH = Math.round(a.getBoundingClientRect().height);
    out.linkAria = a.hasAttribute('aria-hidden') || a.hasAttribute('aria-label');
    out.linkText = txt(a);
    out.badgeInLink = !!a.querySelector('.ui-badge');
    const badge = part.querySelector('[data-inhalt-only-here]');
    out.onlyHere = !!badge;
    out.badgeAfter = badge ? !!(a.compareDocumentPosition(badge) & Node.DOCUMENT_POSITION_FOLLOWING) : null;
    out.badgeHidden = badge ? badge.hasAttribute('aria-hidden') : null;
  }
  const reason = part.querySelector('[data-inhalt-reason]');
  out.reason = !!reason;
  out.reasonLink = reason ? !!reason.querySelector('a,[aria-disabled]') : false;
  return out; }"""

#: ревью M5d-2 (a11y H1): строка в «Ausgeblendet» после закрытия её окна
HIDDEN_JS = """(ref) => { const d = document.querySelector('details[data-schema-hidden]');
  const row = document.getElementById('schema-row-' + ref);
  const a = document.activeElement;
  return {open: !!d && d.open, rowIn: !!d && !!row && d.contains(row),
    focusIn: !!d && !!a && a !== document.body && d.contains(a),
    target: !!row && row.matches(':target')}; }"""

#: ревью M5d-2 (a11y Y7): крайние размеры — (код, ширина, высота, корневой кегль в %)
EXTREMES = (
    ("x320", 320, 568, 0),
    ("zoom1440", 1440, 900, 200),
    ("zoom390", 390, 844, 200),
    ("land", 844, 390, 0),
)
ZOOM_INIT = """document.addEventListener('DOMContentLoaded', () => {
  const s = document.createElement('style'); s.textContent = 'html{font-size:%d%%}';
  document.head.appendChild(s); });"""
#: довести элемент окна до экрана (фокусом, нефокусируемый — прокруткой) и сказать, виден ли
REACH_JS = """(sel) => { const win = document.querySelector('dialog.ui-bwin[open]');
  const el = win && win.querySelector(sel);
  if (!el) return {found: false};
  el.focus();
  if (document.activeElement !== el) el.scrollIntoView({block: 'nearest', inline: 'nearest'});
  const r = el.getBoundingClientRect();
  const x = Math.min(Math.max(r.left + r.width / 2, 0), window.innerWidth - 1);
  const top = document.elementFromPoint(x, r.top + r.height / 2);
  return {found: true, focused: document.activeElement === el,
    box: [r.left, r.top, r.right, r.bottom].map(Math.round),
    inView: r.top >= -0.5 && r.left >= -0.5 && r.bottom <= window.innerHeight + 0.5 &&
      r.right <= window.innerWidth + 0.5,
    hit: !!top && (top === el || el.contains(top))}; }"""
WINDOW_BOX_JS = """() => { const win = document.querySelector('dialog.ui-bwin[open]');
  if (!win) return null;
  const r = win.getBoundingClientRect();
  const scrollers = [win, ...win.querySelectorAll('*')].filter(e =>
    /(auto|scroll)/.test(getComputedStyle(e).overflowY));
  return {fits: r.top >= -0.5 && r.left >= -0.5 && r.bottom <= window.innerHeight + 0.5 &&
      r.right <= window.innerWidth + 0.5,
    box: [r.left, r.top, r.right, r.bottom].map(Math.round),
    scrollable: scrollers.length > 0,
    clipped: scrollers.every(e => e.scrollHeight <= e.clientHeight + 1) &&
      win.scrollHeight > win.clientHeight + 1}; }"""

FOCUS_JS = """() => { const a = document.activeElement; if (!a) return {};
  const win = document.querySelector('dialog.ui-bwin[open]');
  return {id: a.id || '', tag: a.tagName, block: a.getAttribute('data-schema-block') || '',
    link: a.hasAttribute('data-inhalt-link'), inside: !!win && win.contains(a)}; }"""


def base_of(slug):
    return f"http://{slug}.{sl.BASE_DOMAIN}:{PORT}"


def creds(slug):
    return (sl.EMAIL, sl.PASSWORD) if slug == "ptx" else (f"{slug}@example.com", DEMO_PASSWORD)


def aufbau(slug, seite, extra=""):
    return f"{base_of(slug)}/dashboard/site/aufbau/?seite={seite}{extra}"


def row_selector(ref):
    return f'a[data-schema-block="{ref}"]'


def open_row(pg, ref, js) -> bool:
    """Клик по строке: с JS — окно `<dialog>`, без — панель той же страницей. Скрытая
    строка лежит в свёрнутом «Ausgeblendet» — сначала раскрыть список."""
    row = pg.query_selector(row_selector(ref))
    if row is not None and not row.is_visible():
        pg.click("details[data-schema-hidden] > summary")
    pg.click(row_selector(ref))
    if js:
        try:
            pg.wait_for_selector(f"{DLG}[open]", timeout=10000)
        except Exception as exc:  # noqa: BLE001 — стенд сообщает ✗, а не падает
            print(f"    окно не открылось: {type(exc).__name__}")
            return False
        sl.settle(pg, True)
        return True
    pg.wait_for_load_state()
    return True


def hidden_state(rep, pg, t, ref, how, js) -> None:
    """Ревью M5d-2 (a11y H1): окно скрытой строки закрыто без правок — «Ausgeblendet» раскрыт,
    ссылка строки в нём; с JS фокус на ней, без JS к ней ведёт адрес (`:target`). Общая
    проверка случаев со скрытой строкой (`hidden` в ожиданиях)."""
    st = pg.evaluate(HIDDEN_JS, ref)
    rep.check(
        st["open"] and st["rowIn"],
        f"{t}: {how} → «Ausgeblendet» раскрыт, строка в нём ({st})",
        code="hidden-open",
    )
    at = st["focusIn"] if js else st["target"]
    rep.check(at, f"{t}: {how} → фокус (без JS — якорь) на ссылке строки ({st})", code="hidden-at")


def back_on_row(pg, ref) -> bool:
    """Окно закрыто, фокус — на строке блока."""
    try:
        pg.wait_for_url(lambda u: "block=" not in u, timeout=20000)
        pg.wait_for_load_state()
        sl.settle(pg, True)
        pg.wait_for_function(
            "(r) => (document.activeElement && "
            "document.activeElement.getAttribute('data-schema-block')) === r",
            arg=ref,
            timeout=3000,
        )
    except Exception as exc:  # noqa: BLE001 — стенд сообщает ✗, а не падает
        print(
            f"    фокус не вернулся на строку {ref}: {type(exc).__name__} {pg.evaluate(FOCUS_JS)}"
        )
        return False
    return True


def expect(rep, m, t, lang, want):
    """Проверки разметки части по ожиданиям случая (одни для окна и для колонки без JS)."""
    rep.check(m["part"] and m["summary"] and m["hint"], f"{t}: часть «Inhalt» есть", code="part")
    if not m["part"]:
        return
    rep.check(m["ordered"], f"{t}: порядок zeigt → dl → ссылка/причина → подсказка", code="order")
    rep.check(m["done"], f"{t}: «Fertig» окна есть", code="done")
    rep.check(
        m["tabs"] == 0 and m["emptyTablist"] == 0,
        f"{t}: одна вкладка — без полосы и пустого tablist",
        code="tablist",
    )
    fixed = 1 if want["pinned"] else 0
    rep.check(
        m["fixed"] == fixed and m["fixedHidden"],
        f"{t}: «🔒 fest» — {fixed} раз ({m['fixed']})",
        code="fixed",
    )
    if want["dl"]:
        rep.check(m["dl"] == 1 and m["woher"], f"{t}: один dl с «Woher»", code="dl")
        if not want["pinned"]:
            rep.check(m["visibility"], f"{t}: «Auf der Seite» есть", code="dl-visibility")
    else:
        rep.check(m["dl"] == 0, f"{t}: dl нет (как у G2)", code="dl-none")
    if want["link"] is None:
        rep.check(m["link"] != m["reason"], f"{t}: ссылка или причина (одно из двух)", code="link")
    elif want["link"]:
        rep.check(m["link"], f"{t}: ссылка «Inhalt bearbeiten» есть", code="link")
    else:
        rep.check(not m["link"] and not m["reason"], f"{t}: ссылки нет (авто)", code="link-none")
    if m["link"]:
        rep.check(m["linkH"] >= MIN_TARGET, f"{t}: ссылка ≥ 44 px ({m['linkH']})", code="link-44")
        rep.check(
            not m["linkAria"] and not m["badgeInLink"],
            f"{t}: имя ссылки = видимый текст, плашки внутри нет",
            code="link-name",
        )
        only_here = bool(want.get("only_here"))
        rep.check(m["onlyHere"] == only_here, f"{t}: «nur hier» — {only_here}", code="only-here")
        if m["onlyHere"]:
            rep.check(
                m["badgeAfter"] and not m["badgeHidden"],
                f"{t}: «nur hier» — после ссылки, не aria-hidden",
                code="only-here-after",
            )
    if m["reason"]:
        rep.check(not m["reasonLink"], f"{t}: в причине нет ссылки", code="reason-link")
    rep.check(m["overflow"] <= 0, f"{t}: без гор. скролла ({m['overflow']}px)", code="overflow")
    rep.check(m["inner"] <= 0, f"{t}: окно без гор. скролла ({m['inner']}px)", code="overflow-in")
    if lang == "ru":
        bad = [g for g in GERMAN_IN_RU if g in m["text"]]
        rep.check(not bad, f"{t}: ru — немецких подписей нет ({bad})", code="ru-german")


def tab_walk(pg) -> list[dict]:
    stops = []
    for _ in range(TAB_PRESSES):
        pg.keyboard.press("Tab")
        stops.append(pg.evaluate(FOCUS_JS))
    return stops


def run_focus(rep, pg, t, ref, m, want):
    """С JS: фокус при открытии, обход Tab, Esc и «Fertig» возвращают на строку (Y2, Y7)."""
    hidden = bool(want.get("hidden"))
    at = pg.evaluate(FOCUS_JS)
    rep.check(
        at.get("id") == "schema-panel-title" and not at.get("link"),
        f"{t}: при открытии фокус — на заголовке окна ({at})",
        code="focus-open",
    )
    stops = tab_walk(pg)
    inside = [s for s in stops if s.get("tag") not in ("BODY", "HTML")]
    rep.check(
        all(s.get("inside") for s in inside),
        f"{t}: Tab не выходит из окна",
        code="tab-inside",
    )
    if m["link"]:
        # круг целей повторяется: ссылка встречается не чаще, чем раз за круг
        links = [i for i, s in enumerate(stops) if s.get("link")]
        gaps = [b - a for a, b in zip(links, links[1:], strict=False)]
        rep.check(
            bool(links) and all(g > 1 for g in gaps),
            f"{t}: на ссылку — одна Tab-остановка за круг ({links})",
            code="tab-link",
        )
    pg.keyboard.press("Escape")
    rep.check(back_on_row(pg, ref), f"{t}: Esc → фокус на строке блока", code="focus-esc")
    if hidden:
        hidden_state(rep, pg, t, ref, "Esc", True)
    if not open_row(pg, ref, True):
        rep.check(False, f"{t}: окно открылось повторно", code="reopen")
        return
    pg.click(f'{DLG}[open] [data-window-actions] button[value="window_done"]')
    rep.check(back_on_row(pg, ref), f"{t}: «Fertig» → фокус на строке блока", code="focus-done")
    if hidden:
        hidden_state(rep, pg, t, ref, "«Fertig»", True)


def run_hidden_nojs(rep, pg, t, ref):
    """Без JS: «Fertig» в панели скрытой строки — список «Ausgeblendet» раскрыт, адрес ведёт
    к ссылке строки."""
    pg.click('[data-schema-panel] [data-window-actions] button[value="window_done"]')
    pg.wait_for_load_state()
    hidden_state(rep, pg, t, ref, "«Fertig»", False)


def reach(rep, pg, t, selector, what, code):
    """Элемент окна достижим: после фокуса (или прокрутки) он целиком на экране и не перекрыт."""
    r = pg.evaluate(REACH_JS, selector)
    rep.check(
        r["found"] and r["inView"] and r["hit"],
        f"{t}: {what} достижим — на экране и не перекрыт ({r})",
        code=code,
    )


def run_extreme(rep, browser, extreme, case) -> None:
    """Ревью M5d-2 (a11y Y7): одно окно на крайнем размере (с JS, de)."""
    tag, w, h, zoom = extreme
    slug, seite, ref, _want = case
    t = f"{tag} {slug}/{seite}/{ref}"
    pg = sl.open_page(browser, w, h, js=True, lang="de")
    try:
        if zoom:
            pg.add_init_script(ZOOM_INIT % zoom)
        email, password = creds(slug)
        if not rep.check(sl.login(pg, base_of(slug), email, password), f"{t}: вход", code="login"):
            return
        pg.goto(aufbau(slug, seite))
        sl.settle(pg, True, rep)
        if not pg.query_selector(row_selector(ref)):
            rep.note(f"{t}: строки нет у кита — пропущено")
            return
        if not rep.check(open_row(pg, ref, True), f"{t}: окно открылось", code="open"):
            return
        m = pg.evaluate(PART_JS)
        if not rep.check(bool(m and m["part"]), f"{t}: часть «Inhalt» есть", code="part"):
            return
        sl.shot(pg, OUT, f"{slug}_{seite}_{ref}_{tag}")
        if tag == "x320":
            rep.check(
                m["overflow"] <= 0, f"{t}: без гор. скролла ({m['overflow']}px)", code="overflow"
            )
            rep.check(
                m["inner"] <= 0, f"{t}: окно без гор. скролла ({m['inner']}px)", code="overflow-in"
            )
        box = pg.evaluate(WINDOW_BOX_JS)
        rep.check(
            bool(box) and box["fits"], f"{t}: окно в пределах экрана ({box})", code="window-fits"
        )
        if tag == "land":
            rep.check(
                bool(box) and box["scrollable"] and not box["clipped"],
                f"{t}: окно прокручивается, содержимое не обрезано ({box})",
                code="window-scroll",
            )
            if m["link"]:
                reach(rep, pg, t, "a[data-inhalt-link]", "ссылка «Inhalt bearbeiten»", "reach-link")
        done = '[data-window-actions] button[value="window_done"]'
        reach(rep, pg, t, done, "«Fertig»", "reach-done")
        # на телефоне (уже 768 px) × скрыт стилями: его место — верхняя «Fertig» панели
        shown = pg.evaluate(
            "() => { const x = document.querySelector('dialog.ui-bwin[open] [data-bwin-close]');"
            " return !!x && x.getClientRects().length > 0; }"
        )
        if shown:
            reach(rep, pg, t, "[data-bwin-close]", "×", "reach-close")
        else:
            reach(rep, pg, t, "[data-schema-done]", "верхняя «Fertig» (× скрыт)", "reach-close")
        rep.check(not pg.js_errors, f"{t}: без ошибок JS ({pg.js_errors[:2]})", code="js-errors")
    finally:
        pg.context.close()


def run_extremes(rep, browser) -> None:
    """Крайние размеры — по первому случаю каждого среза (своего якоря `# --- cases: … ---`)."""
    for group in CASE_GROUPS:
        for case in group[:1]:
            for extreme in EXTREMES:
                run_extreme(rep, browser, extreme, case)


def run_case(rep, pg, tag, lang, js, case) -> bool:
    """Один случай; False — страницы или строки у кита нет (заметкой, не ✗)."""
    slug, seite, ref, want = case
    t = f"{tag} {slug}/{seite}/{ref}"
    resp = pg.goto(aufbau(slug, seite))
    sl.settle(pg, js, rep)
    if not rep.check(resp is not None and resp.status < 400, f"{t}: экран отвечает", code="status"):
        return True
    if not pg.query_selector(row_selector(ref)):
        rep.note(f"{t}: строки нет у кита — пропущено")
        return False
    if not rep.check(open_row(pg, ref, js), f"{t}: окно открылось", code="open"):
        return True
    m = pg.evaluate(PART_JS)
    if not rep.check(m is not None, f"{t}: панель окна есть", code="panel"):
        return True
    rep.check(m["dialog"] == js, f"{t}: {'dialog' if js else 'колонка без JS'}", code="mode")
    expect(rep, m, t, lang, want)
    sl.shot(pg, OUT, f"{slug}_{seite}_{ref}_{tag.replace(' ', '_')}")
    if js and m["part"]:
        run_focus(rep, pg, t, ref, m, want)
    elif m["part"] and want.get("hidden"):
        run_hidden_nojs(rep, pg, t, ref)
    rep.check(not pg.js_errors, f"{t}: без ошибок JS ({pg.js_errors[:2]})", code="js-errors")
    return True


def main():
    rep = sl.Report()
    seen = 0
    with sl.launch() as browser:
        for w, h, lang, js in sl.matrix():
            tag = f"{w} {lang} {'js' if js else 'nojs'}"
            for slug in dict.fromkeys(case[0] for case in CASES):
                pg = sl.open_page(browser, w, h, js=js, lang=lang)
                email, password = creds(slug)
                if rep.check(
                    sl.login(pg, base_of(slug), email, password),
                    f"{tag} {slug}: вход",
                    code="login",
                ):
                    for case in CASES:
                        if case[0] == slug:
                            seen += run_case(rep, pg, tag, lang, js, case)
                pg.context.close()
        run_extremes(rep, browser)
    combos = len(list(sl.matrix()))
    rep.check(
        seen >= MIN_WINDOWS * combos,
        f"проверено окон: {seen} (не меньше {MIN_WINDOWS} на сочетание)",
        code="coverage",
    )
    rep.finish()


if __name__ == "__main__":
    main()
