"""FB-33 M2b-2a: стенд «FAQ на детальных» — услуга и событие × 3 вида × FAQ пуст/2/6,
1440/390, de/ru, без JS; главная — та же при любом виде блока детальных.

    DB_NAME=<стенд-БД> python manage.py runserver 0.0.0.0:8041 --settings=config.settings.stand --noreload
    DB_NAME=<стенд-БД> uv run python scripts/fb33_m2b2a_faq_stand.py --setup        # один раз
    DB_NAME=<стенд-БД> uv run --with playwright==1.55.0 python scripts/fb33_m2b2a_faq_stand.py <папка> [порт]

Печатает по каждой странице: ширину прокрутки, есть ли блок FAQ, число вопросов, FAQPage,
заглушку превью; в конце — ✓/✗ проверок. Скриншоты — в <папку>. Не входит в CI.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys

CHROME = "/opt/pw-browsers/chromium"
BASE = "siteadaptor.de"
SLUG = "fq2a"
PASSWORD = "Stand-Passwort-123"
FAQ6 = [
    {"q": "Wie lange dauert ein Termin?", "a": "Je nach Leistung 30 bis 90 Minuten."},
    {"q": "Kann ich ohne Termin kommen?", "a": "Ja, wenn ein Platz frei ist."},
    {"q": "Wie kann ich bezahlen?", "a": "Bar, mit Karte oder per Überweisung."},
    {"q": "Gibt es Parkplätze?", "a": "Direkt vor dem Haus."},
    {"q": "Kann ich absagen?", "a": "Bis 24 Stunden vorher kostenlos."},
    {"q": "Gibt es Gutscheine?", "a": "Ja, im Laden und online."},
]
VIEWS = ("", "list", "twocol")
COUNTS = (0, 2, 6)

SETUP = f"""
from datetime import timedelta
from django.utils import timezone
from django_tenants.utils import tenant_context
from apps.tenants.models import Domain, Tenant
from apps.tenants.services import create_business
from apps.tenants import onboarding
for old in Tenant.objects.filter(schema_name={SLUG!r}):
    old.delete(force_drop=True)
from django.db import connection
with connection.cursor() as c:
    c.execute("DROP SCHEMA IF EXISTS {SLUG} CASCADE")
tenant, _ = create_business(business_name="Salon Stand FAQ", slug={SLUG!r},
    business_type="friseur", city="Haan", email="owner@{SLUG}.test", password={PASSWORD!r})
tenant.published_at = timezone.now()
tenant.enabled_locales = ["de", "ru"]
tenant.disabled_modules = [m for m in (tenant.disabled_modules or []) if m not in ("events", "booking")]
tenant.save(update_fields=["published_at", "enabled_locales", "disabled_modules"])
onboarding.mark_complete(tenant)
from apps.tenants import siteconfig
cfg = dict(tenant.site_config or {{}})
cfg["sections"] = [{{**s, "enabled": True}} if s.get("key") == "faq" else s
                   for s in siteconfig.normalize(cfg)["sections"]]  # FAQ главной — для сверки
tenant.site_config = cfg
tenant.save(update_fields=["site_config"])
Domain.objects.update_or_create(domain="{SLUG}.{BASE}", defaults={{"tenant": tenant, "is_primary": True}})
with tenant_context(tenant):
    from apps.booking.models import Service
    from apps.events.models import Event
    Service.objects.create(name="Balayage", description="Strähnen von Hand gemalt.",
        duration_minutes=150, price_cents=12900, is_active=True)
    Event.objects.create(title="Haarpflege-Abend", description="Tipps vom Team.",
        starts_at=timezone.now() + timedelta(days=10), status=Event.STATUS_PUBLISHED)
print("READY")
"""

STATE = """
import json
from django_tenants.utils import tenant_context
from apps.tenants.models import Tenant
tenant = Tenant.objects.get(schema_name=%(slug)r)
cfg = dict(tenant.site_config or {})
cfg["faq"] = json.loads(%(faq)r)
style = %(style)r
narrow = %(narrow)r
block = lambda host: {"key": "faq_ref", "id": "faq-" + host, "data": {"style": style} if style else {},
                      **({"width": "w12"} if narrow else {})}
text = lambda host: {"key": "text", "id": "txt-" + host, "width": "w12",
                     "data": {"title": "Gut zu wissen", "body": "Bitte 5 Minuten vorher da sein."}}
blocks = dict(cfg.get("page_blocks") or {})
blocks["service_detail"] = [text("service"), block("service")] if narrow else [block("service")]
blocks["event_detail"] = [text("event"), block("event")] if narrow else [block("event")]
cfg["page_blocks"] = blocks
tenant.site_config = cfg
tenant.save(update_fields=["site_config"])
with tenant_context(tenant):
    from apps.booking.models import Service
    from apps.events.models import Event
    print("URLS", Service.objects.get().pk, Event.objects.get().pk)
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


def set_state(style: str, n: int, narrow: bool = False) -> tuple[str, str]:
    code = STATE % {"slug": SLUG, "faq": json.dumps(FAQ6[:n]), "style": style, "narrow": narrow}
    line = next(x for x in shell(code).splitlines() if x.startswith("URLS"))
    _tag, service, event = line.split()
    return f"/leistung/{service}/", f"/veranstaltung/{event}/"


def _home_norm(html: str) -> str:
    html = re.sub(r'name="csrfmiddlewaretoken" value="[^"]+"', "", html)
    html = re.sub(r'nonce="[^"]+"', "", html)
    return re.sub(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", "UUID", html)


def run(out: str, port: str) -> int:
    from playwright.sync_api import sync_playwright

    os.makedirs(out, exist_ok=True)
    fails, homes = [], {}
    host = f"http://{SLUG}.{BASE}:{port}"
    with sync_playwright() as p:
        b = p.chromium.launch(
            executable_path=CHROME, args=[f"--host-resolver-rules=MAP *.{BASE} 127.0.0.1"]
        )
        for style in VIEWS:
            for n in COUNTS:
                urls = dict(zip(("service", "event"), set_state(style, n), strict=True))
                for lang in ("de", "ru"):
                    ctx = b.new_context(java_script_enabled=False)
                    pg = ctx.new_page()
                    pg.goto(f"{host}/?hl={lang}")  # кука языка витрины
                    for w, h in ((1440, 900), (390, 844)):
                        pg.set_viewport_size({"width": w, "height": h})
                        for kind, url in urls.items():
                            pg.goto(host + url, wait_until="load")
                            html = pg.content()
                            sec = pg.locator(f'[data-sf-section="faq-{kind}"]')
                            qs = sec.locator("[data-edit$='.q']").count()
                            ld = html.count('"@type":"FAQPage"')
                            sw = pg.evaluate("document.documentElement.scrollWidth")
                            name = f"{kind}-{style or 'akkordeon'}-{n}-{lang}-{w}"
                            pg.screenshot(path=f"{out}/{name}.png", full_page=True)
                            ok = (
                                sw <= w and ld == 0 and qs == n and (sec.count() == (1 if n else 0))
                            )
                            ok = ok and "data-faq-empty" not in html
                            print(
                                name,
                                "scrollW",
                                sw,
                                "block",
                                sec.count(),
                                "q",
                                qs,
                                "ld",
                                ld,
                                "✓" if ok else "✗",
                            )
                            if not ok:
                                fails.append(name)
                        pg.goto(host + "/", wait_until="load")
                        home = pg.content()
                        homes.setdefault((n, lang, w), set()).add(_home_norm(home))
                        if n and home.count('"@type":"FAQPage"') != 1:
                            fails.append(f"home-ld-{style}-{n}-{lang}-{w}")
                        if style == "" and n == 6:
                            pg.screenshot(path=f"{out}/home-{n}-{lang}-{w}.png", full_page=True)
                    ctx.close()
        # пустой FAQ в узком ряду рядом с текстом: на сайте — только текст, в превью — заглушка
        urls = dict(zip(("service", "event"), set_state("", 0, narrow=True), strict=True))
        ctx = b.new_context(java_script_enabled=False)
        pg = ctx.new_page()
        for w, h in ((1440, 900), (390, 844)):
            pg.set_viewport_size({"width": w, "height": h})
            for kind, url in urls.items():
                for mode, q in (("live", ""), ("preview", "?preview=1&stand=saved")):
                    pg.goto(host + url + q, wait_until="load")
                    html = pg.content()
                    sw = pg.evaluate("document.documentElement.scrollWidth")
                    stub = pg.locator("[data-faq-empty]").count()
                    text = "Gut zu wissen" in html
                    name = f"narrow-{kind}-{mode}-{w}"
                    pg.screenshot(path=f"{out}/{name}.png", full_page=True)
                    ok = sw <= w and text and stub == (1 if mode == "preview" else 0)
                    if mode == "live":
                        ok = ok and f'data-sf-section="faq-{kind}"' not in html
                    print(name, "scrollW", sw, "text", text, "stub", stub, "✓" if ok else "✗")
                    if not ok:
                        fails.append(name)
        ctx.close()
        b.close()
    same = all(len(v) == 1 for v in homes.values())
    print("home unchanged across detail views:", "✓" if same else "✗")
    if not same:
        fails.append("home-changed")
    print("FAILS", fails or "none")
    return 1 if fails else 0


if __name__ == "__main__":
    if sys.argv[1:2] == ["--setup"]:
        print(shell(SETUP).strip().splitlines()[-1])
        sys.exit(0)
    sys.exit(run(sys.argv[1], sys.argv[2] if len(sys.argv) > 2 else "8041"))
