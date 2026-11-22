"""FB-33 M3-9c: стенд целей касания — панель блока без скриптов (≥ 44 px) и мелкие цели
витрины (≥ 24×24 px, WCAG 2.2 2.5.8 AA). Python-Playwright через `standlib`, не в CI.

Часть «окно» (тенант `ptx`): «Seitenaufbau» → каждая строка страниц `WINDOW_PAGES` → каждая
вкладка окна (адрес `?tab=`); у видимых `button`, `summary`, `select`, `[role=tab]` панели
`[data-schema-panel]` меряется высота. Без JS это колонка-панель, с JS — `<dialog>`.

Часть «витрина» (`ptx` с подвалом в колонках и демо-киты магазин, ресторан, салон, отель,
ретрит): главная и страницы, найденные по ссылкам (товар, акция, запись, номер, событие,
корзина); меряются цели из списка
`TARGETS` (подвал, «Alle anzeigen →», стрелки дня и месяца, «+ Mehr hinzufügen», «Herunterladen»,
«📅», «💬», точки слайдера — только с JS; M3-9d — точки обложки раздела и шапки категории,
«📞 Rückruf», телефон и e-mail блока «Kontakt») и ширина страницы (`scrollWidth`). С JS у точек
обложки и шапки категории — `aria-current` у нажатой, фокус по Tab (скриншот), ряд ниже CTA.

    DB_NAME=platform_m39c_stand uv run python manage.py migrate_schemas --shared
    DB_NAME=platform_m39c_stand uv run python scripts/text_pages_stand.py --setup
    DB_NAME=platform_m39c_stand uv run python scripts/text_pages_stand.py --jobs
    DB_NAME=platform_m39c_stand uv run python manage.py seed_demo_tenants \\
        --kit shop restaurant friseur hotel retreat
    DB_NAME=platform_m39c_stand uv run python scripts/fb33_m3_9_owner_stand.py --setup
    DB_NAME=platform_m39c_stand uv run python scripts/fb33_m39c_targets_stand.py --setup
    DB_NAME=platform_m39c_stand uv run python manage.py runserver 0.0.0.0:8047 \\
        --settings=config.settings.stand --noreload
    STAND_URL=http://ptx.siteadaptor.de:8047 uv run --no-project --with playwright \\
        python scripts/fb33_m39c_targets_stand.py <папка-скриншотов> \\
        [--part window|storefront] [--no-js-only] [--sizes 390] [--langs de]

Гонять ДО правки и после: «до» — ✗ на прежних 40 px и 16–20 px, «после» — «N ✓, 0 ✗».
В конце — таблицы «цель → наименьший размер» по каждому сочетанию размера, языка и режима.
`--setup` (только стенд-БД, `DB_NAME=…_stand`) даёт `ptx` подвал в две колонки, телефон и e-mail.
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
from urllib.parse import parse_qs, quote, urlparse

import standlib as sl

WIN_MIN = 44  # окно блока: контракт M3-2
PAGE_MIN = 24  # витрина: WCAG 2.2 2.5.8 AA
AUFBAU = "/dashboard/site/aufbau/"
#: страницы «Seitenaufbau» тенанта ptx: главная, корзина и заявка (вкладка «Felder»), товар
#: (Karte, «Ähnliche»), каталог (Wie anordnen), текстовая (Texte)
WINDOW_PAGES = ("home", "cart", "anfrage", "product", "catalog", "text")
#: бизнес → поддомен: `ptx` и демо-киты (`seed_demo_tenants`: kit.subdomain или «<kit>-demo»)
KITS = {
    "ptx": "ptx",
    "shop": "shop",
    "restaurant": "restaurant-demo",
    "friseur": "friseur",
    "hotel": "hotel",
    "retreat": "retreat",
}
#: страницы бизнеса: путь или `(путь-откуда, шаблон ссылки)` — первая ссылка страницы по шаблону
KIT_PAGES = {
    "ptx": ["/", "/warenkorb/"],
    "shop": [
        "/",
        "/warenkorb/",
        "/sortiment/",
        ("/sortiment/", r"^/sortiment/[a-z0-9-]+/$"),
        ("/sortiment/", r"^/sortiment/[a-z0-9-]+/[a-z0-9-]+/$"),
        "/ueber-uns/",
        "/aktionen/",
        ("/aktionen/", r"^/p/[0-9a-f-]{36}/$"),
    ],
    "restaurant": [
        "/",
        "/warenkorb/",
        "/aktionen/",
        ("/aktionen/", r"^/p/[0-9a-f-]{36}/$"),
        ("/kombi/", r"^/kombi/[0-9a-f-]{36}/$"),
    ],
    "friseur": ["/", "/termin/", ("/termin/", r"^/leistung/[0-9a-f-]{36}/$")],
    "hotel": ["/", "/unterkunft/", ("/unterkunft/", r"^/unterkunft/[0-9a-f-]{36}/")],
    "retreat": [
        "/",
        "/veranstaltung/",
        "/veranstaltung/kalender/",
        ("/veranstaltung/", r"^/veranstaltung/[0-9a-f-]{36}/$"),
    ],
}
#: цели витрины: имя → [селектор, шаблон текста или None]
TARGETS = {
    "подвал: ссылка колонки": ["footer [data-footer-columns] ul a[href]", None],
    "подвал: контакт": ["footer a[href^='tel:'], footer a[href^='mailto:']", None],
    "подвал: правовая строка": ["footer [data-sf-footer-inner] > div:last-child a[href]", None],
    "«Alle anzeigen →»": ["main a[href]:not(.sf-more):not([href*='tag='])", "^[^←→]{3,40}→$"],
    "день «← / →»": ["main a[href*='tag=']", "^(←.+|.+→)$"],
    "месяц «‹ / ›»": ["main a[href*='cal=']", "^[‹›]$"],
    "«+ Mehr hinzufügen»": ["main a[href$='/sortiment/']", "^\\+ "],
    "«Herunterladen»": ["main a[download]", None],
    "«📅 …»": ["main a[href]", "^📅"],
    "«💬 …»": ["main a[href]:not([class*='bg-'])", "^💬"],
    "точка слайдера": [".sf-slider-dot", None],
    # M3-9d
    "точка обложки раздела": ["[data-cover-dot]", None],
    "точка шапки категории": ["[data-cat-dot]", None],
    # только ссылка блока «Kontakt»: плитка quick_links «Rückruf anfordern» ведёт туда же, без «📞»
    "«📞 Rückruf»": ["main a[href*='kind=callback']", "^📞"],
    "«Kontakt»: телефон, e-mail": ["main a[href^='tel:'], main a[href^='mailto:']", None],
}
#: цели, которых на демо-китах может не быть (обложка раздела и шапка категории — по фото)
OPTIONAL_TARGETS = ("точка обложки раздела", "точка шапки категории")
#: точки со своим скриптом (не `.sf-slider-dot`): селектор → кнопка-CTA над ними (или None)
OWN_DOTS = {"[data-cover-dot]": "[data-cover-hero] a", "[data-cat-dot]": None}

_PANEL_JS = """() => {
  const p = document.querySelector('[data-schema-panel]');
  if (!p) return null;
  const out = [];
  for (const e of p.querySelectorAll('button, summary, select, [role=tab], a.ui-btn')) {
    if (!e.getClientRects().length || e.closest('[hidden], .sr-only')) continue;
    if (getComputedStyle(e).visibility === 'hidden') continue;
    const r = e.getBoundingClientRect();
    if (!r.width || !r.height) continue;
    const t = (e.textContent || '').trim() || e.getAttribute('aria-label') || e.name || '';
    out.push({tag: e.tagName.toLowerCase(), text: t.replace(/\\s+/g, ' ').slice(0, 28),
      h: Math.round(r.height * 10) / 10, pick: (e.getAttribute('name') || '') === 'pick_op'});
  }
  return out;
}"""

_TARGETS_JS = """(specs) => {
  const out = {};
  for (const [name, [sel, pattern]] of Object.entries(specs)) {
    const re = pattern ? new RegExp(pattern, 'u') : null, found = [];
    for (const e of document.querySelectorAll(sel)) {
      if (!e.getClientRects().length || e.closest('[hidden], .sr-only')) continue;
      if (getComputedStyle(e).visibility === 'hidden') continue;
      const t = (e.textContent || '').trim().replace(/\\s+/g, ' ');
      if (re && !re.test(t)) continue;
      const r = e.getBoundingClientRect();
      if (!r.width || !r.height) continue;
      found.push({text: t.slice(0, 28) || e.getAttribute('aria-label') || '',
        w: Math.round(r.width * 10) / 10, h: Math.round(r.height * 10) / 10});
    }
    out[name] = found;
  }
  return out;
}"""

#: подвал в колонках и контакты у `ptx` (у демо-китов подвал без колонок)
SETUP = """
from apps.core.pagecache import bump_storefront_cache
from apps.tenants import siteconfig
from apps.tenants.models import Tenant
t = Tenant.objects.get(schema_name="ptx")
cfg = dict(t.site_config or {})
cfg["menus"] = {**(cfg.get("menus") or {}), "footer": {"columns": [
    {"label": "Shop", "items": [
        {"label": "Sortiment", "type": "url", "target": "/sortiment/"},
        {"label": "Aktionen", "type": "url", "target": "/aktionen/"},
        {"label": "Warenkorb", "type": "url", "target": "/warenkorb/"}]},
    {"label": "Service", "items": [
        {"label": "Nachricht schreiben", "type": "url", "target": "/nachricht/"},
        {"label": "Newsletter", "type": "url", "target": "/newsletter/"}]},
]}}
t.site_config = siteconfig.normalize(cfg)
t.contact_phone = "+49 2129 123456"
t.contact_email = "hallo@ptx.test"
t.address = t.address or "Markt 1, 42781 Haan"
t.save(update_fields=["site_config", "contact_phone", "contact_email", "address"])
bump_storefront_cache(t.schema_name)
print("READY", len(t.site_config["menus"]["footer"]["columns"]), t.public_phone)
"""

_HREFS_JS = "() => [...document.querySelectorAll('a[href]')].map(a => a.getAttribute('href'))"


def _flag(argv, name, default):
    return argv[argv.index(name) + 1].split(",") if name in argv else default


def _mode(js) -> str:
    return "js" if js else "nojs"


class Table:
    """Наименьший размер цели по сочетанию «размер язык режим»."""

    def __init__(self):
        self.rows: dict[str, dict[str, tuple]] = {}

    def add(self, name, combo, size, where):
        cur = self.rows.setdefault(name, {}).get(combo)
        if cur is None or size < cur[0]:
            self.rows[name][combo] = (size, where)

    def show(self, title, fmt):
        print(f"\n{title}")
        for name, by in sorted(self.rows.items()):
            cells = "  ".join(f"{c}: {fmt(v[0])}" for c, v in sorted(by.items()))
            print(f"  {name:<34} {cells}")


# --- окно блока ---------------------------------------------------------------------------


def _refs(hrefs) -> list[str]:
    out = []
    for h in hrefs:
        ref = (parse_qs(urlparse(h or "").query).get("block") or [""])[0]
        if ref and ref not in out:
            out.append(ref)
    return out


def measure_panel(rep, table, pg, combo, where):
    found = pg.evaluate(_PANEL_JS)
    if not rep.check(found is not None, f"{combo} {where}: панель блока есть", code="panel"):
        return
    small = []
    for t in found:
        # вне правила окна (и со скриптами): ссылки-кнопки `a.ui-btn` — меряются, в ✗ не идут;
        # ручной состав «Liste» (`_schema_pick.html`) с M3-9d — 44 px, как остальное окно
        outside = t["tag"] == "a"
        kind = "состав «Liste» (pick_op)" if t["pick"] else ("a.ui-btn" if outside else t["tag"])
        table.add(kind, combo, t["h"], where)
        if t["h"] < WIN_MIN - 0.5 and not outside:
            small.append(f"{t['tag']}«{t['text']}» {t['h']:g}")
    rep.check(
        not small,
        f"{combo} {where}: цели панели ≥ {WIN_MIN} px ({small[:3]})",
        sigs=[re.sub(r"\d+$", "N", s) for s in small] or None,
        code="win44",
        quiet=True,
    )
    over = sl.overflow(pg)
    rep.check(over <= 0, f"{combo} {where}: без гор. скролла ({over}px)", code="overflow")


def window_part(rep, table, browser, out, w, h, lang, js):
    combo = f"{w} {lang} {_mode(js)}"
    pg = sl.open_page(browser, w, h, js=js, lang=lang)
    if not rep.check(sl.login(pg, sl.BASE_URL, sl.EMAIL, sl.PASSWORD), f"{combo}: вход"):
        pg.context.close()
        return
    for code in WINDOW_PAGES:
        pg.goto(f"{sl.BASE_URL}{AUFBAU}?seite={code}")
        sl.settle(pg, js, rep)
        refs = _refs(pg.evaluate(_HREFS_JS))
        rep.check(bool(refs), f"{combo} {code}: строки блоков ({len(refs)})", code="rows")
        for ref in refs:
            base = f"{sl.BASE_URL}{AUFBAU}?seite={code}&block={quote(ref, safe='')}"
            resp = pg.goto(base)
            sl.settle(pg, js, rep)
            if not rep.check(resp.status < 400, f"{combo} {code}/{ref}: {resp.status}", quiet=True):
                continue
            measure_panel(rep, table, pg, combo, f"{code}/{ref}")
            tabs = pg.evaluate(
                "() => [...document.querySelectorAll('[data-window-tab-link]')]"
                ".map(e => e.getAttribute('data-window-tab-link'))"
            )
            for tab in tabs[1:]:
                pg.goto(f"{base}&tab={tab}")
                sl.settle(pg, js, rep)
                measure_panel(rep, table, pg, combo, f"{code}/{ref}?tab={tab}")
                if (code, ref, tab) in (("cart", "form", "felder"), ("anfrage", "form", "felder")):
                    sl.shot(pg, out, f"m39c_felder_{code}_{w}_{lang}_{_mode(js)}", full=not js)
    rep.check(not pg.js_errors, f"{combo}: без ошибок JS ({pg.js_errors[:2]})", code="js")
    pg.context.close()


# --- витрина ------------------------------------------------------------------------------


def _kit_url(sub: str) -> str:
    return re.sub(r"//[^.]+\.", f"//{sub}.", sl.BASE_URL, count=1)


def _resolve(pg, base, spec, js, rep):
    if isinstance(spec, str):
        return spec
    src, pattern = spec
    pg.goto(base + src)
    sl.settle(pg, js, rep)
    rx = re.compile(pattern)
    return next((h for h in pg.evaluate(_HREFS_JS) if h and rx.search(h)), None)


_CTA_GAP_JS = """([dot, cta]) => {
  const d = document.querySelector(dot), b = cta && document.querySelector(cta);
  if (!d || !b) return null;
  return Math.round(d.parentElement.getBoundingClientRect().top - b.getBoundingClientRect().bottom);
}"""


def own_dots(rep, pg, out, combo, where, w, lang):
    """M3-9d (ревью a11y): точки обложки и шапки категории — после щелчка ровно одна точка с
    `aria-current`, и это нажатая; фокус по Tab виден (скриншот); ряд точек ниже кнопки CTA."""
    for sel, cta in OWN_DOTS.items():
        dots = pg.locator(sel)
        if dots.count() < 2 or not dots.nth(1).is_visible():
            continue
        dots.nth(1).click()
        pg.wait_for_timeout(300)
        cur = pg.evaluate(
            "(sel) => [...document.querySelectorAll(sel)]"
            ".map((d, k) => d.getAttribute('aria-current') === 'true' ? k : -1)"
            ".filter(k => k >= 0)",
            sel,
        )
        rep.check(
            cur == [1], f"{combo} {where}: {sel} aria-current у нажатой ({cur})", code="dotcur"
        )
        dots.nth(0).focus()
        pg.keyboard.press("Tab")
        pg.keyboard.press("Shift+Tab")
        kept = pg.evaluate("(sel) => document.activeElement.matches(sel)", sel)
        rep.check(kept, f"{combo} {where}: {sel} в фокусе по Tab", code="dotfocus")
        name = re.sub(r"\W+", "", sel)
        sl.shot(pg, out, f"m39d_focus_{name}_{w}_{lang}", full=False)
        gap = pg.evaluate(_CTA_GAP_JS, [sel, cta])
        if gap is not None:
            rep.check(gap >= 0, f"{combo} {where}: ряд {sel} ниже кнопки ({gap}px)", code="dotcta")


def storefront_part(rep, table, browser, out, w, h, lang, js):
    combo = f"{w} {lang} {_mode(js)}"
    seen: set[str] = set()
    for kit, sub in KITS.items():
        base = _kit_url(sub)
        pg = sl.open_page(browser, w, h, js=js, lang=lang, url=base)
        for spec in KIT_PAGES[kit]:
            path = _resolve(pg, base, spec, js, rep)
            if not rep.check(path is not None, f"{combo} {kit}: страница {spec}", code="page"):
                continue
            resp = pg.goto(base + path)
            sl.settle(pg, js, rep)
            where = f"{kit}{path}"
            if not rep.check(resp.status < 400, f"{combo} {where}: {resp.status}", code="status"):
                continue
            for name, found in pg.evaluate(_TARGETS_JS, TARGETS).items():
                small = []
                for t in found:
                    seen.add(name)
                    table.add(name, combo, (t["h"], t["w"]), where)
                    if t["h"] < PAGE_MIN - 0.5 or t["w"] < PAGE_MIN - 0.5:
                        small.append(f"«{t['text']}» {t['w']:g}×{t['h']:g}")
                if found:
                    rep.check(
                        not small,
                        f"{combo} {where}: {name} ≥ {PAGE_MIN} px ({small[:3]})",
                        sigs=f"{name} < {PAGE_MIN} px",
                        code="page24",
                    )
            if js and pg.locator(".sf-slider-dot").count() > 1:
                # ревью a11y: точка в фокусе переживает прокрутку (раньше точки пересоздавались)
                dot = pg.locator(".sf-slider:not(.sf-slider-single) .sf-slider-dot").nth(1)
                if dot.count() and dot.is_visible():
                    dot.focus()
                    pg.keyboard.press("Enter")
                    pg.wait_for_timeout(900)
                    kept = pg.evaluate(
                        "document.activeElement && document.activeElement.classList"
                        ".contains('sf-slider-dot')"
                    )
                    rep.check(kept, f"{combo} {where}: фокус остаётся на точке", code="dotfocus")
                    cur = pg.locator(".sf-slider-dot[aria-current='true']").count()
                    rep.check(cur >= 1, f"{combo} {where}: aria-current у точки", code="dotcur")
            if js:
                own_dots(rep, pg, out, combo, where, w, lang)
            over = sl.overflow(pg)
            rep.check(over <= 0, f"{combo} {where}: без гор. скролла ({over}px)", code="overflow")
            if path == "/" and kit in ("ptx", "shop"):
                sl.shot(pg, out, f"m39c_home_{kit}_{w}_{lang}_{_mode(js)}", full=True)
        rep.check(not pg.js_errors, f"{combo} {kit}: без ошибок JS ({pg.js_errors[:2]})", code="js")
        pg.context.close()
    # каждая цель списка встретилась хоть на одной странице (точки слайдера строит скрипт)
    for name in TARGETS:
        if name == "точка слайдера" and not js:
            continue
        if name in OPTIONAL_TARGETS:
            if name not in seen:
                rep.note(f"{combo}: необязательная цель «{name}» на витрине не встретилась")
            continue
        rep.check(name in seen, f"{combo}: цель «{name}» найдена на витрине", code="found")


def main():
    argv = sys.argv[1:]
    if argv[:1] == ["--setup"]:
        if not os.environ.get("DB_NAME", "").endswith("_stand"):
            sys.exit("--setup пишет в БД: только стенд-БД (DB_NAME=…_stand)")
        done = subprocess.run(
            [sys.executable, "manage.py", "shell", "--settings=config.settings.stand", "-c", SETUP],
            capture_output=True,
            text=True,
            check=False,
        )
        print((done.stdout + done.stderr)[-400:])
        sys.exit(done.returncode)
    if not argv or argv[0].startswith("--"):
        sys.exit(__doc__)
    out = argv[0]
    parts = _flag(argv, "--part", ["window", "storefront"])
    sizes = [s for s in sl.SIZES if str(s[0]) in _flag(argv, "--sizes", ["1440", "390"])]
    langs = _flag(argv, "--langs", list(sl.LANGS))
    modes = (False,) if "--no-js-only" in argv else sl.JS_MODES
    rep = sl.Report(quiet=True)
    win, page = Table(), Table()
    with sl.launch() as browser:
        for w, h, lang, js in sl.matrix(sizes, langs, modes):
            print(f"— {w} {lang} {_mode(js)}")
            if "window" in parts:
                window_part(rep, win, browser, out, w, h, lang, js)
            if "storefront" in parts:
                storefront_part(rep, page, browser, out, w, h, lang, js)
    win.show("панель блока: наименьшая высота, px", lambda v: f"{v:g}")
    page.show("витрина: наименьшая цель, ширина×высота px", lambda v: f"{v[1]:g}×{v[0]:g}")
    rep.finish("FB-33 M3-9c цели касания")


if __name__ == "__main__":
    main()
