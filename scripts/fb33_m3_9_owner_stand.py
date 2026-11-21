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
        python scripts/fb33_m3_9_owner_stand.py <папка-скриншотов> [--only shop,hotel] [--no-js-pass|--js-only]
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
        "Amex OpenStreetMap OSM Mo Di Mi Do Fr Sa So EUR CHF Deutsch English Türkçe "
        "Button-Lösung"
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
#: слово латиницей (вкл. ç ş ğ ı é … — «Türkçe» одно слово, а не «Türk» с умлаутом)
_WORD = re.compile(r"[A-Za-zÀ-ÖØ-öø-ɏ]{2,}(?:[-'][A-Za-zÀ-ÖØ-öø-ɏ]+)*")
_UMLAUT = re.compile(r"[ÄÖÜäöüß]")
#: цитата закреплённой подписи кнопки § 312j (M0-10: «Zahlungspflichtig bestellen» не
#: переводится и не правится) — допустима в ru как цитата
#: «Без перевода: …» — список немецких исходников без перевода (так задумано: что перевести)
_SOURCE_LIST = re.compile(r"Без перевода:[^\n]*")
_LEGAL_QUOTE = re.compile(r"«?(?:Zahlungspflichtig|Kostenpflichtig)\b[^»\n]*»?")


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
from apps.core import site_schema
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
        blocks = site_schema.blocks_for(saved, r.code, host=r.host or None)  # как экран
        # общий блок в схеме одного объекта (R8) — пунктиром, только чтение, окна нет
        refs = [b["ref"] for b in blocks if not b.get("shared")]
        # строка «Einstellungen der Seite» — по правилу экрана (site_schema_views: настройки
        # или «Design» у типа есть, а ★-строки и строки-носителя нет)
        try:
            has = bool(site_schema.setting_codes(t, r.code) or site_schema.design_codes(t, r.code))
        except site_schema.SchemaError:
            has = False
        carrier = site_schema.settings_carrier(r.code)
        if has and not any(b["main"] or b["ref"] == carrier for b in blocks):
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
    """Счёт ✓/✗; повтор того же дефекта (подпись `sig`) печатается один раз, в конце — сводка."""

    def __init__(self):
        self.ok = 0
        self.fail: list[str] = []
        self.sigs: dict[str, list] = {}  # подпись дефекта → [число, первый пример]
        self.notes: dict[str, int] = {}
        self.codes: list[str] = []  # коды проверок, давших ✗ (замок сверяет их, не текст)

    def check(self, cond, label, quiet=True, sigs=None, code="other"):
        if cond:
            self.ok += 1
            if not quiet:
                print("  ✓ " + label)
            return True
        self.fail.append(label)
        self.codes.append(code)
        new = False
        for sig in sigs or [label]:
            seen = self.sigs.setdefault(sig, [0, label])
            seen[0] += 1
            new = new or seen[0] == 1
        if new or sigs is None:
            print("  ✗ " + label)
        return False

    def note(self, sig):
        """Наблюдение (не ✗): печатается один раз, в сводке — с числом."""
        self.notes[sig] = self.notes.get(sig, 0) + 1
        if self.notes[sig] == 1:
            print("  · " + sig)

    def summary(self):
        if self.notes:
            print(f"\nнаблюдения ({len(self.notes)}):")
            for sig, n in sorted(self.notes.items(), key=lambda kv: -kv[1]):
                print(f"  ×{n:<4} {sig}")
        print(f"\nсводка дефектов ({len(self.sigs)} разных):")
        for sig, (n, first) in sorted(self.sigs.items(), key=lambda kv: -kv[1][0]):
            print(f"  ×{n:<4} {sig}\n         напр.: {first[:220]}")


_TARGETS_JS = """([scope, min, spacing]) => {
  const root = scope ? document.querySelector(scope) : document.body;
  if (!root) return [];
  const sel = 'a[href],button,summary,select,input:not([type=hidden]),textarea,[role=tab]';
  const seen = new Set(), all = [];
  for (let e of root.querySelectorAll(sel)) {
    if (!e.getClientRects().length) continue;
    const cs = getComputedStyle(e);
    if (cs.visibility === 'hidden' || cs.display === 'contents') continue;
    if (e.closest('[hidden],[aria-hidden=true],.sr-only')) continue;
    // ссылка внутри предложения — исключение 2.5.8 «Inline»
    if (e.tagName === 'A' && cs.display === 'inline' && e.closest('p,td,dd,label,small'))
      continue;
    if (e.type === 'radio' || e.type === 'checkbox') e = e.closest('label') || e;
    if (seen.has(e)) continue; seen.add(e);
    const r = e.getBoundingClientRect();
    if (!r.width || !r.height) continue;
    all.push({e, r, small: r.height < min || r.width < 24,
      cx: r.left + r.width / 2, cy: r.top + r.height / 2});
  }
  // 2.5.8 «Spacing»: мелкая цель допустима, если круг Ø24 вокруг её центра не задевает
  // другие цели и круги других мелких целей (только для порога 24, не для окна 44)
  const dist = (x, y, r) => Math.hypot(Math.max(r.left - x, 0, x - r.right),
                                       Math.max(r.top - y, 0, y - r.bottom));
  const bad = [];
  for (const t of all) {
    if (!t.small) continue;
    if (spacing && !all.some(o => o !== t && !o.e.contains(t.e) && !t.e.contains(o.e) &&
        (dist(t.cx, t.cy, o.r) < 12 || (o.small && Math.hypot(o.cx - t.cx, o.cy - t.cy) < 24))))
      continue;
    const e = t.e;
    bad.push(e.tagName.toLowerCase() + '«' + (e.textContent || e.name || e.getAttribute('aria-label')
      || '').trim().replace(/\\s+/g, ' ').slice(0, 24) + '» ' + t.r.width.toFixed(0) + '×'
      + t.r.height.toFixed(0));
  }
  return bad;
}"""


def targets(pg, scope: str, minimum: int) -> list[str]:
    return pg.evaluate(_TARGETS_JS, [scope, minimum, minimum < WIN_MIN])


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


def german(text: str, content: Content | None, rep: Report | None = None) -> list[str]:
    """Немецкие слова интерфейса в тексте ru (с контекстом строки)."""
    text = _SOURCE_LIST.sub(" ", text)  # до данных: «Без» может оказаться словом содержимого
    text = _LEGAL_QUOTE.sub(" ", text)
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
    rep.check(info["panel"] and info["title"], f"{tag}: панель блока с заголовком", code="panel")
    if len(info["keys"]) > 1:
        rep.check(
            info["nav"] and info["navLabel"] and not info["unnamed"],
            f"{tag}: вкладки — nav[aria-label] и подписи ({info['navLabel']!r}, "
            f"без подписи {info['unnamed']})",
            code="tabs_label",
        )
        rep.check(
            info["sections"] == len(info["keys"]),
            f"{tag}: у каждой вкладки свой раздел ({info['sections']}/{len(info['keys'])})",
            code="tabs_sections",
        )
    if want_tab:
        rep.check(
            info["active"] == want_tab,
            f"{tag}: открыта вкладка {want_tab} ({info['active']})",
            code="tab_active",
        )
    return info["keys"]


#: страница просит окно (тот же признак, что `aufbauWindowWanted` в aufbau.js)
_WANTS_WINDOW = "!!document.querySelector('[data-schema-panel] button[value=\"window_done\"]')"


def check_window_js(rep, pg, tag):
    info = pg.evaluate(_DIALOG_JS)
    good = info["dialog"] and info["open"] and info["modal"] and info["title"]
    rep.check(
        good,
        f"{tag}: <dialog> открыт модально, заголовок по aria-labelledby ({info})",
        code="dialog",
    )
    if info.get("ntabs", 0) > 1:
        rep.check(
            info["list"]
            and info["listLabel"]
            and not info["unnamed"]
            and info["selected"] == 1
            and info["controls"],
            f"{tag}: tablist[aria-label] · tab с подписью · tabpanel ({info})",
            code="tablist",
        )
    return info.get("keys") or []


def click_tab(rep, pg, key, tag, code=""):
    """С JS вкладка открывается щелчком (APG): после щелчка видна её панель."""
    pg.click(f"dialog.ui-bwin [role=tab][data-window-tab-link={key}]", timeout=5000)
    settle(pg, True, rep)
    return rep.check(
        pg.locator(f"dialog.ui-bwin [data-window-tab={key}]").is_visible(),
        f"{tag}: панель вкладки видна после щелчка",
        sigs=[f"окно js: вкладка {key} не открылась щелчком ({_num_free(code)})"],
        code="tab_click",
    )


def _num_free(item: str) -> str:
    return re.sub(r"[0-9a-f]{8}-[0-9a-f-]{27}|[0-9a-f]{32}", "<id>", item)


def check_common(rep, pg, tag, status, errs, scope, minimum, lang, content, kind=""):
    """Общие проверки страницы; `kind` — где (окно/экран/витрина) для подписи дефекта."""
    where = _num_free(tag.split(" ", 4)[-1])
    rep.check(
        status is not None and status < 500, f"{tag}: ответ без 5xx ({status})", code="status5xx"
    )
    rep.check(
        status is not None and status < 400,
        f"{tag}: ответ не 4xx ({status})",
        sigs=[f"{kind} ответ {status} {where}"],
        code="status4xx",
    )
    over = overflow(pg)
    width = pg.evaluate("window.innerWidth")
    rep.check(
        over <= 0,
        f"{tag}: без горизонтального скролла ({over}px)",
        sigs=[f"{kind} {width}: гор. скролл {where}"],
        code="overflow",
    )
    small = targets(pg, scope, minimum)
    rep.check(
        not small,
        f"{tag}: цели ≥ {minimum}px ({len(small)}: {small[:3]})",
        sigs=[f"{kind} цель < {minimum}: {_num_free(x)}" for x in small],
        code="target",
    )
    if lang == "ru":
        de = german(visible_text(pg, scope), content, rep)
        rep.check(
            not de,
            f"{tag}: нет немецких строк в ru ({len(de)}: {de[:3]})",
            sigs=[f"{kind} ru: «{x.split(' ‹')[0]}» ‹{x.split(' ‹', 1)[1][:50]}" for x in de],
            code="german",
        )
    if errs is not None:
        rep.check(
            not errs,
            f"{tag}: без ошибок JS ({errs[:2]})",
            sigs=[f"{kind} JS: {e[:80]}" for e in errs],
            code="jserror",
        )
        errs.clear()


# --- обход --------------------------------------------------------------------------------


def login(pg, url, slug):
    pg.goto(url + "/accounts/login/")
    pg.fill("input[name=login]", f"{slug}@example.com")
    pg.fill("input[name=password]", PASSWORD)
    pg.click("button[type=submit]")
    pg.wait_for_load_state()


def settle(pg, js, rep: Report | None = None):
    """С JS: сеть затихла и закончились конечные анимации (открытие окна — 160 мс);
    бесконечные (слайдер, бегущая строка витрины) не ждём. Таймаут — не сбой стенда."""
    if not js:
        return
    try:
        # не networkidle: кадр «Vorschau» окна (M3-7) грузит витрину и держит сеть
        pg.wait_for_load_state("load", timeout=10000)
        pg.wait_for_function(
            "!document.getAnimations().filter(a => a.effect && "
            "a.effect.getTiming().iterations !== Infinity && a.playState === 'running').length",
            timeout=5000,
        )
    except Exception:  # noqa: BLE001 — замер всё равно идёт по текущему состоянию
        pass


def walk(rep, browser, slug, data, w, h, lang, js, out_dir):
    url = f"http://{data['host']}:{PORT}"
    content = Content([*data["content"], data["name"]])
    mode = "js" if js else "nojs"
    ctx = browser.new_context(
        viewport={"width": w, "height": h}, locale=f"{lang}-DE", java_script_enabled=js
    )
    ctx.add_cookies([{"name": "django_language", "value": lang, "url": url}])
    pg = ctx.new_page()
    errs: list[str] | None = [] if js else None
    if js:
        pg.on("pageerror", lambda e: errs.append(str(e)[:160]))
    login(pg, url, slug)
    if not rep.check("/accounts/login/" not in pg.url, f"{slug}: вход владельца"):
        ctx.close()
        return
    pref = f"{data['btype']} {w} {lang} {mode}"
    shot = f"{out_dir}/m39_{slug}_{w}_{lang}_{mode}"
    win_scope = "dialog.ui-bwin" if js else "[data-schema-panel]"

    def guard(tag, fn, *args):
        """Сбой стенда на одной странице — ✗ этой страницы, обход идёт дальше."""
        try:
            fn(*args)
        except Exception as exc:  # noqa: BLE001
            msg = str(exc).splitlines()[0][:160]
            rep.check(False, f"{tag}: стенд не прошёл страницу ({msg})", sigs=[f"сбой: {msg}"])

    def screen(code, n, refs):
        resp = pg.goto(f"{url}{AUFBAU}?seite={quote(code, safe='')}")
        settle(pg, js)
        check_common(
            rep,
            pg,
            f"{pref} «{code}»",
            resp and resp.status,
            errs,
            "main",
            PAGE_MIN,
            lang,
            content,
            kind="экран",
        )
        dom = pg.eval_on_selector_all(
            "[data-schema-block]", "els => els.map(e => e.getAttribute('data-schema-block'))"
        )
        want = set(refs)
        rep.check(
            set(dom) == want,
            f"{pref} «{code}»: строки экрана = строки site_schema "
            f"(лишние {sorted(set(dom) - want)}, нет {sorted(want - set(dom))})",
            sigs=[
                f"экран: строки ≠ site_schema «{_num_free(code)}» "
                f"+{sorted(set(dom) - want)} -{sorted(want - set(dom))}"
            ],
        )
        if n == 0:
            pg.screenshot(path=f"{shot}_aufbau.png")

    def window(code, ref, first):
        wurl = f"{url}{AUFBAU}?seite={quote(code, safe='')}&block={quote(ref, safe='')}"
        tag = f"{pref} «{code}» {ref}"
        resp = pg.goto(wurl)
        settle(pg, js)
        scope = win_scope
        if js and not pg.locator("dialog.ui-bwin").count() and not pg.evaluate(_WANTS_WINDOW):
            # у блока без вкладок окна нет (M3-2: `window_done` рисуется только при вкладках) —
            # панель остаётся колонкой; проверяем её как без JS
            rep.note(
                f"окно js: блок без вкладок — панель колонкой, без <dialog> («{_num_free(code)}» {ref})"
            )
            keys, scope = check_window_nojs(rep, pg, tag), "[data-schema-panel]"
        else:
            keys = check_window_js(rep, pg, tag) if js else check_window_nojs(rep, pg, tag)
        check_common(
            rep,
            pg,
            tag,
            resp and resp.status,
            errs,
            scope,
            WIN_MIN,
            lang,
            content,
            kind="окно",
        )
        if first:
            pg.screenshot(path=f"{shot}_window.png")
        for key in keys[1:] if js else keys:
            ttag = f"{tag} tab={key}"
            if js:  # вкладка — щелчком (APG); проверки — по видимой панели
                click_tab(rep, pg, key, ttag, code)
                status = 200
            else:  # без JS — адрес `?tab=`
                resp = pg.goto(f"{wurl}&tab={key}")
                check_window_nojs(rep, pg, ttag, want_tab=key)
                status = resp and resp.status
            check_common(
                rep, pg, ttag, status, errs, win_scope, WIN_MIN, lang, content, kind="окно"
            )

    def storefront(sf, first):
        site = ctx.new_page()
        if js:
            site.on("pageerror", lambda e: errs.append(str(e)[:160]))
        try:
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
                lang,
                content,
                kind="витрина",
            )
            if first:
                site.screenshot(path=f"{shot}_site.png", full_page=True)
        finally:
            site.close()

    visited_sf = set()
    for n, page in enumerate(data["pages"]):
        code = page["code"]
        guard(f"{pref} «{code}»", screen, code, n, page["refs"])
        for i, ref in enumerate(page["refs"]):
            guard(f"{pref} «{code}» {ref}", window, code, ref, n == 0 and i == 0)
        sf = page["preview"]
        if sf and sf not in visited_sf:
            visited_sf.add(sf)
            guard(f"{pref} витрина {sf}", storefront, sf, len(visited_sf) == 1)
    ctx.close()


def main_walk(argv):
    out_dir = argv[0]
    os.makedirs(out_dir, exist_ok=True)
    only = None
    if "--only" in argv:
        only = set(argv[argv.index("--only") + 1].split(","))
    passes = (False,) if "--no-js-pass" in argv else (False, True)
    if "--js-only" in argv:  # отладка прохода с JS; приёмка — оба прохода
        passes = (True,)
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
    import signal

    def stop(_sig, _frame):  # timeout/kill: сводка того, что успели пройти
        raise KeyboardInterrupt

    signal.signal(signal.SIGTERM, stop)
    try:
        _walk_all(rep, slugs, data, passes, out_dir)
    except KeyboardInterrupt:
        rep.check(False, "обход прерван (timeout/сигнал) — сводка неполная")
    rep.summary()
    print(f"\n{rep.ok} ✓, {len(rep.fail)} ✗")
    sys.exit(1 if rep.fail else 0)


def _walk_all(rep, slugs, data, passes, out_dir):
    from playwright.sync_api import sync_playwright

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
                        walk(rep, browser, slug, data[slug], w, h, lang, js, out_dir)
                        print(f"  · {slug} {w} {lang}: ✗ {len(rep.fail) - before}")
        browser.close()


# --- замок стенда: сломанные страницы обязаны дать ✗ --------------------------------------

_HEAD = '<!doctype html><html lang="ru"><meta name=viewport content="width=device-width">'
_BTN44 = "display:inline-flex;box-sizing:border-box;height:44px;padding:0 12px"
_OK_PAGE = (
    _HEAD
    + """<body style="margin:0;font:16px sans-serif"><main>
<aside data-schema-panel aria-labelledby="schema-panel-title"><h2 id="schema-panel-title">Баннер</h2>
<nav aria-label="Разделы блока" data-window-tabs><ul>
<li><a href="?tab=was" data-window-tab-link="was" aria-current="page" style="BTN">Что</a></li>
<li><a href="?tab=wie" data-window-tab-link="wie" style="BTN">Расположение</a></li></ul></nav>
<section data-window-tab="was"><p>Заголовок «Bäckerei Sonnenfeld» — <a href="#">ссылка</a></p>
<p>Наш девиз: Speichern Sie Zeit beim Bäcker</p><p>Поле «Details» для заметок</p>
<button style="BTN">Готово</button><button style="BTN;width:20px">×</button></section>
<section data-window-tab="wie" hidden><button style="BTN">Сохранить</button></section>
</aside></main></body></html>""".replace("BTN", _BTN44)
)
#: данные бизнеса чистой страницы: «Speichern» внутри них — не интерфейс
_SELF_CONTENT = ["Bäckerei Sonnenfeld", "Наш девиз: Speichern Sie Zeit beim Bäcker"]


def _broken(kind: str) -> str:
    page = _OK_PAGE
    if kind == "wide":
        page = page.replace("<main>", '<main><div style="width:800px">широкая полоса</div>')
    elif kind == "small":
        page = page.replace(f'"{_BTN44}">Готово', f'"{_BTN44.replace("44px", "20px")}">Готово')
    elif kind == "h43":  # граница: 43 px — ✗, 44 px (чистая) — ✓
        page = page.replace(f'"{_BTN44}">Готово', f'"{_BTN44.replace("44px", "43px")}">Готово')
    elif kind == "unlabeled":
        page = page.replace('aria-label="Разделы блока" ', "").replace(">Расположение<", "><")
    elif kind == "german":
        page = page.replace(">Готово<", ">Speichern und schließen<")  # видимая кнопка
    elif kind == "legal":  # «Button-Lösung» — ✗ (переведём), цитата кнопки § 312j — нет
        page = page.replace(">Готово<", ">кнопка «Zahlungspflichtig bestellen» (Button-Lösung)<")
    elif kind == "err404":  # страница ошибки: только код ответа, без целей/скролла/языка
        page = page.replace("<main>", '<main><div style="width:800px">Seite nicht gefunden</div>')
    return page


#: страница «витрины» (порог 24): ссылка в строке текста внутри div — исключение Inline
_PAGE24 = (
    _HEAD + '<body style="margin:0;font:14px sans-serif"><main><div>Читайте наши '
    '<a href="#">§1</a>,<a href="#">§2</a> перед заказом.</div>'  # плотные, но в тексте
    '<a href="#" style="display:inline-block;height:30px;width:30px">→</a></main></body>'
)
#: две узкие цели вплотную: круги Ø24 пересекаются — исключение Spacing не спасает
_PAGE24_BAD = _PAGE24.replace(
    '<a href="#" style="display:inline-block;height:30px;width:30px">→</a>',
    '<a href="#" style="display:inline-block;height:30px;width:12px">←</a>'
    '<a href="#" style="display:inline-block;height:30px;width:12px">→</a>',
)


def _dialog_page(kind: str = "") -> str:
    lb = "" if kind == "unlabeled" else ' aria-labelledby="t"'
    name_b = "" if kind == "unlabeled" else "Вид"
    # вкладка, которая не переключается: щелчок ничего не делает
    script = (
        "document.querySelector('dialog').showModal();"
        + (
            ""
            if kind == "stuck"
            else "document.querySelectorAll('[role=tab]').forEach(t => t.onclick = () => {"
            "document.querySelectorAll('[role=tabpanel]').forEach(p => p.hidden = "
            "p.id !== t.getAttribute('aria-controls'));"
            "document.querySelectorAll('[role=tab]').forEach(o => o.setAttribute("
            "'aria-selected', o === t));});"
        )
        + ("throw new Error('selftest-boom');" if kind == "throw" else "")
    )
    return (
        f'<!doctype html><body><dialog class="ui-bwin"{lb}><h2 id="t">Баннер</h2>'
        '<div role="tablist" aria-label="Разделы"><button role="tab" id="a" aria-selected="true" '
        'aria-controls="pa" data-window-tab-link="was" style="height:44px">Что</button>'
        '<button role="tab" id="b" aria-selected="false" aria-controls="pb" '
        f'data-window-tab-link="wie" style="height:44px">{name_b}</button></div>'
        '<div role="tabpanel" id="pa" aria-labelledby="a" data-window-tab="was">1</div>'
        '<div role="tabpanel" id="pb" aria-labelledby="b" data-window-tab="wie" hidden>2</div>'
        f"</dialog><script>{script}</script></body>"
    )


#: случай → (код ответа, страница, режим, ожидаемые коды ✗ — ровно эти)
SELFTEST = {
    "/ok": (200, _OK_PAGE, "win", set()),
    "/err500": (500, _OK_PAGE, "win", {"status5xx"}),
    "/err404": (404, _broken("err404"), "win", {"status4xx"}),
    "/wide": (200, _broken("wide"), "win", {"overflow"}),
    "/small": (200, _broken("small"), "win", {"target"}),
    "/h43": (200, _broken("h43"), "win", {"target"}),
    "/unlabeled": (200, _broken("unlabeled"), "win", {"tabs_label"}),
    "/german": (200, _broken("german"), "win", {"german"}),
    "/legal": (200, _broken("legal"), "win", {"german"}),
    "/page24": (200, _PAGE24, "page", set()),
    "/page24-bad": (200, _PAGE24_BAD, "page", {"target"}),
    "/dlg-ok": (200, _dialog_page(), "js", set()),
    "/dlg-bad": (200, _dialog_page("unlabeled"), "js", {"dialog", "tablist"}),
    "/dlg-stuck": (200, _dialog_page("stuck"), "js", {"tab_click"}),
    "/dlg-throw": (200, _dialog_page("throw"), "js", {"jserror"}),
}


def selftest():
    """Каждый случай даёт ✗ ровно теми проверками (по коду), что в `SELFTEST`; чистые — ✓."""
    from playwright.sync_api import sync_playwright

    content = Content(_SELF_CONTENT)
    lock = Report()
    with sync_playwright() as p:
        browser = p.chromium.launch(executable_path=CHROME)
        ctx = browser.new_context(viewport={"width": 390, "height": 844})

        def serve(route):
            path = "/" + route.request.url.split("/", 3)[3].split("?")[0]
            status, body = SELFTEST.get(path, (404, "nope", "", set()))[:2]
            route.fulfill(status=status, body=body, content_type="text/html; charset=utf-8")

        ctx.route("http://selftest.local/**", serve)
        for path, (_status, _body, mode, want) in SELFTEST.items():
            pg = ctx.new_page()
            errs: list[str] = []
            pg.on("pageerror", lambda e, errs=errs: errs.append(str(e)[:160]))
            rep = Report()
            print(f"— {path} (ожидается {sorted(want) or '✓'})")
            resp = pg.goto("http://selftest.local" + path)
            settle(pg, True, rep)
            if mode == "win":
                check_window_nojs(rep, pg, path)
                check_common(
                    rep, pg, path, resp.status, None, "[data-schema-panel]", WIN_MIN, "ru", content
                )
            elif mode == "page":
                check_common(rep, pg, path, resp.status, None, "body", PAGE_MIN, "ru", content)
            else:
                keys = check_window_js(rep, pg, path)
                check_common(
                    rep, pg, path, resp.status, errs, "dialog.ui-bwin", WIN_MIN, "ru", content
                )
                for key in keys[1:]:
                    click_tab(rep, pg, key, f"{path} tab={key}")
            got = set(rep.codes)
            lock.check(got == want, f"{path}: коды ✗ {sorted(got)} = {sorted(want)}", quiet=False)
            pg.close()
        browser.close()
    print(f"\nзамок: {lock.ok} ✓, {len(lock.fail)} ✗ (случаев {len(SELFTEST)})")
    sys.exit(1 if lock.fail else 0)


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
