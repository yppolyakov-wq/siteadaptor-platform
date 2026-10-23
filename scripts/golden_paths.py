"""KA-GP: «золотые пути» покупателя — браузерный стенд (Playwright, Chromium).

Проходит два пути так, как их проходит человек с телефона (390 px), и проверяет,
что в конце появилась настоящая сделка:

  GP-1  Aktionen-lite (демо `klingenbrot`): главная → акция «Zurücklegen» → форма →
        страница подтверждения /r/<code>/ → сделка `Reservation` в БД.
  GP-2  Click & Collect (демо `shop`): каталог → товар → в корзину → корзина →
        самовывоз, имя/почта → заказ /bestellung/<code>/ → `Order` в БД.

Плюс общие проверки на каждой странице: нет JS-ошибок, нет горизонтального
скролла, ответ 2xx.

Запуск (сервер стенда уже работает, демо засеяны):

    python manage.py runserver 0.0.0.0:8000 --settings=config.settings.stand
    uv run --with playwright==1.55.0 python scripts/golden_paths.py

Хосты демо (`*.siteadaptor.de`) направляются на локальный сервер правилом
резолвера Chromium — без правки /etc/hosts. Сценарий НЕ входит в CI (там нет
браузера); его гоняют перед мержем изменений витрины и чекаута.
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
import uuid

from playwright.sync_api import sync_playwright

CHROME = "/opt/pw-browsers/chromium-1194/chrome-linux/chrome"
BASE = "siteadaptor.de"


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


def _page_health(run, page, errors, label):
    width = page.evaluate("document.documentElement.scrollWidth")
    run.check(width <= 392, f"{label}: без горизонтального скролла ({width}px)")
    run.check(not errors, f"{label}: без JS-ошибок {errors[:2]}")
    errors.clear()


def _db_has(model, code, schema):
    """Сделка с этим кодом есть в схеме демо (через manage.py shell)."""
    code_py = (
        "from django_tenants.utils import schema_context\n"
        f"from django.apps import apps\n"
        f"with schema_context({schema!r}):\n"
        f"    m = apps.get_model({model!r})\n"
        f"    print('FOUND' if m.objects.filter(reference_code={code!r}).exists() else 'MISSING')\n"
    )
    out = subprocess.run(
        [sys.executable, "manage.py", "shell", "-c", code_py],
        capture_output=True,
        text=True,
        check=False,
    )
    return "FOUND" in out.stdout


def gp1_aktionen(run, ctx, port):
    print("GP-1 Aktionen-lite (klingenbrot)")
    page = ctx.new_page()
    errors = []
    page.on("pageerror", lambda e: errors.append(str(e)))
    resp = page.goto(f"http://klingenbrot.{BASE}:{port}/")
    run.check(resp and resp.ok, "главная открывается")
    _page_health(run, page, errors, "главная")
    link = page.locator("a[href^='/p/']").first
    run.check(link.count() == 1, "на главной есть акция")
    link.click()
    page.wait_for_load_state()
    _page_health(run, page, errors, "акция")
    form = page.locator("form[action$='/reserve/']")
    run.check(form.count() == 1, "у акции есть форма «Zurücklegen»")
    if not form.count():
        return
    if not form.is_visible():  # форма живёт в диалоге за кнопкой (HF-волна)
        page.locator("a,button").filter(has_text="Zurücklegen").locator(
            "visible=true"
        ).first.click()
        page.wait_for_timeout(300)
    run.check(form.is_visible(), "кнопка открывает форму")
    tag = uuid.uuid4().hex[:6]
    form.locator("input[name='name']").fill(f"GP Kunde {tag}")
    form.locator("input[name='email']").fill(f"gp-{tag}@example.com")
    form.locator("button[type='submit']").click()
    page.wait_for_load_state()
    m = re.search(r"/r/([^/]+)/", page.url)
    if not m:  # форма вернулась с ошибкой (например, лимит частоты при повторных прогонах)
        err = page.locator(".errorlist, [role='alert'], .text-red-600").all_inner_texts()
        print("    ошибка формы:", " | ".join(t.strip() for t in err if t.strip())[:200])
    run.check(bool(m), f"подтверждение /r/<code>/ ({page.url})")
    _page_health(run, page, errors, "подтверждение")
    if m:
        run.check(page.get_by_text(m.group(1)).count() > 0, "код показан покупателю")
        run.check(_db_has("promotions.Reservation", m.group(1), "klingenbrot"), "резерв в БД")


def gp2_click_collect(run, ctx, port):
    print("GP-2 Click & Collect (shop)")
    page = ctx.new_page()
    errors = []
    page.on("pageerror", lambda e: errors.append(str(e)))
    resp = page.goto(f"http://shop.{BASE}:{port}/sortiment/")
    run.check(resp and resp.ok, "каталог открывается")
    _page_health(run, page, errors, "каталог")
    product = page.locator("a[href^='/sortiment/'][href$='/']").filter(
        has_not=page.locator("img[alt='']")
    )
    hrefs = [h for h in product.evaluate_all("els => els.map(e => e.getAttribute('href'))")]
    target = next((h for h in hrefs if h.count("/") >= 4), None)
    run.check(bool(target), "в каталоге есть товар")
    if not target:
        return
    page.goto(f"http://shop.{BASE}:{port}{target}")
    _page_health(run, page, errors, "товар")
    add = page.locator("form[action='/warenkorb/add/'] button[type='submit']").first
    run.check(add.count() == 1, "кнопка «в корзину»")
    add.click()
    page.wait_for_timeout(800)
    page.goto(f"http://shop.{BASE}:{port}/warenkorb/")
    _page_health(run, page, errors, "корзина")
    checkout = page.locator("form[action$='/warenkorb/bestellen/']")
    run.check(checkout.count() == 1, "в корзине есть форма заказа")
    if not checkout.count():
        return
    tag = uuid.uuid4().hex[:6]
    checkout.locator("input[name='name']").fill(f"GP Kunde {tag}")
    checkout.locator("input[name='email']").fill(f"gp-{tag}@example.com")
    slot = checkout.locator("select[name='pickup_slot']")
    if slot.count() and slot.is_visible():
        options = slot.locator("option[value]:not([value=''])")
        if options.count():
            slot.select_option(options.first.get_attribute("value"))
    for box in page.locator(
        "input[form='checkout-form'][required], form#checkout-form input[type='checkbox'][required]"
    ).all():
        box.check()
    # Кнопка «Zahlungspflichtig bestellen» вынесена из формы (`form="checkout-form"`).
    page.locator("button[form='checkout-form']").last.click()
    page.wait_for_load_state()
    m = re.search(r"/bestellung/([^/]+)/", page.url)
    run.check(bool(m), f"подтверждение заказа ({page.url})")
    _page_health(run, page, errors, "подтверждение заказа")
    if m:
        run.check(_db_has("orders.Order", m.group(1), "shop"), "заказ в БД")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()
    run = Run()
    with sync_playwright() as p:
        browser = p.chromium.launch(
            executable_path=CHROME,
            args=[f"--host-resolver-rules=MAP *.{BASE} 127.0.0.1"],
        )
        ctx = browser.new_context(viewport={"width": 390, "height": 844}, locale="de-DE")
        gp1_aktionen(run, ctx, args.port)
        gp2_click_collect(run, ctx, args.port)
        browser.close()
    print(f"\n{run.ok} ok, {len(run.fail)} fail")
    for f in run.fail:
        print("  FAIL:", f)
    sys.exit(1 if run.fail else 0)


if __name__ == "__main__":
    main()
