"""FB-33 M3-9: стенд владельца — обход редактора страницы («Seitenaufbau» и окно блока)
по пяти типам бизнеса × 1440/390 × de/ru; проход без JS (обязательный) и с JS.

Пять демо-китов (магазин, ресторан, салон, отель, ретрит). Строки НЕ списком случаев:
для каждого бизнеса стенд спрашивает у `apps.core.site_schema` все строки выбора «Seitentyp»
(`type_groups`: главная, направления, каждая категория, группа акций, каждая текстовая
страница), по первому объекту каждого вида — строку «Nur diese Seite» (`object_row`), и блоки
каждой строки (`blocks_for` + строка «Einstellungen der Seite», где она есть —
`page_window.pseudo_row`). Вкладки окна — из разметки самого окна (`data-window-tab-link`),
каждая открывается адресом `?tab=` (без JS) и щелчком по вкладке (с JS). Плюс витрина хоста
каждой строки (`PageRow.preview_url`).

Проверки на каждой странице: ответ без 5xx; без горизонтального скролла (на 390 — главное);
цели касания — в окне блока ≥ 44 px по высоте (контракт окна M3-2, `min-h-[44px]`, WCAG 2.5.5
AAA), на остальном экране и витрине ≥ 24×24 px (WCAG 2.2 2.5.8 AA; ссылки внутри текста —
исключение критерия); окно: без JS — панель с заголовком, `nav[aria-label]` и подписанные
вкладки; с JS — `<dialog>` модально, `aria-labelledby` на непустой заголовок, роли
tablist/tab/tabpanel с подписями; в ru — нет немецких строк интерфейса (эвристика ниже);
с JS — без ошибок страницы.

Эвристика «немецкое в ru»: из видимого текста вырезаются данные бизнеса (все строки его
`site_config`, полей моделей схемы и тенанта — это содержимое, не интерфейс), затем
остаётся латиница; слово считается немецким, если в нём есть ä/ö/ü/ß или оно из словаря
частых слов интерфейса/служебных (`GERMAN_WORDS`); бренды и сокращения — `ALLOW`.

    DB_NAME=platform_m39_stand uv run python scripts/fb33_m3_9_owner_stand.py --setup
    DB_NAME=platform_m39_stand uv run python manage.py runserver 0.0.0.0:8039 \\
        --settings=config.settings.stand --noreload
    DB_NAME=platform_m39_stand uv run --with playwright==1.55.0 \\
        python scripts/fb33_m3_9_owner_stand.py <папка-скриншотов> [--only shop,hotel] [--no-js-pass]
    uv run --with playwright==1.55.0 python scripts/fb33_m3_9_owner_stand.py --selftest

`--selftest` — замок самого стенда: те же проверки на заведомо сломанных страницах (5xx,
вылет по ширине, мелкая кнопка, окно без подписи, немецкое в ru) обязаны дать ✗, чистая — ✓.
Итог — «N ✓, M ✗». Chromium — /opt/pw-browsers/chromium (playwright install не запускать).
Порт — `STAND_PORT` (8039). Не входит в CI (там нет браузера).
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from urllib.parse import quote

CHROME = "/opt/pw-browsers/chromium"
BASE = "siteadaptor.de"
PORT = int(os.environ.get("STAND_PORT", "8039"))
PASSWORD = "demo-12345678"  # seed_demo_tenants.DEMO_PASSWORD
#: кит → тип (магазин, ресторан, салон, отель, ретрит)
KITS = {
    "shop": "retail",
    "restaurant": "restaurant",
    "friseur": "friseur",
    "hotel": "hotel",
    "retreat": "events",
}
SIZES = ((1440, 900), (390, 844))
LANGS = ("de", "ru")
AUFBAU = "/dashboard/site/aufbau/"
WIN_MIN = 44  # окно блока: контракт M3-2
PAGE_MIN = 24  # экран и витрина: WCAG 2.2 2.5.8 AA

#: бренды, сокращения, технические слова — латиница, допустимая в ru
ALLOW = frozenset(
    w.lower()
    for w in (
        "SiteAdaptor Stripe PayPal SumUp Klarna Google Maps Apple WhatsApp Instagram Facebook "
        "Telegram TikTok YouTube Pinterest LinkedIn Resend Mini App QR SEO URL PDF HTML CSS FAQ "
        "USP DATEV GmbH UG e.K. AG KG OHG GbR Impressum AGB DSGVO UWG PAngV BGB UStG UStVA "
        "Click Collect Hero Online Shop Tailwind iCal Booking Airbnb Expedia Tripadvisor "
        "https http www com de net org png jpg webp svg ok IBAN BIC SEPA Visa Mastercard "
        "Amex OpenStreetMap OSM Mo Di Mi Do Fr Sa So EUR CHF"
    ).split()
)
#: частые немецкие слова интерфейса и служебные — признак немецкой строки без умлаута
GERMAN_WORDS = frozenset(
    w.lower()
    for w in (
        "und oder nicht mit auf für der die das den dem des ein eine einen einer keine kein "
        "hier nur gilt wird werden sind ist ihre ihr sie wie was wo zu zum zur von vom bei "
        "alle alles eigene eigener eigenes neue neuer neues jetzt noch schon mehr weniger "
        "Speichern Abbrechen Fertig Bearbeiten Entfernen Seite Seiten Block Blocks anordnen "
        "Karte Texte Felder Vorschau Einstellungen Hauptliste Liste Ansicht zurücksetzen "
        "wählen anzeigen zeigen Breite Reihe Spalten Bild Bilder Kategorie Kategorien Vorlage "
        "Kacheln Schnellzugriff Platz Inhalte Angebote Produkte Leistungen Termine Zimmer "
        "Veranstaltungen Kontakt Startseite Hinzufügen Weiter Zurück Schließen Öffnen "
        "Übernehmen Fenster Darstellung Spalte Höchstens Zeichen Beispiel Pflichtfeld optional "
        "Bestellen Warenkorb Buchen Anfrage Senden Mehr erfahren Details Preis Preise ab"
    ).split()
)
_WORD = re.compile(r"[A-Za-zÄÖÜäöüß]{2,}(?:[-'][A-Za-zÄÖÜäöüß]+)*")
_UMLAUT = re.compile(r"[ÄÖÜäöüß]")


# --- данные из Django (строки схемы, содержимое бизнеса) ---------------------------------

SETUP = """
from django.utils import timezone
from apps.tenants import onboarding
from apps.tenants.models import Tenant
for t in Tenant.objects.filter(slug__in=SLUGS):
    t.published_at = t.published_at or timezone.now()
    t.enabled_locales = sorted(set(t.enabled_locales or []) | {"de", "ru"})
    t.save(update_fields=["published_at", "enabled_locales"])
    onboarding.mark_complete(t)
    print("READY", t.slug, t.enabled_locales)
"""

DUMP = r"""
import json
from django.apps import apps
from django.conf import settings
from django.db import connection
from django.db.models import CharField, JSONField, TextField
from apps.core import page_window, site_schema
from apps.tenants import siteconfig
from apps.tenants.models import Domain, Tenant

def leaves(v, out):
    if isinstance(v, str):
        if v.strip():
            out.add(v.strip())
    elif isinstance(v, dict):
        for x in v.values():
            leaves(x, out)
    elif isinstance(v, (list, tuple)):
        for x in v:
            leaves(x, out)

tenant_labels = {a.split(".")[-1] for a in settings.TENANT_APPS}
res = {}
for slug in SLUGS:
    t = Tenant.objects.get(slug=slug)
    host = Domain.objects.filter(tenant=t, is_primary=True).values_list("domain", flat=True).first()
    connection.set_tenant(t)
    saved = siteconfig.normalize(t.site_config)
    rows = []
    for _g, items in site_schema.type_groups(t, saved):
        rows.extend(items)
    seen = {r.code for r in rows}
    for kind in site_schema.OBJECT_KINDS:  # «Nur diese Seite»: первый объект каждого вида
        try:
            obj = site_schema.object_model(kind).objects.order_by("pk").first()
        except Exception:
            obj = None
        if obj is None:
            continue
        row = site_schema.object_row(saved, f"{kind}@{kind}:{obj.pk.hex}")
        if row is not None and row.code not in seen and site_schema.host_for(row.code):
            try:
                site_schema.resolve(t, row.code)
            except Exception:
                continue
            rows.append(row)
    pages = []
    for r in rows:
        blocks = site_schema.blocks_for(saved, r.code, host=r.host or None, summaries=False)
        refs = [b["ref"] for b in blocks]
        if page_window.pseudo_row(site_schema.PAGE_REF, blocks) is not None:
            refs.append(site_schema.PAGE_REF)
        pages.append({"code": r.code, "label": str(r.label), "preview": r.preview_url,
                      "refs": refs})
    content = set()
    leaves(t.site_config, content)
    for f in t._meta.get_fields():
        if isinstance(f, (CharField, TextField, JSONField)) and not f.is_relation:
            leaves(getattr(t, f.name, None), content)
    for m in apps.get_models():
        if m._meta.app_label not in tenant_labels or m._meta.proxy:
            continue
        fs = [f.name for f in m._meta.concrete_fields
              if isinstance(f, (CharField, TextField, JSONField))]
        if not fs:
            continue
        try:
            for vals in m.objects.values_list(*fs)[:2000]:
                leaves(list(vals), content)
        except Exception:
            pass
    res[slug] = {"host": host, "btype": t.business_type, "name": t.name,
                 "locales": list(t.enabled_locales or []), "pages": pages,
                 "content": sorted(content)}
    connection.set_schema_to_public()
print("@@JSON@@" + json.dumps(res))
"""


def django_shell(code: str, slugs) -> str:
    out = subprocess.run(
        [
            sys.executable,
            "manage.py",
            "shell",
            "--settings=config.settings.stand",
            "-c",
            f"SLUGS = {list(slugs)!r}\n" + code,
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    if out.returncode:
        sys.exit("manage.py shell: " + (out.stdout + out.stderr)[-1500:])
    return out.stdout


def kit_slugs() -> list[str]:
    """Поддомен кита — как у `seed_demo_tenants` (kit.subdomain или «<kit>-demo»)."""
    out = django_shell(
        "from apps.tenants import demo_kits\n"
        "print('@@' + ','.join(demo_kits.KITS[k].subdomain or f'{k}-demo' for k in SLUGS))",
        list(KITS),
    )
    return out.rsplit("@@", 1)[1].strip().split(",")


# --- проверки (одни и те же в обходе и в --selftest) -------------------------------------


class Report:
    def __init__(self):
        self.ok = 0
        self.fail: list[str] = []

    def check(self, cond, label, quiet=True):
        if cond:
            self.ok += 1
            if not quiet:
                print("  ✓ " + label)
        else:
            self.fail.append(label)
            print("  ✗ " + label)
        return bool(cond)


_TARGETS_JS = """([scope, min, wide]) => {
  const root = scope ? document.querySelector(scope) : document.body;
  if (!root) return [];
  const sel = 'a[href],button,summary,select,input:not([type=hidden]),textarea,[role=tab]';
  const seen = new Set(), bad = [];
  for (let e of root.querySelectorAll(sel)) {
    if (!e.getClientRects().length) continue;
    const cs = getComputedStyle(e);
    if (cs.visibility === 'hidden' || cs.display === 'contents') continue;
    if (e.closest('[hidden],[aria-hidden=true],.sr-only')) continue;
    // ссылка внутри текста — исключение 2.5.8 (inline)
    if (e.tagName === 'A' && cs.display === 'inline' && e.closest('p,li,td,dd,label,span,small'))
      continue;
    if (e.type === 'radio' || e.type === 'checkbox') e = e.closest('label') || e;
    if (seen.has(e)) continue; seen.add(e);
    const r = e.getBoundingClientRect();
    if (r.height < min || r.width < (wide ? min : 24))
      bad.push(e.tagName.toLowerCase() + '«' + (e.textContent || e.name || e.getAttribute('aria-label')
        || '').trim().replace(/\\s+/g, ' ').slice(0, 24) + '» ' + r.width.toFixed(0) + '×'
        + r.height.toFixed(0));
  }
  return bad;
}"""


def targets(pg, scope: str, minimum: int, wide: bool) -> list[str]:
    return pg.evaluate(_TARGETS_JS, [scope, minimum, wide])


def overflow(pg) -> int:
    return pg.evaluate("document.documentElement.scrollWidth - window.innerWidth")


def visible_text(pg, scope: str) -> str:
    return pg.evaluate(
        "(s) => { const r = s ? document.querySelector(s) : document.body; "
        "return r ? r.innerText : ''; }",
        scope,
    )


class Content:
    """Данные бизнеса: вырезаются из текста до поиска немецкого (это не интерфейс)."""

    def __init__(self, strings):
        phrases, words = set(), set()
        for s in strings:
            for part in re.split(r"[\n\r]+", s):
                part = part.strip()
                if len(part) >= 3:
                    phrases.add(part)
            for w in _WORD.findall(s):
                if w.lower() not in GERMAN_WORDS:
                    words.add(w.lower())
        self.phrases = sorted(phrases, key=len, reverse=True)[:6000]
        self.words = words

    def strip(self, text: str) -> str:
        for p in self.phrases:
            if p in text:
                text = text.replace(p, " ")
        return text


def german(text: str, content: Content | None) -> list[str]:
    """Немецкие слова интерфейса в тексте ru (с контекстом строки)."""
    if content is not None:
        text = content.strip(text)
    found = []
    for line in text.splitlines():
        for w in _WORD.findall(line):
            low = w.lower()
            if low in ALLOW or (content is not None and low in content.words):
                continue
            if _UMLAUT.search(w) or low in GERMAN_WORDS:
                found.append(f"{w} ‹{line.strip()[:60]}›")
                break
    return found


_DIALOG_JS = """() => {
  const d = document.querySelector('dialog.ui-bwin');
  if (!d) return {dialog: false};
  const lb = d.getAttribute('aria-labelledby'), h = lb && document.getElementById(lb);
  const tabs = [...d.querySelectorAll('[role=tab]')];
  const list = d.querySelector('[role=tablist]');
  return {dialog: true, open: d.open, modal: d.matches(':modal'),
    title: h ? h.textContent.trim() : '',
    ntabs: tabs.length, list: !!list, listLabel: list ? (list.getAttribute('aria-label') || '') : '',
    unnamed: tabs.filter(t => !t.textContent.trim() && !t.getAttribute('aria-label')).length,
    selected: tabs.filter(t => t.getAttribute('aria-selected') === 'true').length,
    controls: tabs.every(t => { const p = document.getElementById(t.getAttribute('aria-controls'));
      return p && p.getAttribute('role') === 'tabpanel' && p.getAttribute('aria-labelledby') === t.id; }),
    keys: tabs.map(t => t.getAttribute('data-window-tab-link'))};
}"""

_PANEL_JS = """() => {
  const p = document.querySelector('[data-schema-panel]');
  const h = document.getElementById('schema-panel-title');
  const nav = document.querySelector('nav[data-window-tabs]');
  const links = [...document.querySelectorAll('[data-window-tab-link]')];
  const keys = links.map(a => a.getAttribute('data-window-tab-link'));
  return {panel: !!p, title: h ? h.textContent.trim() : '', nav: !!nav,
    navLabel: nav ? (nav.getAttribute('aria-label') || '') : '',
    unnamed: links.filter(a => !a.textContent.trim()).length, keys: keys,
    sections: keys.filter(k => document.querySelector('[data-window-tab="' + k + '"]')).length,
    active: (document.querySelector('[data-window-tab]:not([hidden])') || {}).dataset?.windowTab || ''};
}"""


def check_window_nojs(rep, pg, tag, want_tab=""):
    """Окно блока без JS: панель с заголовком, подписанные вкладки, открыта запрошенная."""
    info = pg.evaluate(_PANEL_JS)
    rep.check(info["panel"] and info["title"], f"{tag}: панель блока с заголовком")
    if len(info["keys"]) > 1:
        rep.check(
            info["nav"] and info["navLabel"] and not info["unnamed"],
            f"{tag}: вкладки — nav[aria-label] и подписи ({info['navLabel']!r}, "
            f"без подписи {info['unnamed']})",
        )
        rep.check(
            info["sections"] == len(info["keys"]),
            f"{tag}: у каждой вкладки свой раздел ({info['sections']}/{len(info['keys'])})",
        )
    if want_tab:
        rep.check(
            info["active"] == want_tab, f"{tag}: открыта вкладка {want_tab} ({info['active']})"
        )
    return info["keys"]


def check_window_js(rep, pg, tag):
    info = pg.evaluate(_DIALOG_JS)
    good = info["dialog"] and info["open"] and info["modal"] and info["title"]
    rep.check(good, f"{tag}: <dialog> открыт модально, заголовок по aria-labelledby ({info})")
    if info.get("ntabs", 0) > 1:
        rep.check(
            info["list"]
            and info["listLabel"]
            and not info["unnamed"]
            and info["selected"] == 1
            and info["controls"],
            f"{tag}: tablist[aria-label] · tab с подписью · tabpanel ({info})",
        )
    return info.get("keys") or []


def check_common(rep, pg, tag, status, errs, scope, minimum, wide, lang, content):
    rep.check(status is not None and status < 500, f"{tag}: ответ без 5xx ({status})")
    over = overflow(pg)
    rep.check(over <= 0, f"{tag}: без горизонтального скролла ({over}px)")
    small = targets(pg, scope, minimum, wide)
    rep.check(not small, f"{tag}: цели ≥ {minimum}px ({len(small)}: {small[:3]})")
    if lang == "ru":
        de = german(visible_text(pg, scope), content)
        rep.check(not de, f"{tag}: нет немецких строк в ru ({len(de)}: {de[:3]})")
    if errs is not None:
        rep.check(not errs, f"{tag}: без ошибок JS ({errs[:2]})")
        errs.clear()


# --- обход --------------------------------------------------------------------------------


def login(pg, url, slug):
    pg.goto(url + "/accounts/login/")
    pg.fill("input[name=login]", f"{slug}@example.com")
    pg.fill("input[name=password]", PASSWORD)
    pg.click("button[type=submit]")
    pg.wait_for_load_state()


def settle(pg, js):
    if js:
        pg.wait_for_load_state("networkidle")
        pg.wait_for_function("!document.getAnimations().length", timeout=5000)


def walk(rep, browser, slug, data, w, h, lang, js, out_dir, shots):
    url = f"http://{data['host']}:{PORT}"
    content = Content(data["content"] + [data["name"]])
    mode = "js" if js else "nojs"
    ctx = browser.new_context(
        viewport={"width": w, "height": h}, locale=f"{lang}-DE", java_script_enabled=js
    )
    ctx.add_cookies([{"name": "django_language", "value": lang, "url": url}])
    pg = ctx.new_page()
    errs: list[str] | None = [] if js else None
    if js:
        pg.on("pageerror", lambda e: errs.append(str(e)[:120]))
    login(pg, url, slug)
    if "/accounts/login/" in pg.url:
        rep.check(False, f"{slug}: вход владельца")
        ctx.close()
        return
    pref = f"{data['btype']} {w} {lang} {mode}"
    visited_sf = set()
    for page in data["pages"]:
        code = page["code"]
        base = f"{url}{AUFBAU}?seite={quote(code, safe='')}"
        resp = pg.goto(base)
        settle(pg, js)
        check_common(
            rep,
            pg,
            f"{pref} «{code}»",
            resp and resp.status,
            errs,
            "main",
            PAGE_MIN,
            True,
            lang,
            content,
        )
        if shots and code == "home":
            pg.screenshot(path=f"{out_dir}/m39_{slug}_{w}_{lang}_{mode}_aufbau.png")
        for ref in page["refs"]:
            wurl = f"{base}&block={quote(ref, safe='')}"
            tag = f"{pref} «{code}» {ref}"
            resp = pg.goto(wurl)
            settle(pg, js)
            if js:
                keys = check_window_js(rep, pg, tag)
                scope = "dialog.ui-bwin"
            else:
                keys = check_window_nojs(rep, pg, tag)
                scope = "[data-schema-panel]"
            check_common(
                rep, pg, tag, resp and resp.status, errs, scope, WIN_MIN, False, lang, content
            )
            for key in keys[1:] if js else keys:
                ttag = f"{tag} tab={key}"
                if js:  # вкладка — щелчком (APG), панель видна, проверки — по видимому
                    pg.click(f"dialog.ui-bwin [role=tab][data-window-tab-link={key}]")
                    rep.check(
                        pg.locator(f"dialog.ui-bwin [data-window-tab={key}]").is_visible(),
                        f"{ttag}: панель вкладки видна",
                    )
                    check_common(rep, pg, ttag, 200, errs, scope, WIN_MIN, False, lang, content)
                else:  # без JS — адрес `?tab=`
                    resp = pg.goto(f"{wurl}&tab={key}")
                    check_window_nojs(rep, pg, ttag, want_tab=key)
                    check_common(
                        rep,
                        pg,
                        ttag,
                        resp and resp.status,
                        None,
                        scope,
                        WIN_MIN,
                        False,
                        lang,
                        content,
                    )
            if shots and page is data["pages"][0] and ref == page["refs"][0]:
                pg.screenshot(path=f"{out_dir}/m39_{slug}_{w}_{lang}_{mode}_window.png")
        sf = page["preview"]
        if sf and sf not in visited_sf:
            visited_sf.add(sf)
            site = ctx.new_page()
            if js:
                site.on("pageerror", lambda e: errs.append(str(e)[:120]))
            resp = site.goto(url + sf)
            settle(site, js)
            check_common(
                rep,
                site,
                f"{pref} витрина {sf}",
                resp and resp.status,
                errs,
                "body",
                PAGE_MIN,
                False,
                lang,
                content,
            )
            if shots and len(visited_sf) == 1:
                site.screenshot(path=f"{out_dir}/m39_{slug}_{w}_{lang}_{mode}_site.png")
            site.close()
    ctx.close()


def main_walk(argv):
    from playwright.sync_api import sync_playwright

    out_dir = argv[0]
    os.makedirs(out_dir, exist_ok=True)
    only = None
    if "--only" in argv:
        only = set(argv[argv.index("--only") + 1].split(","))
    passes = (False,) if "--no-js-pass" in argv else (False, True)
    slugs = kit_slugs()
    if only:
        slugs = [s for s, k in zip(slugs, KITS, strict=True) if s in only or k in only]
    raw = django_shell(DUMP, slugs).split("@@JSON@@", 1)[1]
    data = json.loads(raw)
    rep = Report()
    for slug in slugs:
        d = data[slug]
        n = sum(len(p["refs"]) for p in d["pages"])
        print(f"— {slug} ({d['btype']}): {len(d['pages'])} строк, {n} блоков, языки {d['locales']}")
        rep.check("ru" in d["locales"], f"{slug}: ru включён у бизнеса ({d['locales']})")
    with sync_playwright() as p:
        browser = p.chromium.launch(
            executable_path=CHROME, args=[f"--host-resolver-rules=MAP *.{BASE} 127.0.0.1"]
        )
        for js in passes:
            print(f"=== проход {'с JS' if js else 'без JS'}")
            for slug in slugs:
                for w, h in SIZES:
                    for lang in LANGS:
                        before = len(rep.fail)
                        walk(rep, browser, slug, data[slug], w, h, lang, js, out_dir, True)
                        print(f"  · {slug} {w} {lang}: ✗ {len(rep.fail) - before}")
        browser.close()
    print(f"\n{rep.ok} ✓, {len(rep.fail)} ✗")
    sys.exit(1 if rep.fail else 0)


# --- замок стенда: сломанные страницы обязаны дать ✗ --------------------------------------

_OK_PAGE = """<!doctype html><html lang="ru"><meta name=viewport content="width=device-width">
<body style="margin:0;font:16px sans-serif"><main>
<aside data-schema-panel aria-labelledby="schema-panel-title"><h2 id="schema-panel-title">Баннер</h2>
<nav aria-label="Разделы блока" data-window-tabs><ul>
<li><a href="?tab=was" data-window-tab-link="was" aria-current="page"
 style="display:inline-flex;min-height:44px;padding:0 12px">Что</a></li>
<li><a href="?tab=wie" data-window-tab-link="wie"
 style="display:inline-flex;min-height:44px;padding:0 12px">Расположение</a></li></ul></nav>
<section data-window-tab="was"><p>Заголовок «Bäckerei Sonnenfeld» — <a href="#">ссылка</a></p>
<button style="min-height:44px;min-width:44px">Готово</button></section>
<section data-window-tab="wie" hidden><button style="min-height:44px">Сохранить</button></section>
</aside></main></body></html>"""


def _broken(kind: str) -> str:
    page = _OK_PAGE
    if kind == "wide":
        page = page.replace("<main>", '<main><div style="width:800px">широкая полоса</div>')
    elif kind == "small":
        page = page.replace("min-height:44px;min-width:44px", "height:20px")
    elif kind == "unlabeled":
        page = page.replace('aria-label="Разделы блока" ', "").replace(">Расположение<", "><")
    elif kind == "german":
        page = page.replace(">Готово<", ">Speichern und schließen<")  # видимая кнопка
    return page


def _selftest_dialog_page(broken: bool) -> str:
    lb = "" if broken else ' aria-labelledby="t"'
    return (
        f'<!doctype html><body><dialog class="ui-bwin"{lb}><h2 id="t">Баннер</h2>'
        '<div role="tablist" aria-label="Разделы"><button role="tab" id="a" aria-selected="true" '
        'aria-controls="pa" data-window-tab-link="was">Что</button><button role="tab" id="b" '
        'aria-selected="false" aria-controls="pb" data-window-tab-link="wie">'
        f"{'' if broken else 'Вид'}</button></div>"
        '<div role="tabpanel" id="pa" aria-labelledby="a">1</div>'
        '<div role="tabpanel" id="pb" aria-labelledby="b" hidden>2</div></dialog>'
        "<script>document.querySelector('dialog').showModal()</script></body>"
    )


def selftest():
    """Каждый сломанный случай даёт ✗ ровно той проверкой, которая его ловит; чистая — ✓."""
    from playwright.sync_api import sync_playwright

    pages = {
        "/ok": (200, _OK_PAGE),
        "/err500": (500, _OK_PAGE),
        "/wide": (200, _broken("wide")),
        "/small": (200, _broken("small")),
        "/unlabeled": (200, _broken("unlabeled")),
        "/german": (200, _broken("german")),
        "/dlg-ok": (200, _selftest_dialog_page(False)),
        "/dlg-bad": (200, _selftest_dialog_page(True)),
    }
    content = Content(["Bäckerei Sonnenfeld"])
    lock, caught = Report(), Report()
    with sync_playwright() as p:
        browser = p.chromium.launch(executable_path=CHROME)
        ctx = browser.new_context(viewport={"width": 390, "height": 844})

        def serve(route):
            path = "/" + route.request.url.split("/", 3)[3].split("?")[0]
            status, body = pages.get(path, (404, "nope"))
            route.fulfill(status=status, body=body, content_type="text/html; charset=utf-8")

        ctx.route("http://selftest.local/**", serve)
        pg = ctx.new_page()
        scope = "[data-schema-panel]"

        def run(path):
            rep = Report()
            resp = pg.goto("http://selftest.local" + path)
            check_window_nojs(rep, pg, path)
            check_common(rep, pg, path, resp.status, None, scope, WIN_MIN, False, "ru", content)
            return rep.fail

        print("— чистая страница (ожидается ✓)")
        lock.check(not run("/ok"), "чистая страница — без ✗", quiet=False)
        for path, marker in (
            ("/err500", "5xx"),
            ("/wide", "скролла"),
            ("/small", "цели"),
            ("/unlabeled", "подписи"),
            ("/german", "немецких"),
        ):
            print(f"— сломанный случай {path} (ожидается ✗)")
            fails = run(path)
            caught.check(bool(fails), f"{path}: стенд дал ✗", quiet=False)
            lock.check(
                any(marker in f for f in fails), f"{path}: ✗ именно проверкой «{marker}»", False
            )
        for path, bad in (("/dlg-ok", False), ("/dlg-bad", True)):
            print(f"— окно с JS {path} (ожидается {'✗' if bad else '✓'})")
            rep = Report()
            pg.goto("http://selftest.local" + path)
            check_window_js(rep, pg, path)
            lock.check(bool(rep.fail) == bad, f"{path}: проверка <dialog>/вкладок", quiet=False)
        browser.close()
    print(
        f"\nзамок: {lock.ok} ✓, {len(lock.fail)} ✗ (сломанных пойманы: {caught.ok}/{caught.ok + len(caught.fail)})"
    )
    sys.exit(1 if lock.fail or caught.fail else 0)


def main():
    argv = sys.argv[1:]
    if "--selftest" in argv:
        selftest()
    elif "--setup" in argv:
        print(django_shell(SETUP, kit_slugs())[-800:])
    elif argv:
        main_walk(argv)
    else:
        sys.exit(__doc__)


if __name__ == "__main__":
    main()
