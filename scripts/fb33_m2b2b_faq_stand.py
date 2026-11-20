"""FB-33 M2b-2b: стенд «свои вопросы FAQ у объекта» — услуга, товар, номер, событие, тур с
блоком «FAQ» (`data.source=object`), 1440/390, de/ru, без JS; окно блока в «Seitenaufbau»:
выбор источника и свои вопросы на хосте объекта, подсказка и ссылки на общем хосте; правка
→ «Speichern» → вопросы у объекта.

    DB_NAME=<стенд-БД> python manage.py runserver 0.0.0.0:8062 --settings=config.settings.stand --noreload
    DB_NAME=<стенд-БД> uv run python scripts/fb33_m2b2b_faq_stand.py --setup        # один раз
    DB_NAME=<стенд-БД> uv run --with playwright==1.55.0 python scripts/fb33_m2b2b_faq_stand.py <папка> [порт]

Печатает по каждой проверке ✓/✗, скриншоты — в <папку>. Не входит в CI.
"""

from __future__ import annotations

import os
import subprocess
import sys

CHROME = "/opt/pw-browsers/chromium"
BASE = "siteadaptor.de"
SLUG = "fq2b"
PASSWORD = "Stand-Passwort-123"

SETUP = f"""
from datetime import timedelta
from decimal import Decimal
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
tenant, _ = create_business(business_name="Salon Stand Eigene FAQ", slug={SLUG!r},
    business_type="friseur", city="Haan", email="owner@{SLUG}.test", password={PASSWORD!r})
tenant.published_at = timezone.now()
tenant.enabled_locales = ["de", "ru"]
tenant.disabled_modules = []
tenant.save(update_fields=["published_at", "enabled_locales", "disabled_modules"])
onboarding.mark_complete(tenant)
Domain.objects.update_or_create(domain="{SLUG}.{BASE}", defaults={{"tenant": tenant, "is_primary": True}})
OWN = [
    {{"q": "Wie lange dauert Balayage?", "a": "Je nach Haarlänge 2,5 bis 3,5 Stunden, inklusive Schnitt und Föhnen."}},
    {{"q": "Muss ich mit gewaschenen Haaren kommen?", "a": "Nein, wir waschen vorher."}},
    {{"q": "Was kostet ein Nachfärben?", "a": "Ab 40 € — je nach Länge."}},
]
RU = [{{"q": "Сколько длится балаяж?"}}, {{"q": "Нужно ли мыть волосы?"}}, {{"q": "Сколько стоит подкрашивание?"}}]
with tenant_context(tenant):
    from apps.booking.models import Service
    from apps.catalog.models import Product
    from apps.events.models import Event, Tour
    from apps.stays.models import StayUnit
    Service.objects.all().delete(); Product.objects.all().delete()
    s = Service.objects.create(name="Balayage", description="Strähnen von Hand gemalt.",
        duration_minutes=150, price_cents=12900, is_active=True, faq=OWN, faq_i18n={{"ru": RU}})
    Service.objects.create(name="Haarschnitt", duration_minutes=30, price_cents=3900, is_active=True)
    p = Product.objects.create(name={{"de": "Pflegeöl"}}, base_price=Decimal("19.90"), is_active=True,
        faq=OWN[:2], faq_i18n={{"ru": RU[:2]}})
    u = StayUnit.objects.create(name="Gästezimmer", price_cents=8900, is_active=True, faq=OWN[:2])
    e = Event.objects.create(title="Haarpflege-Abend", starts_at=timezone.now() + timedelta(days=10),
        status=Event.STATUS_PUBLISHED, details={{"faq": OWN}}, details_i18n={{"ru": {{"faq": RU}}}})
    t = Tour.objects.create(title="Haar-Reise", slug="haar-reise", is_published=True, details={{"faq": OWN[:1]}})
    Event.objects.create(title="Juni-Tour", tour=t, starts_at=timezone.now() + timedelta(days=30),
        status=Event.STATUS_PUBLISHED)
    cfg = dict(tenant.site_config or {{}})
    own = lambda bid: {{"key": "faq_ref", "id": bid, "enabled": True, "data": {{"source": "object"}}}}
    blocks = dict(cfg.get("page_blocks") or {{}})
    for host in ("service_detail", "product_detail", "stay_detail", "event_detail"):
        blocks[host] = [own("own-" + host.split("_")[0])]
    blocks["service:" + s.pk.hex] = [own("own-balayage")]
    cfg["page_blocks"] = blocks
    tenant.site_config = siteconfig.normalize(cfg)
    tenant.save(update_fields=["site_config"])
    print("URLS", s.pk, s.pk.hex, p.pk, u.pk, e.pk)
print("READY")
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


URLS_CODE = f"""
from django_tenants.utils import tenant_context
from apps.tenants.models import Tenant
tenant = Tenant.objects.get(schema_name={SLUG!r})
with tenant_context(tenant):
    from apps.booking.models import Service
    from apps.catalog.models import Product
    from apps.events.models import Event
    from apps.stays.models import StayUnit
    s = Service.objects.get(name="Balayage")
    from apps.events.models import Tour
    print("URLS", s.pk, s.pk.hex, Product.objects.get().pk, StayUnit.objects.get().pk,
          Event.objects.get(title="Haarpflege-Abend").pk, Tour.objects.get().pk)
"""

FAQ_OF = f"""
from django_tenants.utils import tenant_context
from apps.tenants.models import Tenant
with tenant_context(Tenant.objects.get(schema_name={SLUG!r})):
    from apps.booking.models import Service
    s = Service.objects.get(name="Balayage")
    print("FAQ", [f["q"] for f in s.faq])
"""


def login(pg, host):
    pg.goto(host + "/accounts/login/")
    pg.fill("input[name=login]", f"owner@{SLUG}.test")
    pg.fill("input[name=password]", PASSWORD)
    pg.click("button[type=submit]")
    pg.wait_for_load_state()


def run(out: str, port: str) -> int:
    from playwright.sync_api import sync_playwright

    os.makedirs(out, exist_ok=True)
    line = next(x for x in shell(URLS_CODE).splitlines() if x.startswith("URLS"))
    _tag, spk, shex, ppk, upk, epk, tour_pk = line.split()
    pages = {
        "service": f"/leistung/{spk}/",
        "product": f"/sortiment/{ppk}/",
        "stay": f"/unterkunft/{upk}/",
        "event": f"/veranstaltung/{epk}/",
        "tour": "/tour/haar-reise/",
    }
    expect = {"service": 3, "product": 2, "stay": 2, "event": 3, "tour": 1}
    fails: list[str] = []
    host = f"http://{SLUG}.{BASE}:{port}"

    def check(name, ok, *info):
        print(name, *info, "✓" if ok else "✗")
        if not ok:
            fails.append(name)

    with sync_playwright() as p:
        b = p.chromium.launch(
            executable_path=CHROME, args=[f"--host-resolver-rules=MAP *.{BASE} 127.0.0.1"]
        )
        for lang in ("de", "ru"):
            ctx = b.new_context(java_script_enabled=False)
            pg = ctx.new_page()
            pg.goto(f"{host}/?hl={lang}")
            for w, h in ((1440, 900), (390, 844)):
                pg.set_viewport_size({"width": w, "height": h})
                for kind, url in pages.items():
                    pg.goto(host + url, wait_until="load")
                    html = pg.content()
                    own = pg.locator("[data-faq-own]")
                    blocks = own.count()
                    edit = own.first.locator("[data-edit]").count() if blocks else -1
                    ld = html.count('"@type":"FAQPage"')
                    sw = pg.evaluate("document.documentElement.scrollWidth")
                    text = own.first.inner_text() if blocks else ""
                    qs = (
                        own.first.locator("details, li, div > p.font-medium").count()
                        if blocks
                        else 0
                    )
                    tr = (
                        ("Сколько длится балаяж?" in text)
                        if lang == "ru" and kind == "service"
                        else True
                    )
                    pg.screenshot(path=f"{out}/{kind}-{lang}-{w}.png", full_page=True)
                    want_blocks = 2 if kind == "service" else 1  # услуга: общий хост + свой
                    check(
                        f"{kind}-{lang}-{w}",
                        sw <= w and blocks == want_blocks and edit == 0 and ld == 1
                        and qs == expect[kind] and tr,
                        "scrollW", sw, "blocks", blocks, "q", qs, "ld", ld, "edit", edit,
                    )  # fmt: skip
            ctx.close()
        # окно блока без JS (вкладка «Texte»)
        for w, h in ((1440, 900), (390, 844)):
            ctx = b.new_context(viewport={"width": w, "height": h}, java_script_enabled=False)
            pg = ctx.new_page()
            login(pg, host)
            code = f"service@service:{shex}"
            pg.goto(f"{host}/dashboard/site/aufbau/?seite={code}&block=own-balayage&tab=texte")
            html = pg.content()
            sw = pg.evaluate("document.documentElement.scrollWidth")
            pg.screenshot(path=f"{out}/window-object-{w}.png", full_page=True)
            check(
                f"window-object-{w}",
                sw <= w and "data-faq-source" in html and 'name="faq_scope" value="object"' in html
                and 'value="Wie lange dauert Balayage?"' in html and "data-faq-double" in html,
                "scrollW", sw,
            )  # fmt: skip
            pg.goto(f"{host}/dashboard/site/aufbau/?seite={code}&block=faq&tab=texte")
            html = pg.content()
            pg.screenshot(path=f"{out}/window-section-{w}.png", full_page=True)
            check(
                f"window-section-{w}",
                'value="Wie lange dauert Balayage?"' in html and "data-faq-source" not in html,
            )
            pg.goto(f"{host}/dashboard/site/aufbau/?seite=service&block=own-service&tab=texte")
            html = pg.content()
            pg.screenshot(path=f"{out}/window-shared-{w}.png", full_page=True)
            check(
                f"window-shared-{w}",
                'name="faq_scope" value="each"' in html
                and "data-faq-links" in html
                and 'name="faq_0_q"' not in html,
            )
            if w == 1440:
                # ревью: формы объектов — пары полей общего редактора с отпечатком (без JS)
                for name, path in (
                    ("form-event", f"/dashboard/events/{epk}/edit/"),
                    ("form-tour", "/dashboard/events/touren/" + tour_pk + "/"),
                    ("form-product", f"/catalog/products/{ppk}/edit/"),
                    ("form-stay", f"/dashboard/stays/units/{upk}/"),
                    ("form-service", f"/dashboard/booking/leistungen/{spk}/"),
                ):
                    pg.goto(host + path, wait_until="load")
                    html = pg.content()
                    pg.screenshot(path=f"{out}/{name}.png", full_page=True)
                    check(
                        name,
                        'name="faq_q_0"' in html and 'name="faq_base"' in html
                        and 'name="faq_text"' not in html,
                    )  # fmt: skip
                # правка → «Speichern»: второй вопрос наверх, на сайте — у услуги
                pg.goto(f"{host}/dashboard/site/aufbau/?seite={code}&block=own-balayage&tab=texte")
                pg.locator('#bw-form-faq button[name="faq_move"][value="0:down"]').click()
                pg.wait_for_load_state()
                pg.locator('button[name="op"][value="save"]').first.click()
                pg.wait_for_load_state()
                got = next(x for x in shell(FAQ_OF).splitlines() if x.startswith("FAQ"))
                check(
                    "save-moves-question",
                    "'Muss ich mit gewaschenen Haaren kommen?', 'Wie" in got,
                    got,
                )
            ctx.close()
        b.close()
    print("FAILS", fails or "none")
    return 1 if fails else 0


if __name__ == "__main__":
    if sys.argv[1:2] == ["--setup"]:
        print(shell(SETUP).strip().splitlines()[-1])
        sys.exit(0)
    sys.exit(run(sys.argv[1], sys.argv[2] if len(sys.argv) > 2 else "8062"))
