"""M21.10: браузерный стенд «Seiten» = центр всех текстовых страниц + полный редактор.

Хаб (системные/правовые/свои) → правовой текст с автотекстом → новая страница:
панель (role=toolbar, roving tabindex), H4, выравнивание, разделитель, фото с
компьютера → окно фото (размер M, справа, описание, подпись), отмена, вставка из
буфера через белый список → витрина 1440/390 → цели меню.

    python manage.py runserver 0.0.0.0:8000 --settings=config.settings.stand
    uv run python scripts/text_pages_stand.py --setup     # один раз
    uv run python scripts/text_pages_stand.py

Не входит в CI (там нет браузера).
"""

from __future__ import annotations

import argparse
import io
import subprocess
import sys
import tempfile

CHROME = "/opt/pw-browsers/chromium"
BASE = "siteadaptor.de"
SLUG = "ptx"
PASSWORD = "Stand-Passwort-123"

SETUP = f"""
from django.utils import timezone
from apps.tenants.models import Domain, Tenant
from apps.tenants.services import create_business
from apps.tenants import onboarding
for old in Tenant.objects.filter(schema_name={SLUG!r}):
    old.delete(force_drop=True)
from django.db import connection
with connection.cursor() as c:
    c.execute("DROP SCHEMA IF EXISTS {SLUG} CASCADE")
tenant, _ = create_business(business_name="Stand Textseiten", slug={SLUG!r},
    business_type="online_shop", city="Haan", email="owner@{SLUG}.test", password={PASSWORD!r})
tenant.published_at = timezone.now()
cfg = dict(tenant.site_config or {{}})
cfg["about_text"] = "Seit 1998 in Haan.\\nTee & Kräuter."
tenant.site_config = cfg
tenant.save(update_fields=["published_at", "site_config"])
onboarding.mark_complete(tenant)
Domain.objects.update_or_create(domain="{SLUG}.{BASE}", defaults={{"tenant": tenant, "is_primary": True}})
print("READY")
"""


class Run:
    def __init__(self):
        self.ok, self.fail = 0, []

    def check(self, cond, label):
        (self.fail.append(label) if not cond else None)
        self.ok += bool(cond)
        print(("  ✓ " if cond else "  ✗ ") + label)


def _shell(code):
    out = subprocess.run(
        [sys.executable, "manage.py", "shell", "--settings=config.settings.stand", "-c", code],
        capture_output=True,
        text=True,
        check=False,
    )
    return out.stdout + out.stderr[-800:]


def _png() -> str:
    from PIL import Image

    buf = io.BytesIO()
    Image.new("RGB", (800, 500), (120, 160, 110)).save(buf, "PNG")
    f = tempfile.NamedTemporaryFile(suffix=".png", delete=False)
    f.write(buf.getvalue())
    f.close()
    return f.name


def main():  # noqa: PLR0915 — один линейный сценарий стенда
    ap = argparse.ArgumentParser()
    ap.add_argument("--setup", action="store_true")
    ap.add_argument("--port", type=int, default=8000)
    args = ap.parse_args()
    if args.setup:
        print(_shell(SETUP)[-300:])
        return
    from playwright.sync_api import sync_playwright

    run = Run()
    url = f"http://{SLUG}.{BASE}:{args.port}"
    with sync_playwright() as p:
        browser = p.chromium.launch(
            executable_path=CHROME, args=[f"--host-resolver-rules=MAP *.{BASE} 127.0.0.1"]
        )
        ctx = browser.new_context(viewport={"width": 1440, "height": 900}, locale="de-DE")
        page = ctx.new_page()
        errors = []
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.on("dialog", lambda d: errors.append("ALERT:" + d.message) or d.dismiss())
        page.goto(url + "/accounts/login/")
        page.fill("input[name=login]", f"owner@{SLUG}.test")
        page.fill("input[name=password]", PASSWORD)
        page.click("button[type=submit]")
        page.wait_for_load_state()

        print("Hub")
        page.goto(url + "/dashboard/site/seiten/")
        for slug in ("ueber-uns", "versand"):
            run.check(page.locator(f"[data-system-row={slug}]").count() == 1, f"системная: {slug}")
        for kind in ("impressum", "datenschutz", "widerruf", "agb"):
            run.check(page.locator(f"[data-legal-row={kind}]").count() == 1, f"правовая: {kind}")

        print("Über uns aus der Startseite")
        page.click("[data-system-row=ueber-uns] a.ui-btn")
        page.wait_for_load_state()
        run.check("Tee &amp; Kräuter" in page.content(), "заготовка из текста главной")
        page.click("button.ui-btn-primary")
        page.wait_for_load_state()
        run.check("/dashboard/site/seiten/" in page.url and "system" not in page.url, "сохранено")
        page.goto(url + "/ueber-uns/")
        run.check("Tee &amp; Kräuter" in page.content(), "/ueber-uns/ показывает текст")

        print("Impressum mit automatischem Text")
        page.goto(url + "/dashboard/site/seiten/recht/impressum/")
        page.click("[data-legal-fallback] summary")
        page.click("[data-take-fallback]")
        area = page.locator(".rte-area").first
        run.check("Stand Textseiten" in area.inner_text(), "автотекст подставлен в редактор")
        page.click("button.ui-btn-primary")
        page.wait_for_load_state()
        page.goto(url + "/dashboard/site/seiten/")
        run.check(
            "Eigener Text" in page.locator("[data-legal-row=impressum]").inner_text(),
            "Impressum: «Eigener Text»",
        )

        print("Editor")
        page.goto(url + "/dashboard/site/seiten/neu/")
        page.fill("input[name=title]", "Laden")
        bar = page.locator(".rte-bar[role=toolbar]")
        run.check(bar.count() == 1, "панель role=toolbar")
        run.check(page.locator('.rte-bar button[tabindex="0"]').count() == 1, "одна Tab-остановка")
        page.locator(".rte-bar button").first.focus()
        page.keyboard.press("ArrowRight")
        focused = page.evaluate("document.activeElement.getAttribute('data-rte-cmd')")
        run.check(focused == "h3", f"→ двигает фокус по панели ({focused})")
        area = page.locator(".rte-area")
        area.click()
        page.keyboard.type("Unser Laden")
        page.click(".rte-bar [data-rte-cmd=h4]")
        page.click(".rte-bar [data-rte-cmd=sf-right]")
        pressed = page.get_attribute(".rte-bar [data-rte-cmd=sf-right]", "aria-pressed")
        run.check(pressed == "true", "Rechtsbündig: aria-pressed")
        page.keyboard.press("End")
        page.keyboard.press("Enter")
        page.keyboard.type("Frischer Tee aus Haan.")
        page.click(".rte-bar [data-rte-cmd=hr]")
        with page.expect_file_chooser() as fc:
            page.click(".rte-bar [data-rte-cmd=insertImage]")
        fc.value.set_files(_png())
        page.wait_for_selector("[data-rte-pop]")
        run.check(page.locator("[data-rte-pop][role=dialog]").count() == 1, "окно фото открыто")
        focused = page.evaluate("document.activeElement.id || ''")
        run.check(focused.endswith("-alt"), "фокус — в поле описания")
        page.check("[data-rte-pop] input[value=md]")
        page.check("[data-rte-pop] input[value=right]")
        page.fill("[data-rte-pop] input[id$=-alt]", "Teeregal im Laden")
        page.fill("[data-rte-pop] input[id$=-cap]", "Unser Regal")
        page.keyboard.press("Escape")
        run.check(page.locator("[data-rte-pop]").count() == 0, "Esc закрывает окно")
        run.check(
            page.evaluate("document.activeElement.tagName") == "FIGURE", "фокус вернулся на фото"
        )
        # отмена изменения размера и повтор
        page.keyboard.press("Enter")
        page.check("[data-rte-pop] input[value=sm]")
        page.keyboard.press("Escape")
        area.press("Control+z")
        cls = page.evaluate("document.querySelector('.rte-area figure').className")
        run.check("sf-img-md" in cls, f"Strg+Z вернул размер M ({cls})")
        # вставка из буфера: стиль и onerror отбрасываются
        page.evaluate(
            """() => {
              const a = document.querySelector('.rte-area');
              a.focus();
              const dt = new DataTransfer();
              dt.setData('text/html', '<p style="color:red" onclick="x()">Kopiert</p><img src=x onerror="window.__pwn=1">');
              a.dispatchEvent(new ClipboardEvent('paste', {clipboardData: dt, bubbles: true, cancelable: true}));
            }"""
        )
        page.wait_for_timeout(300)
        run.check(not page.evaluate("window.__pwn"), "вставка: onerror не исполнился")
        html = page.evaluate("document.querySelector('.rte-area').innerHTML")
        run.check("Kopiert" in html and "style=" not in html, "вставка: текст есть, стилей нет")
        page.click("button.ui-btn-primary")
        page.wait_for_load_state()
        run.check("Seite angelegt" in page.content(), "сохранено")
        run.check(not errors, f"кабинет без JS-ошибок {errors[:2]}")

        print("Website")
        page.goto(url + "/seite/laden/")
        html = page.content()
        run.check('class="sf-img-md sf-float-right"' in html, "фото M справа")
        run.check('alt="Teeregal im Laden"' in html, "описание фото")
        run.check("<figcaption>Unser Regal</figcaption>" in html, "подпись")
        run.check('<h4 class="sf-right">' in html and "<hr>" in html, "H4 справа + разделитель")
        body = page.locator("[data-page-body]").inner_html()
        run.check(
            "contenteditable" not in body and "tabindex" not in body, "без атрибутов редактора"
        )
        fl = page.evaluate(
            "getComputedStyle(document.querySelector('[data-page-body] figure')).float"
        )
        run.check(fl == "right", f"1440: обтекание справа ({fl})")
        page.set_viewport_size({"width": 390, "height": 860})
        page.reload()
        fl = page.evaluate(
            "getComputedStyle(document.querySelector('[data-page-body] figure')).float"
        )
        run.check(fl == "none", f"390: без обтекания ({fl})")
        scroll = page.evaluate("document.documentElement.scrollWidth")
        run.check(scroll <= 392, f"390: без горизонтального скролла ({scroll})")
        page.set_viewport_size({"width": 1440, "height": 900})

        print("Menü")
        page.goto(url + "/dashboard/site/menu/")
        import json

        pages = json.loads(page.locator("#builder-data").text_content())["pages"]
        values = {p["value"] for p in pages}
        for key in ("shipping", "impressum", "privacy", "withdrawal", "agb"):
            run.check(key in values, f"цель меню: {key}")
        run.check(not errors, f"без JS-ошибок {errors[:2]}")
        browser.close()
    print(f"\n{run.ok} ✓, {len(run.fail)} ✗")
    sys.exit(1 if run.fail else 0)


if __name__ == "__main__":
    main()
