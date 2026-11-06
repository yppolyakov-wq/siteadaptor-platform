"""AIS-5: стенд «🌐 Übersetzen» в форме товара (Python-Playwright, не входит в CI).

Нужен сервер с ИИ на фейковом маршруте, где «перевод» = «EN <текст>» (настройки стенда —
в docs/ais-5-translate-plan-2026-11-06.md), и тенант с языками de+en и владельцем
(сквозной стенд мастера создаёт `e2ebaeck`).

    uv run --with playwright==1.55.0 python scripts/ais5_translate_stand.py --port 8001

Проверяет: кнопка видна только на не-базовом языке; пустые поля заполняются, заполненные
владельцем — нет; отказ пост-проверки оставляет поле пустым; Save пишет перевод, уход
без Save — ничего; 390 px без горизонтального скролла и без JS-ошибок.
"""

from __future__ import annotations

import argparse
import sys

CHROME = "/opt/pw-browsers/chromium"
BASE = "siteadaptor.de"


def _saved_description(slug: str, name: str) -> str:
    import subprocess

    code = (
        "from django_tenants.utils import schema_context\n"
        "from apps.catalog.models import Product\n"
        f"with schema_context({slug!r}):\n"
        f"    p = Product.objects.filter(name__de={name!r}).order_by('-pk').first()\n"
        "    print('DESC=' + ((p.description or {}).get('en', '') if p else 'NONE'))\n"
    )
    out = subprocess.run(
        [sys.executable, "manage.py", "shell", "--settings=config.settings.stand", "-c", code],
        capture_output=True,
        text=True,
        check=False,
    ).stdout
    line = next((x for x in out.splitlines() if x.startswith("DESC=")), "DESC=?")
    return line[5:]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=8001)
    parser.add_argument("--slug", default="e2ebaeck")
    parser.add_argument("--password", default="Stand-Passwort-123")
    args = parser.parse_args()
    from playwright.sync_api import sync_playwright

    url = f"http://{args.slug}.{BASE}:{args.port}"
    ok, fail = 0, []

    def check(cond, label):
        nonlocal ok
        if cond:
            ok += 1
            print(f"  ✓ {label}")
        else:
            fail.append(label)
            print(f"  ✗ {label}")

    with sync_playwright() as p:
        browser = p.chromium.launch(
            executable_path=CHROME, args=[f"--host-resolver-rules=MAP *.{BASE} 127.0.0.1"]
        )
        for width in (1440, 390):
            print(f"\nProdukt · {width}px")
            ctx = browser.new_context(viewport={"width": width, "height": 900}, locale="de-DE")
            page = ctx.new_page()
            errors = []
            page.on("pageerror", lambda e, errs=errors: errs.append(str(e)))
            page.goto(url + "/accounts/login/")
            page.fill("input[name=login]", f"owner@{args.slug}.test")
            page.fill("input[name=password]", args.password)
            page.click("button[type=submit]")
            page.wait_for_load_state()
            page.goto(url + "/catalog/products/new/")
            btn = page.locator("[data-i18n-translate]")
            check(btn.count() == 1 and not btn.is_visible(), "кнопка скрыта на базовом языке")
            page.fill("input[name=name_de]", f"Stand Brezel {width}")
            page.locator("#id_description_de + * .rte-area").fill("Frische Brezel BAD")
            page.fill("input[name=base_price]", "1,50")
            page.select_option("[data-i18n-select]", "en")
            check(btn.is_visible(), "кнопка видна на «en»")
            btn.click()
            page.wait_for_function(
                "document.querySelector('[data-i18n-translate-status]').textContent"
                ".indexOf('Felder') !== -1",
                timeout=20000,
            )
            name_en = page.locator("input[name=name_en]").input_value()
            check(name_en == f"EN Stand Brezel {width}", f"name_en заполнен ({name_en!r})")
            check(
                page.locator("input[name=name_en][data-ai-filled]").count() == 1,
                "поле помечено как перевод ИИ",
            )
            desc = page.locator("textarea[name=description_en]").input_value()
            check(desc == "", f"отказ пост-проверки: описание осталось пустым ({desc!r})")
            status = page.locator("[data-i18n-translate-status]").text_content() or ""
            check("übersprungen" in status, f"статус говорит о пропуске ({status!r})")
            # повторный клик: заполненное не трогается, перевода нет
            page.fill("input[name=name_en]", "Mein eigener Name")
            btn.click()
            page.wait_for_timeout(800)
            check(
                page.locator("input[name=name_en]").input_value() == "Mein eigener Name",
                "текст владельца не перезаписан",
            )
            # rich-описание: перевод доезжает до Save (редактор не перетирает поле)
            page.select_option("[data-i18n-select]", "de")
            page.locator("#id_description_de + * .rte-area").fill("Frische Brezel")
            page.select_option("[data-i18n-select]", "en")
            btn.click()
            page.wait_for_function(
                "document.querySelector('textarea[name=description_en]').value !== ''",
                timeout=20000,
            )
            page.locator("main button.ui-btn-primary[type=submit]").first.click()
            page.wait_for_load_state()
            saved = _saved_description(args.slug, f"Stand Brezel {width}")
            check(saved == "EN Frische Brezel", f"Save сохранил перевод описания ({saved!r})")
            scroll = page.evaluate("document.documentElement.scrollWidth")
            check(scroll <= width + 2, f"без горизонтального скролла ({scroll}px)")
            check(not errors, f"без JS-ошибок {errors[:2]}")
            ctx.close()
        browser.close()
    print(f"\n{ok} ok, {len(fail)} fail")
    for f in fail:
        print("  FAIL:", f)
    sys.exit(1 if fail else 0)


if __name__ == "__main__":
    main()
