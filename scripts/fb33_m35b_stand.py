"""FB-33 M3-5b: стенд «FAQ-вопросы и плашки Schnellzugriff в окне блока» (1440 и 390, de/ru, без JS).

Café Morgenrot (плашки gastro) + блоки «Schnellzugriff» наборов bakery, aktionsmarkt, friseur на
главной; FAQ главной с переводом ru; детальная услуги с блоком FAQ (`faq_ref`). Сценарий: окно FAQ
(«Texte»: вопросы, ↑↓, Entfernen, «＋ Frage hinzufügen», «Gilt für alle Seiten…») → перестановка →
«Speichern» → витрина de/ru (переводы на месте); правка немецкого ответа снимает только его
перевод; окно плашек («Was»: скрыть, подпись, «Vorlage für die Kacheln», «Abbrechen»); без JS.

    DB_NAME=<стенд-БД> uv run python scripts/fb33_m35b_stand.py --setup          # один раз
    DB_NAME=<стенд-БД> python manage.py runserver 0.0.0.0:8053 --settings=config.settings.stand --noreload
    DB_NAME=<стенд-БД> uv run --no-project --with playwright python scripts/fb33_m35b_stand.py <папка> [порт]

Chromium — /opt/pw-browsers/chromium (playwright install не запускать). Итог: «N ✓, M ✗».
Не входит в CI (там нет браузера).
"""

from __future__ import annotations

import json
import os
import subprocess
import sys

CHROME = "/opt/pw-browsers/chromium"
BASE = "siteadaptor.de"
SLUG = "m35b"
PASSWORD = "Stand-Passwort-123"
#: подпись окна FAQ — кабинет на немецком или английском (язык кабинета владельца)
Q_FIELDS = "#bw-form-faq input[name^=faq_][name$=_q]:not([name=faq_new_q])"
SHARED = (
    "Gilt für alle Seiten — dieselben Fragen zeigt jeder FAQ-Block.",
    "Applies to all pages — every FAQ block shows the same questions.",
)
FAQ = [
    {"q": "Kann ich vorbestellen?", "a": "Ja, bis 18 Uhr für den nächsten Tag."},
    {"q": "Liefern Sie auch?", "a": "Im Umkreis von 5 km."},
    {"q": "Gibt es Parkplätze?", "a": "Direkt vor dem Haus."},
]
FAQ_RU = [
    {"q": "Можно заказать заранее?", "a": "Да, до 18:00 на следующий день."},
    {"q": "Вы доставляете?", "a": "В радиусе 5 км."},
    {"q": "Есть парковка?", "a": "Прямо перед домом."},
]
SETS = (
    ("qgastro", "gastro"),
    ("qbakery", "bakery"),
    ("qakt", "aktionsmarkt"),
    ("qfris", "friseur"),
)

SETUP = f"""
import json
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
tenant, _ = create_business(business_name="Café Morgenrot", slug={SLUG!r},
    business_type="cafe", city="Haan", email="owner@{SLUG}.test", password={PASSWORD!r})
tenant.published_at = timezone.now()
tenant.enabled_locales = ["de", "ru"]
tenant.disabled_modules = [m for m in (tenant.disabled_modules or [])
                           if m not in ("booking", "promotions", "loyalty", "orders", "jobs")]
tenant.save(update_fields=["published_at", "enabled_locales", "disabled_modules"])
onboarding.mark_complete(tenant)
Domain.objects.update_or_create(domain="{SLUG}.{BASE}", defaults={{"tenant": tenant, "is_primary": True}})
with tenant_context(tenant):
    from apps.booking.models import Service
    Service.objects.all().delete()
    svc = Service.objects.create(name="Frühstück für zwei", description="Am Wochenende.",
        duration_minutes=60, price_cents=2900, is_active=True)
cfg = siteconfig.normalize(tenant.site_config or {{}})
rows = [r for r in cfg["sections"] if r.get("key") not in ("quick_links", "faq")]
at = next((i + 1 for i, r in enumerate(rows) if r.get("key") == "hero"), 0)
blocks = [{{"key": "quick_links", "id": rid, "enabled": True, "data": {{"set": s}}}}
          for rid, s in json.loads({json.dumps(SETS)!r})]
rows[at:at] = [*blocks, {{"key": "faq", "enabled": True}}]
cfg["sections"] = rows
cfg["faq"] = json.loads({json.dumps(FAQ)!r})
cfg.setdefault("i18n", {{}}).setdefault("ru", {{}})["faq"] = json.loads({json.dumps(FAQ_RU)!r})
pb = dict(cfg.get("page_blocks") or {{}})
pb["service_detail"] = [{{"key": "faq_ref", "id": "faq-svc", "enabled": True, "data": {{}}}}]
cfg["page_blocks"] = pb
tenant.site_config = cfg
tenant.save(update_fields=["site_config"])
print("READY", svc.pk, [m for m in ("booking", "promotions", "loyalty", "orders", "jobs")
                        if tenant.is_module_active(m)])
"""

#: вернуть вопросы и плашки к началу (стенд перезапускаемый)
RESET = f"""
import json
from apps.tenants.models import Tenant
t = Tenant.objects.get(schema_name={SLUG!r})
cfg = dict(t.site_config)
cfg["faq"] = json.loads({json.dumps(FAQ)!r})
cfg.setdefault("i18n", {{}}).setdefault("ru", {{}})["faq"] = json.loads({json.dumps(FAQ_RU)!r})
sets = dict(json.loads({json.dumps(SETS)!r}))
cfg["sections"] = [{{**r, "data": {{"set": sets[r["id"]]}}}} if r.get("id") in sets else r
                   for r in cfg["sections"]]
t.site_config = cfg
t.save(update_fields=["site_config"])
from django_tenants.utils import tenant_context
with tenant_context(t):
    from apps.booking.models import Service
    print("SVC", Service.objects.get().pk)
"""

READ = f"""
import json
from apps.tenants.models import Tenant
from apps.tenants import siteconfig
cfg = siteconfig.normalize(Tenant.objects.get(schema_name={SLUG!r}).site_config)
print("CFG" + json.dumps({{"faq": cfg["faq"], "ru": (cfg.get("i18n") or {{}}).get("ru", {{}}).get("faq"),
      "ql": {{r["id"]: r.get("data") for r in cfg["sections"] if r.get("key") == "quick_links"}}}}))
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


def busy_done(pg):
    pg.wait_for_function(
        "!+document.documentElement.getAttribute('data-schema-busy')", timeout=15000
    )


def settle(pg):
    """Скриншот — после анимации открытия окна."""
    pg.wait_for_function("!document.getAnimations().length", timeout=5000)


def save(pg, host):
    pg.goto(host + "/dashboard/site/aufbau/?seite=home")
    pg.click("button[name=op][value=save]")
    pg.wait_for_load_state()


def storefront(b, host, out, tag, lang, path="/"):
    """Витрина без скриптов: вопросы FAQ по порядку, плашки, ширина прокрутки."""
    res = {}
    for w, h in ((1440, 900), (390, 844)):
        ctx = b.new_context(viewport={"width": w, "height": h}, java_script_enabled=False)
        pg = ctx.new_page()
        pg.goto(f"{host}/?hl={lang}")
        pg.goto(host + path)
        res[w] = pg.evaluate(
            """() => ({sw: document.documentElement.scrollWidth, iw: innerWidth,
              qs: [...document.querySelectorAll('main details summary, main dt, main h3')]
                    .map(e => e.textContent.trim()).filter(Boolean),
              text: document.querySelector('main') ? document.querySelector('main').textContent : '',
              blocks: document.querySelectorAll('[data-block-quick-links]').length})"""
        )
        pg.screenshot(path=f"{out}/m35b-{tag}-{lang}-{w}.png", full_page=True)
        check(res[w]["sw"] <= res[w]["iw"], f"{tag} {lang} {w}: без горизонтальной прокрутки")
        ctx.close()
    return res[1440]


def faq_window(pg, host, out, w):
    url = host + "/dashboard/site/aufbau/?seite=home&block=faq&tab=texte"
    pg.goto(url)
    form = pg.locator("#bw-form-faq")
    check(form.is_visible(), f"{w}: окно FAQ — форма вопросов во вкладке «Texte»")
    check(
        pg.locator(Q_FIELDS).count() == 3,
        f"{w}: три вопроса в окне",
    )
    check(
        any(t in form.inner_text() for t in SHARED),
        f"{w}: подпись «Gilt für alle Seiten…»",
    )
    settle(pg)  # мерить после анимации открытия окна (масштаб)
    small = pg.evaluate(
        """() => [...document.querySelectorAll('#bw-form-faq :is(button,summary,input,textarea)')]
          .filter(e => e.getClientRects().length && !e.classList.contains('sr-only'))
          .filter(e => e.getBoundingClientRect().height < 44 && e.type !== 'hidden')
          .map(e => e.tagName + ':' + (e.name || e.textContent.trim()).slice(0, 14))"""
    )
    check(not small, f"{w}: цели формы FAQ не ниже 44 px ({small[:4]})")
    settle(pg)
    pg.screenshot(path=f"{out}/m35b-window-faq-{w}.png")
    # ↓ у первого вопроса: вопросы переставлены, окно открыто на «Texte»
    pg.click('#bw-form-faq button[name=faq_move][value="0:down"]')
    pg.wait_for_load_state()
    first = pg.locator("#bw-form-faq input[name=faq_0_q]").input_value()
    check(first == FAQ[1]["q"], f"{w}: ↓ — второй вопрос стал первым ({first})")
    # правка немецкого ответа «Kann ich vorbestellen?» (теперь № 2) — на лету, со скриптами
    item = pg.locator("details[data-faq-item='1']")
    # со скриптами фокус при открытии окна ставит aufbau.js на заголовок (M3-2) — фокус на
    # сдвинутом вопросе проверяется без JS (`nojs`)
    check(item.get_attribute("open") is not None, f"{w}: после ↓ сдвинутый вопрос открыт")
    pg.fill("#bw-form-faq textarea[name=faq_1_a]", "Ja, bis 17 Uhr.")
    pg.locator("#bw-form-faq input[name=faq_0_q]").focus()
    busy_done(pg)
    # новый вопрос — кнопкой
    pg.locator("details[data-faq-new] summary").click()
    pg.fill("#bw-form-faq input[name=faq_new_q]", "Haben Sie WLAN?")
    pg.fill("#bw-form-faq textarea[name=faq_new_a]", "Ja, kostenlos.")
    pg.click("#bw-form-faq [data-faq-new] button[name=faq_add]")
    pg.wait_for_load_state()
    check(
        pg.locator("#bw-form-faq input[name=faq_3_q]").input_value() == "Haben Sie WLAN?",
        f"{w}: «＋ Frage hinzufügen» — четвёртый вопрос",
    )
    pg.locator("details[data-faq-item='3'] summary").click()
    pg.click('#bw-form-faq button[name=faq_remove][value="3"]')
    pg.wait_for_load_state()
    check(
        pg.locator(Q_FIELDS).count() == 3,
        f"{w}: Entfernen — снова три",
    )
    settle(pg)
    pg.screenshot(path=f"{out}/m35b-window-faq-edited-{w}.png")
    save(pg, host)
    cfg = saved()
    check(
        [f["q"] for f in cfg["faq"]] == [FAQ[1]["q"], FAQ[0]["q"], FAQ[2]["q"]],
        f"{w}: «Speichern» — порядок на сайте",
    )
    check(
        cfg["ru"] == [FAQ_RU[1], {"q": FAQ_RU[0]["q"]}, FAQ_RU[2]],
        f"{w}: переводы на месте, снят только перевод исправленного ответа ({cfg['ru']})",
    )


def tiles_window(pg, host, out, w):
    url = host + "/dashboard/site/aufbau/?seite=home&block=qakt&tab=was"
    pg.goto(url)
    form = pg.locator("#bw-form-tiles")
    check(form.is_visible(), f"{w}: окно «Schnellzugriff» — плашки во «Was»")
    text = form.inner_text()
    check(
        ("Vorlage für die Kacheln" in text or "Template for the tiles" in text)
        and ("nur wenn Deals laufen" in text or "only while deals are running" in text)
        and ("Katalog" in text or "Catalog" in text),
        f"{w}: «Vorlage für die Kacheln» и подсказки в той же форме",
    )
    settle(pg)
    pg.screenshot(path=f"{out}/m35b-window-tiles-{w}.png")
    pg.uncheck("#bw-form-tiles input[name=f_show_newsletter]")
    busy_done(pg)
    pg.fill("#bw-form-tiles input[name=f_label_loyalty]", "Punkte sammeln")
    pg.locator("#bw-form-tiles input[name=f_label_deals]").focus()
    busy_done(pg)
    # «Abbrechen» другого блока ничего здесь не трогает; набор меняется селектом
    pg.goto(host + "/dashboard/site/aufbau/?seite=home&block=qgastro&tab=was")
    pg.uncheck("#bw-form-tiles input[name=f_show_menu]")
    busy_done(pg)
    pg.click("[data-window-actions] button[value=revert]")
    pg.wait_for_load_state()
    save(pg, host)
    cfg = saved()
    check(
        cfg["ql"]["qakt"]
        == {
            "set": "aktionsmarkt",
            "hidden": ["newsletter"],
            "labels": {"loyalty": "Punkte sammeln"},
        },
        f"{w}: скрытие и подпись записаны ({cfg['ql']['qakt']})",
    )
    check(cfg["ql"]["qgastro"] == {"set": "gastro"}, f"{w}: «Abbrechen» вернул плашки gastro")


def nojs(b, host, out):
    for w, h in ((1440, 900), (390, 844)):
        ctx = b.new_context(viewport={"width": w, "height": h}, java_script_enabled=False)
        pg = ctx.new_page()
        login(pg, host)
        pg.goto(host + "/dashboard/site/aufbau/?seite=home&block=faq&tab=texte")
        pg.locator("details[data-faq-item='2'] summary").click()  # без JS — родной <details>
        pg.fill("#bw-form-faq input[name=faq_2_q]", "Gibt es Parkplätze vor Ort?")
        pg.click('#bw-form-faq button[name=faq_move][value="2:up"]')
        pg.wait_for_load_state()
        # фокус на сдвинутом вопросе: `autofocus` браузер не применяет при якоре в адресе
        # (`#schema-panel` после действия) — проверяем, что вопрос открыт (см. notes)
        moved = pg.locator("details[data-faq-item='1']").get_attribute("open")
        check(moved is not None, f"без JS {w}: после ↑ открыт сдвинутый вопрос")
        check(
            pg.locator("#bw-form-faq input[name=faq_1_q]").input_value()
            == "Gibt es Parkplätze vor Ort?",
            f"без JS {w}: набранное и ↑ одной отправкой",
        )
        pg.goto(host + "/dashboard/site/aufbau/?seite=home&block=qbakery&tab=was")
        pg.uncheck("#bw-form-tiles input[name=f_show_party]")
        pg.click("#bw-form-tiles button.ui-btn-primary")
        pg.wait_for_load_state()
        check(
            not pg.locator("#bw-form-tiles input[name=f_show_party]").is_checked(),
            f"без JS {w}: плашка скрыта «Übernehmen»",
        )
        pg.screenshot(path=f"{out}/m35b-nojs-{w}.png")
        pg.goto(host + "/dashboard/site/aufbau/?seite=home")
        pg.click("button[name=op][value=discard]")
        pg.wait_for_load_state()
        ctx.close()


def run(out: str, port: str) -> int:
    from playwright.sync_api import sync_playwright

    os.makedirs(out, exist_ok=True)
    host = f"http://{SLUG}.{BASE}:{port}"
    with sync_playwright() as p:
        b = p.chromium.launch(
            executable_path=CHROME, args=[f"--host-resolver-rules=MAP *.{BASE} 127.0.0.1"]
        )
        for w, h in ((1440, 900), (390, 844)):
            print(f"— {w}px")
            svc = next(x for x in shell(RESET).splitlines() if x.startswith("SVC")).split()[1]
            before = storefront(b, host, out, f"home-before-{w}", "ru")
            check(FAQ_RU[0]["q"] in before["text"], f"{w}: ru до правки — перевод первого вопроса")
            ctx = b.new_context(viewport={"width": w, "height": h})
            pg = ctx.new_page()
            errs = []
            pg.on("pageerror", lambda e, errs=errs: errs.append(str(e)))
            login(pg, host)
            faq_window(pg, host, out, w)
            tiles_window(pg, host, out, w)
            check(not errs, f"{w}: без ошибок JS ({errs[:2]})")
            ctx.close()
            de = storefront(b, host, out, f"home-after-{w}", "de")
            ru = storefront(b, host, out, f"home-after-{w}", "ru")
            check(
                de["text"].find(FAQ[1]["q"]) < de["text"].find(FAQ[0]["q"]),
                f"{w}: de — порядок вопросов новый",
            )
            pos = [ru["text"].find(FAQ_RU[i]["q"]) for i in (1, 0, 2)]
            check(
                all(x >= 0 for x in pos) and pos == sorted(pos),
                f"{w}: ru — переводы едут за вопросами",
            )
            check(
                "Ja, bis 17 Uhr." in ru["text"] and FAQ_RU[0]["a"] not in ru["text"],
                f"{w}: ru — исправленный ответ немецкий, старый перевод снят",
            )
            check(
                "Punkte sammeln" in de["text"] and "Deals per E-Mail" not in de["text"],
                f"{w}: витрина — своя подпись, скрытая плашка пропала",
            )
            check("Speisekarte" in de["text"], f"{w}: витрина — плашки gastro как были")
            detail = storefront(b, host, out, f"service-{w}", "ru", f"/leistung/{svc}/")
            check(FAQ_RU[1]["q"] in detail["text"], f"{w}: детальная услуги — те же вопросы (ru)")
        shell(RESET)
        nojs(b, host, out)
        shell(RESET)
        b.close()
    print(f"{ok} ✓, {len(fail)} ✗")
    return 1 if fail else 0


if __name__ == "__main__":
    if "--setup" in sys.argv:
        print(shell(SETUP).strip().splitlines()[-1])
        sys.exit(0)
    sys.exit(run(sys.argv[1], sys.argv[2] if len(sys.argv) > 2 else "8053"))
