"""FB-33 M3-6: стенд «Seite у страницы, Wo zeigen у баннера, закреплённый блок 🔒» (1440/390, de/ru,
с JS и без).

Магазин (online_shop): страница «Über uns» с блоком «Banner» (один баннер), категории «Brot» (открыта)
и «Aus» (выключена), корзина, товар. Сценарий: «Einstellungen der Seite» окном (вкладка «Seite»
открыта, Esc, «Abbrechen» — черновика нет, SEO во «Texte» → «Fertig» → «Speichern» → в базе) →
окно баннера (подпись плитки, «Wo zeigen»: поиск, «Hinzufügen», «Abbrechen», снова, «Speichern» →
`Banner.show_on`) → закреплённые: 🔒 в списке и в заголовке окна, плашка § 312j, подпись кнопки
только для чтения, «Kaufen» без ручки. Без JS — то же окно формами, вкладки-ссылки.

    DB_NAME=<стенд-БД> uv run python scripts/fb33_m3_6_stand.py --setup          # один раз
    DB_NAME=<стенд-БД> python manage.py runserver 0.0.0.0:8063 --settings=config.settings.stand --noreload
    DB_NAME=<стенд-БД> uv run --no-project --with playwright python scripts/fb33_m3_6_stand.py <папка> [порт]

Chromium — /opt/pw-browsers/chromium (playwright install не запускать). Итог: «N ✓, M ✗».
Не входит в CI (там нет браузера).
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys

CHROME = "/opt/pw-browsers/chromium"
BASE = "siteadaptor.de"
SLUG = "m36"
PASSWORD = "Stand-Passwort-123"
DLG = "dialog.ui-bwin"
PLAQUE = "§ 312j BGB"

SETUP = f"""
from django.utils import timezone
from django_tenants.utils import tenant_context
from apps.tenants.models import Domain, Tenant
from apps.tenants.services import create_business
from apps.tenants import onboarding, siteconfig
for old in Tenant.objects.filter(schema_name={SLUG!r}):
    old.delete(force_drop=True)
from django.db import connection
with connection.cursor() as c:
    c.execute("DROP SCHEMA IF EXISTS {SLUG} CASCADE")
tenant, _ = create_business(business_name="Bäckerei Stand", slug={SLUG!r},
    business_type="online_shop", city="Haan", email="owner@{SLUG}.test", password={PASSWORD!r})
tenant.published_at = timezone.now()
tenant.enabled_locales = ["de", "ru"]
tenant.save(update_fields=["published_at", "enabled_locales"])
onboarding.mark_complete(tenant)
Domain.objects.update_or_create(domain="{SLUG}.{BASE}", defaults={{"tenant": tenant, "is_primary": True}})
print("READY")
"""

RESET = f"""
import datetime
from django.utils import timezone
from django_tenants.utils import tenant_context
from apps.tenants.models import Tenant
from apps.tenants import siteconfig
t = Tenant.objects.get(schema_name={SLUG!r})
with tenant_context(t):
    from apps.catalog.models import Category
    from apps.core.models import Banner
    Category.objects.filter(slug__in=["brot", "aus"]).delete()
    Category.objects.create(name={{"de": "Brot & Brötchen", "ru": "Хлеб"}}, slug="brot", is_active=True)
    Category.objects.create(name={{"de": "Aus dem Sortiment"}}, slug="aus", is_active=False)
    Banner.objects.all().delete()
    a = Banner.objects.create(title="Herbst: Kürbisbrot", ends=timezone.localdate() + datetime.timedelta(days=10))
    Banner.objects.create(title="Stollen ab 1. Advent", starts=timezone.localdate() + datetime.timedelta(days=9))
    Banner.objects.create(title="Sonntag geöffnet", is_active=False)
cfg = siteconfig.normalize(t.site_config or {{}})
pb = dict(cfg.get("page_blocks") or {{}})
pb["info"] = [{{"key": "banner", "id": "bn1", "enabled": True, "data": {{"pick": [str(a.pk)]}}}}]
cfg["page_blocks"] = pb
cfg.pop("seo", None)
t.site_config = cfg
t.save(update_fields=["site_config"])
print("BANNER", a.pk)
"""

READ = f"""
import json
from django_tenants.utils import tenant_context
from apps.tenants.models import Tenant
t = Tenant.objects.get(schema_name={SLUG!r})
with tenant_context(t):
    from apps.core.models import Banner
    a = Banner.objects.get(title="Herbst: Kürbisbrot")
    print("CFG" + json.dumps({{"seo": (t.site_config.get("seo") or {{}}).get("pages", {{}}).get("info"),
          "show_on": a.show_on}}))
"""


def shell(code: str) -> str:
    out = subprocess.run(
        [sys.executable, "manage.py", "shell", "-c", code],
        capture_output=True,
        text=True,
        env={**os.environ, "DJANGO_SETTINGS_MODULE": "config.settings.stand"},
        check=False,
    )
    if out.returncode:
        sys.exit(out.stderr[-2000:])
    return out.stdout


def saved() -> dict:
    line = next(x for x in shell(READ).splitlines() if x.startswith("CFG"))
    return json.loads(line[3:])


ok, fail = 0, []


def check(c, label):
    global ok
    ok += bool(c)
    print(("  ✓ " if c else "  ✗ ") + label)
    if not c:
        fail.append(label)


def login(pg, host):
    pg.goto(host + "/accounts/login/")
    pg.fill("input[name=login]", f"owner@{SLUG}.test")
    pg.fill("input[name=password]", PASSWORD)
    pg.click("button[type=submit]")
    pg.wait_for_load_state()


def settle(pg):
    pg.wait_for_function("!document.getAnimations().length", timeout=5000)


def no_draft(pg, host, code="text"):
    pg.goto(f"{host}/dashboard/site/aufbau/?seite={code}")
    return pg.locator("[data-schema-draft-note]").count() == 0


def small_targets(pg):
    return pg.evaluate(
        """(sel) => [...document.querySelectorAll(sel + ' :is(a,button,summary,select,input,textarea,[role=tab])')]
          .filter(e => e.getClientRects().length && getComputedStyle(e).visibility !== 'hidden')
          .filter(e => !(e.tagName === 'A' && getComputedStyle(e).display === 'inline'))
          .map(e => (e.type === 'radio' || e.type === 'checkbox') ? (e.closest('label') || e) : e)
          .filter(e => e.getBoundingClientRect().height < 44)
          .map(e => e.tagName + ':' + (e.textContent || e.name || '').trim().slice(0, 12))""",
        DLG,
    )


def page_window(pg, host, out, w, lang):
    """«Einstellungen der Seite» окном: «Seite» открыта, Esc, «Abbrechen», SEO → «Speichern»."""
    aufbau = f"{host}/dashboard/site/aufbau/?seite=text"
    pg.goto(aufbau + "&block=__page")
    settle(pg)
    info = pg.evaluate(
        """(sel) => { const d = document.querySelector(sel); if (!d) return null;
          const t = d.querySelector('[role=tab][aria-selected=true]');
          return {open: d.open, modal: d.matches(':modal'), title: d.querySelector('#schema-panel-title').textContent.trim(),
            tab: t && t.getAttribute('id'), sw: document.documentElement.scrollWidth, iw: innerWidth} }""",
        DLG,
    )
    check(info and info["open"] and info["modal"], f"{w} {lang}: «Seite» открыта модальным окном")
    check(info and info["tab"] == "schema-tabbtn-seite", f"{w} {lang}: открыта вкладка «Seite»")
    check(info and info["sw"] <= info["iw"], f"{w} {lang}: без горизонтальной прокрутки")
    small = small_targets(pg)
    check(not small, f"{w} {lang}: цели окна не ниже 44 px ({small[:4]})")
    pg.screenshot(path=f"{out}/m36-seite-{w}-{lang}.png")
    pg.keyboard.press("Escape")
    pg.wait_for_url(lambda u: "block=" not in u, timeout=20000)
    check(True, f"{w} {lang}: Esc закрывает окно")
    # «Texte»: SEO → «Abbrechen» — черновика нет
    pg.goto(aufbau + "&block=__page&tab=texte")
    settle(pg)
    pg.fill("#schema-f-seo_title", "Über die Bäckerei")
    pg.locator("#schema-f-seo_title").blur()
    pg.wait_for_function(
        "!+document.documentElement.getAttribute('data-schema-busy')", timeout=15000
    )
    pg.wait_for_timeout(400)
    pg.locator(f"{DLG} [data-window-actions] button[value=revert]").click()
    pg.wait_for_load_state()
    check(no_draft(pg, host), f"{w} {lang}: «Abbrechen» — черновика нет")
    pg.goto(aufbau + "&block=__page&tab=texte")
    settle(pg)
    pg.fill("#schema-f-seo_title", "Über die Bäckerei")
    pg.fill("#schema-f-seo_description", "Seit 1920 in Haan.")
    pg.screenshot(path=f"{out}/m36-seo-{w}-{lang}.png")
    pg.locator(f"{DLG} [data-window-actions] button[value=window_done]").click()
    pg.wait_for_url(lambda u: "block=" not in u, timeout=20000)
    check(
        pg.locator("[data-schema-draft-note]").count() == 1, f"{w} {lang}: правка SEO в черновике"
    )
    check(saved()["seo"] is None, f"{w} {lang}: до «Speichern» в базе SEO нет")
    pg.click("button[name=op][value=save]")
    pg.wait_for_load_state()
    check(
        saved()["seo"] == {"title": "Über die Bäckerei", "description": "Seit 1920 in Haan."},
        f"{w} {lang}: «Speichern» — SEO страницы записано",
    )


def banner_window(pg, host, out, w, lang):
    aufbau = f"{host}/dashboard/site/aufbau/?seite=text&block=bn1"
    pg.goto(aufbau)
    settle(pg)
    caps = pg.locator(f"{DLG} [data-schema-banner-caption]").all_text_contents()
    check(
        any(re.search(r"\d\d\.\d\d\.", c) for c in caps),
        f"{w} {lang}: подпись срока у плитки ({caps[:2]})",
    )
    check(
        pg.locator(f"{DLG} [data-schema-banner-library]").count() == 1,
        f"{w} {lang}: текст про библиотеку",
    )
    check(
        pg.locator(f"{DLG} [data-schema-places]").count() == 1,
        f"{w} {lang}: «Wo zeigen» у одного баннера",
    )
    pg.fill(f"{DLG} [data-schema-places-search] input[name=wo]", "Brot")
    pg.locator(f"{DLG} [data-schema-places-search] button").click()
    pg.wait_for_load_state()
    settle(pg)
    boxes = pg.locator(f"{DLG} input[name=wo_add]")
    values = [boxes.nth(i).get_attribute("value") for i in range(boxes.count())]
    check("category:brot" in values, f"{w} {lang}: поиск нашёл открытую категорию")
    check("category:aus" not in values, f"{w} {lang}: выключенной категории в поиске нет")
    pg.locator(f"{DLG} input[name=wo_add][value='category:brot']").check()
    pg.screenshot(path=f"{out}/m36-wo-{w}-{lang}.png")
    pg.locator(f"{DLG} [data-schema-places-add] button[value=add]").click()
    pg.wait_for_load_state()
    settle(pg)
    check(
        pg.locator(f"{DLG} [data-schema-place='category:brot']").count() == 1,
        f"{w} {lang}: место добавлено чипом",
    )
    said = pg.locator(f"{DLG} [data-schema-places-said]").text_content().strip()
    focus = pg.evaluate("() => document.activeElement && document.activeElement.id")
    check(
        said and focus == "schema-tab-places",
        f"{w} {lang}: итог объявлен, фокус на «Wo zeigen» ({said}, {focus})",
    )
    small = small_targets(pg)
    check(not small, f"{w} {lang}: цели окна баннера не ниже 44 px ({small[:4]})")
    pg.locator(f"{DLG} [data-window-actions] button[value=revert]").click()
    pg.wait_for_load_state()
    check(no_draft(pg, host), f"{w} {lang}: «Abbrechen» вернул места — черновика нет")
    check(saved()["show_on"] == [], f"{w} {lang}: библиотека не тронута")
    pg.goto(aufbau + "&wo=Brot")
    settle(pg)
    pg.locator(f"{DLG} input[name=wo_add][value='category:brot']").check()
    pg.locator(f"{DLG} [data-schema-places-add] button[value=add]").click()
    pg.wait_for_load_state()
    settle(pg)
    pg.locator(f"{DLG} [data-window-actions] button[value=window_done]").click()
    pg.wait_for_url(lambda u: "block=" not in u, timeout=20000)
    pg.click("button[name=op][value=save]")
    pg.wait_for_load_state()
    check(
        saved()["show_on"] == ["category:brot"], f"{w} {lang}: «Speichern» — места баннера записаны"
    )


def pinned(pg, host, out, w, lang):
    pg.goto(f"{host}/dashboard/site/aufbau/?seite=cart&block=summary")
    settle(pg)
    info = pg.evaluate(
        """(sel) => { const d = document.querySelector(sel);
          const f = d.querySelector('#schema-legal-label');
          const li = document.querySelector('[data-schema-pinned="summary"]');
          return {title: d.querySelector('#schema-panel-title').textContent,
            plaque: (d.querySelector('[data-schema-legal]') || {}).textContent || '',
            field: f && {ro: f.readOnly, name: f.getAttribute('name'), form: !!f.form, value: f.value,
              whole: f.scrollHeight <= f.clientHeight + 1},
            tabs: [...d.querySelectorAll('[role=tab]')].map(t => t.textContent.trim()),
            lock: li && li.textContent.includes('🔒'), drag: li && li.getAttribute('draggable')} }""",
        DLG,
    )
    check("🔒" in info["title"], f"{w} {lang}: 🔒 в заголовке окна")
    check(PLAQUE in info["plaque"], f"{w} {lang}: плашка § 312j")
    f = info["field"] or {}
    check(
        f.get("ro") and f.get("name") is None and not f.get("form"),
        f"{w} {lang}: подпись кнопки — только чтение, без name и вне формы",
    )
    check(f.get("whole"), f"{w} {lang}: подпись кнопки видна целиком (перенос)")
    check(len(info["tabs"]) == 2, f"{w} {lang}: две вкладки ({info['tabs']})")
    check(info["lock"] and info["drag"] is None, f"{w} {lang}: в списке 🔒, без перетаскивания")
    pg.screenshot(path=f"{out}/m36-pinned-{w}-{lang}.png")
    pg.goto(f"{host}/dashboard/site/aufbau/?seite=product")
    kauf = pg.locator('[data-schema-pinned="__kauf"]')
    check(
        kauf.count() == 1 and kauf.get_attribute("draggable") is None,
        f"{w} {lang}: «Kaufen» закреплена, без ручки",
    )


def nojs(b, host, out):
    for w, h, lang in ((1440, 900, "de"), (390, 844, "ru")):
        ctx = b.new_context(
            viewport={"width": w, "height": h}, java_script_enabled=False, locale=lang
        )
        pg = ctx.new_page()
        login(pg, host)
        pg.goto(f"{host}/dashboard/site/aufbau/?seite=text&block=__page")
        check(
            pg.locator("[data-schema-panel] button[value=window_done]").count() >= 1,
            f"без JS {w} {lang}: «Seite» — окно формами (Fertig)",
        )
        links = (
            pg.locator("[data-window-tabs] a").count()
            + pg.locator("[data-window-tabs] button").count()
        )
        check(links >= 1, f"без JS {w} {lang}: вкладки — ссылки/кнопки")
        pg.goto(f"{host}/dashboard/site/aufbau/?seite=text&block=bn1&wo=Brot")
        check(
            pg.locator("input[name=wo_add][value='category:brot']").count() == 1,
            f"без JS {w} {lang}: поиск «Wo zeigen» обычной формой",
        )
        pg.goto(f"{host}/dashboard/site/aufbau/?seite=cart&block=summary")
        check(
            pg.locator("#schema-legal-label[readonly]").count() == 1,
            f"без JS {w} {lang}: поле подписи только для чтения",
        )
        sw = pg.evaluate("() => document.documentElement.scrollWidth <= innerWidth")
        check(sw, f"без JS {w} {lang}: без горизонтальной прокрутки")
        pg.screenshot(path=f"{out}/m36-nojs-{w}-{lang}.png", full_page=True)
        ctx.close()


def run(out: str, port: str) -> int:
    from playwright.sync_api import sync_playwright

    os.makedirs(out, exist_ok=True)
    host = f"http://{SLUG}.{BASE}:{port}"
    with sync_playwright() as p:
        b = p.chromium.launch(
            executable_path=CHROME, args=[f"--host-resolver-rules=MAP *.{BASE} 127.0.0.1"]
        )
        for w, h, lang in ((1440, 900, "de"), (390, 844, "ru")):
            print(f"— {w}px {lang}")
            shell(RESET)
            ctx = b.new_context(viewport={"width": w, "height": h}, locale=lang)
            pg = ctx.new_page()
            errs = []
            pg.on("pageerror", lambda e, errs=errs: errs.append(str(e)))
            login(pg, host)
            page_window(pg, host, out, w, lang)
            banner_window(pg, host, out, w, lang)
            pinned(pg, host, out, w, lang)
            check(not errs, f"{w} {lang}: без ошибок JS ({errs[:2]})")
            ctx.close()
        shell(RESET)
        nojs(b, host, out)
        b.close()
    print(f"{ok} ✓, {len(fail)} ✗")
    return 1 if fail else 0


if __name__ == "__main__":
    if "--setup" in sys.argv:
        print(shell(SETUP).strip().splitlines()[-1])
        sys.exit(0)
    sys.exit(run(sys.argv[1], sys.argv[2] if len(sys.argv) > 2 else "8063"))
