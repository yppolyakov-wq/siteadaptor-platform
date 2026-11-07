"""AIS-W W4-2: браузерный стенд шага «Angebot prüfen» (Playwright, Chromium) — 5 типов × телефон.

Пять бизнесов (`--setup` создаёт): Bäckerei (образцы → проверка → двойная отправка без дублей),
Friseur (услуга с длительностью → мастер на имя владельца), Pension (номера → фото),
Events (прошедшая дата — ошибка строки → исправление), Sonstiges («Wie verkaufen Sie?»).
На каждой странице: без JS-ошибок и горизонтального скролла, телефон 390 px.

    python manage.py runserver 0.0.0.0:8000 --settings=config.settings.stand
    uv run python scripts/wizard_v4_pruefen_stand.py --setup     # один раз
    uv run --with playwright==1.55.0 python scripts/wizard_v4_pruefen_stand.py

Хосты `<slug>.siteadaptor.de` направляются на локальный сервер правилом резолвера Chromium.
Не входит в CI (там нет браузера).
"""

from __future__ import annotations

import argparse
import base64
import subprocess
import sys
import tempfile

CHROME = "/opt/pw-browsers/chromium"
BASE = "siteadaptor.de"
PASSWORD = "Stand-Passwort-123"
PERSONAS = {
    "pbaeck": "bakery",
    "pfris": "friseur",
    "photel": "hotel",
    "pevent": "events",
    "pother": "other",
    "ppdf": "bakery",
}
# 1×1 PNG — фото номера.
PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=="
)

SETUP = """
from apps.tenants.models import Domain, Tenant
from apps.tenants.services import create_business
from apps.tenants import onboarding

for slug, btype in {personas!r}.items():
    Tenant.objects.filter(schema_name=slug).delete()
    tenant, _ = create_business(business_name=f"Stand {{btype}}", slug=slug,
        business_type=btype, city="Hilden", email=f"owner@{{slug}}.test", password={password!r})
    tenant.published_at = None
    tenant.site_config = {{**(tenant.site_config or {{}}), "onboarding": {{"v": 2, "flow": "v4"}}}}
    tenant.save(update_fields=["published_at", "site_config"])
    onboarding.goto(tenant, "pruefen")
    Domain.objects.update_or_create(domain=f"{{slug}}.{base}",
        defaults={{"tenant": tenant, "is_primary": True}})
print("READY")
"""

COUNT = """
from django_tenants.utils import schema_context
with schema_context({slug!r}):
    from apps.catalog.models import Product
    from apps.booking.models import Resource, Service
    from apps.stays.models import StayUnit
    from apps.events.models import Event
    print("COUNT", Product.objects.count(), Service.objects.count(),
          Resource.objects.filter(type="staff").count(), StayUnit.objects.count(),
          Event.objects.count())
"""


RESET = """
from django_tenants.utils import schema_context
from apps.tenants.models import Tenant
from apps.tenants import onboarding
for slug in {slugs!r}:
    with schema_context(slug):
        from apps.catalog.models import Product
        from apps.booking.models import Resource, Service
        from apps.stays.models import StayUnit
        from apps.events.models import Event
        Product.objects.all().delete()
        Service.objects.all().delete(); Resource.objects.all().delete()
        StayUnit.objects.all().delete(); Event.objects.all().delete()
    t = Tenant.objects.get(schema_name=slug)
    t.site_config = {{**(t.site_config or {{}}), "onboarding": {{"v": 2, "flow": "v4"}}}}
    t.save(update_fields=["site_config"])
    onboarding.goto(t, "pruefen")
print("RESET")
"""


class Run:
    def __init__(self):
        self.ok = 0
        self.fail = []

    def check(self, cond, label):
        if cond:
            self.ok += 1
            print(f"  ✓ {label}")
        else:
            self.fail.append(label)
            print(f"  ✗ {label}")


def _shell(code: str) -> str:
    out = subprocess.run(
        [sys.executable, "manage.py", "shell", "--settings=config.settings.stand", "-c", code],
        capture_output=True,
        text=True,
        check=False,
    )
    return out.stdout + out.stderr[-800:]


def counts(slug: str) -> list[int]:
    line = next(
        (x for x in _shell(COUNT.format(slug=slug)).splitlines() if x.startswith("COUNT")), ""
    )
    return [int(x) for x in line.split()[1:]] or [-1] * 5


def _health(run, page, errors, label, width=390):
    scroll = page.evaluate("document.documentElement.scrollWidth")
    run.check(scroll <= width + 2, f"{label}: без горизонтального скролла ({scroll}px)")
    run.check(not errors, f"{label}: без JS-ошибок {errors[:2]}")
    errors.clear()


def _login(browser, slug, port):
    url = f"http://{slug}.{BASE}:{port}"
    ctx = browser.new_context(viewport={"width": 390, "height": 900}, locale="de-DE")
    page = ctx.new_page()
    errors = []
    page.on("pageerror", lambda e: errors.append(str(e)))
    page.goto(url + "/accounts/login/")
    page.fill("input[name=login]", f"owner@{slug}.test")
    page.fill("input[name=password]", PASSWORD)
    page.click("button[type=submit]")
    page.goto(url + "/dashboard/setup/?step=pruefen")
    return ctx, page, errors, url


def _check(page):
    page.click("[data-pruefen-preview]")
    page.wait_for_load_state()


def bakery(run, browser, port):
    print("Bäckerei")
    ctx, page, errors, url = _login(browser, "pbaeck", port)
    run.check(page.locator("[data-pruefen-form]").count() == 1, "шаг «Angebot prüfen»")
    _health(run, page, errors, "Eingabe")
    page.click("button[value=offer_examples]")
    page.wait_for_load_state()
    run.check("Roggenbrot" in page.input_value("#id_pruefen_text"), "образцы в поле")
    run.check(counts("pbaeck")[0] == 0, "образцы базу не трогают")
    _check(page)
    rows = page.locator("[data-pruefen-row]").count()
    run.check(rows >= 5, f"таблица проверки: {rows} строк")
    _health(run, page, errors, "Prüfen")
    page.fill("input[name=row_0_price]", "3,90")
    # Двойное нажатие: две одинаковые отправки подряд — позиции создаются один раз.
    page.evaluate(
        """async () => {
          const form = document.querySelector('[data-pruefen-review]');
          const data = new FormData(form); data.set('action', 'offer_confirm');
          await Promise.all([1, 2].map(() =>
            fetch(form.getAttribute('action') || location.href, {method: 'POST', body: data, credentials: 'same-origin'})));
        }"""
    )
    created = counts("pbaeck")[0]
    run.check(created == rows, f"двойная отправка: {created} товаров (строк {rows})")
    page.goto(url + "/dashboard/setup/?step=pruefen")
    run.check(page.locator("[data-pruefen-done]").count() == 1, "«Schon angelegt» показан")
    _health(run, page, errors, "Schon angelegt")
    ctx.close()


def friseur(run, browser, port):
    print("Friseur")
    ctx, page, errors, url = _login(browser, "pfris", port)
    page.fill("#id_pruefen_text", "Herrenhaarschnitt — 30 Min — 26 €\nFärben — 9,50")
    _check(page)
    run.check(page.locator("[data-pruefen-error]").count() == 1, "строка без длительности — ошибка")
    page.click("[data-pruefen-confirm]")
    page.wait_for_load_state()
    body = page.content()
    run.check("Mitarbeiter" in body, "сообщение о мастере")
    c = counts("pfris")
    run.check(c[1] == 1 and c[2] == 1, f"1 услуга и 1 мастер ({c[1]}, {c[2]})")
    _health(run, page, errors, "Termine")
    ctx.close()


def pension(run, browser, port):
    print("Pension")
    ctx, page, errors, url = _login(browser, "photel", port)
    page.click("button[value=offer_examples]")
    page.wait_for_load_state()
    _check(page)
    page.click("[data-pruefen-confirm]")
    page.wait_for_load_state()
    run.check(page.locator("[data-pruefen-room]").count() >= 3, "номера в списке")
    run.check("ohne Foto" in page.content(), "бейдж «ohne Foto»")
    _health(run, page, errors, "Zimmer")
    with tempfile.NamedTemporaryFile(suffix=".png") as tmp:
        tmp.write(PNG)
        tmp.flush()
        form = page.locator("[data-pruefen-photo]").first
        form.locator("input[type=file]").set_input_files(tmp.name)
        form.locator("button").click()
        page.wait_for_load_state()
    run.check("mit Foto" in page.content(), "фото сохранено — «mit Foto»")
    _health(run, page, errors, "Zimmer + Foto")
    ctx.close()


def events(run, browser, port):
    print("Events")
    ctx, page, errors, url = _login(browser, "pevent", port)
    page.fill("#id_pruefen_text", "Konzert — 01.01.2020 19:00 — 25 €")
    _check(page)
    run.check(page.locator("[data-pruefen-error]").count() == 1, "прошедшая дата — ошибка")
    page.fill("input[name=row_0_starts_at]", "20.12.2030 19:00")
    page.check("input[name=row_0_on]")
    page.click("[data-pruefen-confirm]")
    page.wait_for_load_state()
    run.check(counts("pevent")[4] == 1, "событие создано после правки даты")
    _health(run, page, errors, "Tickets")
    ctx.close()


def other(run, browser, port):
    print("Sonstiges")
    ctx, page, errors, url = _login(browser, "pother", port)
    run.check(
        page.locator("details[data-pruefen-directions][open]").count() == 1,
        "«Wie verkaufen Sie?» открыт",
    )
    _health(run, page, errors, "Richtung")
    page.check("input[name=direction][value=termine]")
    page.click("button[value=offer_directions]")
    page.wait_for_load_state()
    run.check(
        page.locator("input[name=kind][value=termine]").count() == 1
        or page.locator("input[type=hidden][name=kind][value=termine]").count() == 1,
        "Termine доступны для ввода",
    )
    if page.locator("input[type=radio][name=kind][value=termine]").count():
        page.check("input[type=radio][name=kind][value=termine]")
    page.fill("#id_pruefen_text", "Beratung — 60 Min — 80 €")
    _check(page)
    page.click("[data-pruefen-confirm]")
    page.wait_for_load_state()
    run.check(counts("pother")[1] == 1, "услуга создана")
    _health(run, page, errors, "Sonstiges")
    ctx.close()


def _menu_pdf() -> bytes:
    import io

    from reportlab.lib.pagesizes import A4
    from reportlab.pdfgen import canvas

    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    for y, line in enumerate(
        [
            "Backhaus — Preisliste",
            "Tel. 02103 123456",
            "Roggenbrot ....... 3,50 €",
            "Dinkelbrot 4,20",
            "Öffnungszeiten Mo–Fr 7–18",
        ]
    ):
        c.drawString(60, 800 - 20 * y, line)
    c.save()
    return buf.getvalue()


def pdf(run, browser, port):
    """AIS-4: PDF без ИИ → правила → таблица; нужен Celery-воркер (`celery -A config worker`)."""
    import time

    print("PDF (Bäckerei)")
    ctx, page, errors, url = _login(browser, "ppdf", port)
    block = page.locator("[data-pruefen-scan]")
    run.check(block.count() == 1, "блок PDF виден без ИИ")
    accept = page.get_attribute("[data-pruefen-scan-file]", "accept")
    run.check(accept == "application/pdf", f"без ИИ только PDF ({accept})")
    with tempfile.NamedTemporaryFile(suffix=".pdf") as tmp:
        tmp.write(_menu_pdf())
        tmp.flush()
        page.set_input_files("[data-pruefen-scan-file]", tmp.name)
        page.click("[data-pruefen-scan-start]")
        page.wait_for_load_state()
    _health(run, page, errors, "PDF wird gelesen")
    for _ in range(30):
        if page.locator("[data-pruefen-scan-wait]").count() == 0:
            break
        status = page.text_content("[data-pruefen-scan-status]") or ""
        if "ist gelesen" in status:
            page.click("[data-pruefen-scan-apply]")
            page.wait_for_load_state()
            break
        time.sleep(1)
        page.reload()
    rows = page.locator("[data-pruefen-row]").count()
    run.check(rows == 2, f"из PDF две строки с ценой ({rows})")
    run.check(page.locator("[data-pruefen-from-pdf]").count() == 1, "пометка «Aus der PDF»")
    run.check(counts("ppdf")[0] == 0, "PDF базу не трогает")
    _health(run, page, errors, "Prüfen aus PDF")
    ctx.close()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--setup", action="store_true")
    args = parser.parse_args()
    if args.setup:
        print(_shell(SETUP.format(personas=PERSONAS, password=PASSWORD, base=BASE))[-600:])
        return
    from playwright.sync_api import sync_playwright  # глобальный Playwright, не из venv

    print(_shell(RESET.format(slugs=list(PERSONAS)))[-200:].strip().splitlines()[-1:])
    run = Run()
    with sync_playwright() as p:
        browser = p.chromium.launch(
            executable_path=CHROME, args=[f"--host-resolver-rules=MAP *.{BASE} 127.0.0.1"]
        )
        for persona in (bakery, friseur, pension, events, other, pdf):
            persona(run, browser, args.port)
        browser.close()
    print(f"\n{run.ok} ok, {len(run.fail)} fail")
    for f in run.fail:
        print("  FAIL:", f)
    sys.exit(1 if run.fail else 0)


if __name__ == "__main__":
    main()
