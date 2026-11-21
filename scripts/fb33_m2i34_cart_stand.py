"""FB-33 M2i-34: стенд корзины по «Felder» (Python-Playwright, не входит в CI).

Корзина /warenkorb/ кафе m35b с настройкой `form_fields.checkout` (e-mail «Nicht fragen»,
телефон «Pflicht», своя подпись заметки, свои вопросы): 1440/390, de/ru, с JS и без; отказ
сервера без обязательного (в обход `required`), введённое возвращается; заказ → карточка
заказа и кухонная доска показывают ответы. Без настройки (`--reset`) — прежняя форма.

    DB_NAME=<стенд-БД> uv run python scripts/fb33_m2i34_cart_stand.py --setup   # настройка
    DB_NAME=<стенд-БД> uv run python scripts/fb33_m2i34_cart_stand.py --reset   # без настройки
    DB_NAME=<стенд-БД> python manage.py runserver 0.0.0.0:<порт> --settings=config.settings.stand
    STAND_URL=http://m35b.siteadaptor.de:<порт> \\
      uv run --no-project --with playwright python scripts/fb33_m2i34_cart_stand.py <папка> [--before]

`--before` — прогон без настройки (прежняя форма). Итог: «N ✓, 0 ✗».

FB-33 M2i-7: `--setup --online` включает бизнесу онлайн-оплату (prepay + Connect) — e-mail
«Nicht fragen» и при ней не спрашивается, заказ без адреса уходит на оплату. Сам Stripe не
вызывается: сервер стенда запускать с фиктивными ключами и мёртвым прокси —

    STRIPE_TEST_SECRET_KEY=sk_test_stand STRIPE_CONNECT_CLIENT_ID=ca_stand \
      HTTPS_PROXY=http://127.0.0.1:9 https_proxy=http://127.0.0.1:9 DB_NAME=<стенд-БД> \
      python manage.py runserver …

— запрос к Stripe обрывается до сети (StripeError), заказ остаётся онлайн-оплатой с кнопкой
«Jetzt bezahlen» (та же ветка, что «Stripe недоступен»); стенд сверяет заказ в БД (способ
stripe, адреса нет) и строку «адрес из оплаты» на подтверждении. Прогон: `<папка> --online`.
"""

# ruff: noqa: B023 — вложенные помощники вызываются в той же итерации цикла
import os
import re
import subprocess
import sys

CHROME = "/opt/pw-browsers/chromium"
BASE = "siteadaptor.de"
SLUG = "m35b"
PASSWORD = "Stand-Passwort-123"

SETUP = f"""
from decimal import Decimal
from django_tenants.utils import tenant_context
from apps.core import form_spec
from apps.tenants import siteconfig
from apps.tenants.models import Tenant
t = Tenant.objects.get(schema_name={SLUG!r})
with tenant_context(t):
    from apps.catalog.models import Product
    p = Product.objects.filter(sku="M2I34").first() or Product.objects.create(
        name={{"de": "Bauernbrot", "ru": "Хлеб"}}, base_price=Decimal("4.50"), sku="M2I34")
cfg = siteconfig.normalize(t.site_config or {{}})
ff = dict(cfg.get("form_fields") or {{}})
ff.pop("checkout", None)
cfg["form_fields"] = ff
if not ff:
    cfg.pop("form_fields")
t.orders_prepay = t.payments_enabled = ONLINE
t.stripe_connect_id = "acct_stand_m2i7" if ONLINE else ""
if MODE == "setup":
    state = form_spec.edit_state(cfg, "checkout")
    state["mode"].update({{"email": "off", "phone": "req"}})
    state["labels"] = {{"note": "Wünsche an die Küche"}}
    state["custom"] = [
        {{"id": "n1", "type": "text", "label": "Allergien", "mode": "req",
          "label_i18n": {{"ru": "Аллергии"}}}},
        {{"id": "n2", "type": "choice", "label": "Besteck", "options": ["Ja", "Nein"]}},
        {{"id": "n3", "type": "bool", "label": "Geschenkpapier"}},
    ]
    form_spec.put(cfg, "checkout", state)
t.site_config = cfg
t.save(update_fields=["site_config", "orders_prepay", "payments_enabled", "stripe_connect_id"])
print("READY", p.pk, (t.site_config.get("form_fields") or {{}}).get("checkout"))
"""


ORDER_STATE = f"""
from django_tenants.utils import tenant_context
from apps.tenants.models import Tenant
with tenant_context(Tenant.objects.get(schema_name={SLUG!r})):
    from apps.orders.models import Order
    o = Order.objects.get(reference_code=CODE)
    print("STATE", o.payment_method, o.payment_state, o.status, repr(o.customer.email))
"""

ONLINE = "--online" in sys.argv


def shell(code: str) -> str:
    cmd = ["uv", "run", "python", "manage.py", "shell", "--settings=config.settings.stand"]
    out = subprocess.run([*cmd, "-c", code], capture_output=True, text=True, check=False)
    return out.stdout.strip() or out.stderr[-1500:]


def setup(mode: str) -> bool:
    out = shell(f"MODE = {mode!r}\nONLINE = {ONLINE and mode == 'setup'!r}\n" + SETUP)
    print(out)
    return "READY" in out


if sys.argv[1:2] in (["--setup"], ["--reset"]):
    sys.exit(0 if setup(sys.argv[1][2:]) else 1)

from playwright.sync_api import sync_playwright  # noqa: E402

OUT = sys.argv[1]
BEFORE = "--before" in sys.argv
U = os.environ.get("STAND_URL", f"http://{SLUG}.{BASE}:8034")
ok, fail = 0, []


def check(c, label):
    global ok
    ok += bool(c)
    print(("  ✓ " if c else "  ✗ ") + label)
    if not c:
        fail.append(label)


def product_pk(pg):
    pg.goto(U + "/sortiment/")
    html = pg.content()
    m = re.search(r'name="product" value="([0-9a-f-]{36})"', html)
    return m.group(1) if m else None


def add_to_cart(ctx, pg):
    """В корзину — кнопкой формы «In den Warenkorb» на витрине (тот же POST, что у гостя)."""
    pg.goto(U + "/?hl=de")
    pk = product_pk(pg)
    form = pg.locator(f'form:has(input[name=product][value="{pk}"])').first
    form.locator("button[type=submit], button:not([type])").first.click()
    pg.wait_for_load_state("networkidle")  # со скриптами форма уходит запросом в фоне
    return pk, 200 if pk else 0


def form_info(pg):
    return pg.evaluate(
        """() => { const f = document.getElementById('checkout-form');
          const q = n => f.querySelector(`[name="${n}"]`);
          return {sw: document.documentElement.scrollWidth, iw: innerWidth,
            names: [...f.querySelectorAll('[name]')].map(e => e.name),
            phoneReq: !!(q('phone') && q('phone').required),
            q1Req: !!(q('q1') && q('q1').required),
            text: f.textContent.replace(/\\s+/g, ' '),
            alerts: [...document.querySelectorAll('[role=alert]')].map(e => e.textContent.trim())};
        }"""
    )


def storefront(b, lang, js, w, h):
    ctx = b.new_context(viewport={"width": w, "height": h}, java_script_enabled=js)
    pg = ctx.new_page()
    pk, status = add_to_cart(ctx, pg)
    tag = f"{lang} {w} {'js' if js else 'nojs'}"
    check(pk and status in (200, 302), f"{tag}: товар в корзине")
    pg.goto(U + f"/?hl={lang}")
    pg.goto(U + "/warenkorb/")
    info = form_info(pg)
    pg.screenshot(
        path=f"{OUT}/cart-{'before' if BEFORE else 'ff'}-{lang}-{w}-{tag.split()[-1]}.png",
        full_page=True,
    )
    check(info["sw"] <= info["iw"], f"{tag}: без горизонтальной прокрутки")
    names = set(info["names"])
    if BEFORE:
        check({"name", "email", "phone", "note"} <= names, f"{tag}: прежняя форма")
        check("q1" not in names and "Pflichtfeld" not in info["text"], f"{tag}: без вопросов")
    else:
        check("email" not in names, f"{tag}: e-mail «Nicht fragen» не спрашивается")
        check(info["phoneReq"] and info["q1Req"], f"{tag}: телефон и «Allergien» — required")
        sr = "Pflichtfeld" if lang == "de" else "обязательное поле"
        check(sr.lower() in info["text"].lower(), f"{tag}: sr-only «(Pflichtfeld)»")
        label = "Allergien" if lang == "de" else "Аллергии"
        check(label in info["text"], f"{tag}: подпись вопроса на языке витрины ({label})")
        check({"q2", "q3", "note"} <= names, f"{tag}: вопросы и заметка")
    ctx.close()


def order_flow(b):
    """С JS: в обход required — отказ сервера с введённым; затем заказ и показ ответов."""
    ctx = b.new_context(viewport={"width": 1440, "height": 900})
    pg = ctx.new_page()
    add_to_cart(ctx, pg)
    pg.goto(U + "/warenkorb/")
    pg.fill("#id_name", "Stand Kim")
    pg.fill("#id_q1", "Nüsse <b>")
    pg.select_option("#id_q2", "Nein")
    pg.evaluate("document.querySelectorAll('[required]').forEach(e => e.required = false)")
    pg.click("button[form=checkout-form]")
    pg.wait_for_load_state()
    info = form_info(pg)
    pg.screenshot(path=f"{OUT}/cart-refused-de-1440.png", full_page=True)
    check(pg.url.endswith("/warenkorb/"), "отказ: снова корзина")
    check(any("Telefon" in a or "Phone" in a for a in info["alerts"]), f"отказ: {info['alerts']}")
    check(pg.input_value("#id_q1") == "Nüsse <b>", "отказ: ответ на вопрос вернулся")
    check(pg.input_value("#id_q2") == "Nein", "отказ: выбор вернулся")
    check(pg.input_value("#id_name") == "Stand Kim", "отказ: имя вернулось")
    pg.fill("#id_phone", "0171 234")
    pg.check("input[name=q3]")
    pg.click("button[form=checkout-form]")
    pg.wait_for_load_state()
    m = re.search(r"/bestellung/([^/]+)/", pg.url)
    check(bool(m), f"заказ оформлен: {pg.url}")
    ctx.close()
    return m.group(1) if m else ""


HINT = {
    "de": "Die Bestätigung senden wir an die E-Mail-Adresse aus der Zahlung.",
    "ru": "Подтверждение придёт на адрес электронной почты, указанный при оплате.",
}


def online_flow(b, lang, w, h):
    """FB-33 M2i-7: онлайн-оплата без e-mail в форме — заказ уходит на оплату (Stripe на
    стенде недоступен — см. докстринг), подтверждение говорит «адрес из оплаты» без адреса."""
    ctx = b.new_context(viewport={"width": w, "height": h})
    pg = ctx.new_page()
    add_to_cart(ctx, pg)
    pg.goto(U + f"/?hl={lang}")
    pg.goto(U + "/warenkorb/")
    tag = f"online {lang} {w}"
    info = form_info(pg)
    check("email" not in info["names"], f"{tag}: e-mail «Nicht fragen» и при онлайн-оплате")
    radio = pg.locator("input[name=payment][value=stripe]")
    if radio.count():
        radio.check()
    check(radio.count() or "payment" not in info["names"], f"{tag}: способ «online» выбран")
    pg.fill("#id_name", "Stand Online")
    pg.fill("#id_phone", "0171 7")
    pg.fill("#id_q1", "keine")
    pg.click("button[form=checkout-form]")
    pg.wait_for_load_state()
    m = re.search(r"/bestellung/([^/?]+)/", pg.url)
    check(bool(m), f"{tag}: заказ создан, не отказ ({pg.url})")
    if not m:
        ctx.close()
        return
    state = shell(f"CODE = {m.group(1)!r}\n" + ORDER_STATE)
    check("STATE stripe unpaid new ''" in state, f"{tag}: в БД онлайн-оплата без адреса ({state})")
    pg.screenshot(path=f"{OUT}/online-confirm-{lang}-{w}.png", full_page=True)
    html = pg.content()
    check(HINT[lang] in html, f"{tag}: строка «адрес из оплаты»")
    hint = pg.locator("[data-payer-email-hint]").inner_text()
    check("@" not in hint, f"{tag}: в строке нет адреса")
    check("storefront-order-pay" in html or "/bezahlen/" in html, f"{tag}: «Jetzt bezahlen»")
    sw = pg.evaluate("document.documentElement.scrollWidth <= innerWidth")
    check(sw, f"{tag}: без горизонтальной прокрутки")
    ctx.close()


def cabinet(b, code):
    for w, h in ((1440, 900), (390, 844)):
        ctx = b.new_context(viewport={"width": w, "height": h})
        pg = ctx.new_page()
        pg.goto(U + "/accounts/login/")
        pg.fill("input[name=login]", f"owner@{SLUG}.test")
        pg.fill("input[name=password]", PASSWORD)
        pg.click("button[type=submit]")
        pg.wait_for_load_state()
        pg.goto(U + "/dashboard/orders/kitchen/")
        board = pg.locator("#kds-board").inner_text()
        pg.screenshot(path=f"{OUT}/kds-{w}.png", full_page=True)
        check(code in board and "Allergien" in board and "Nüsse <b>" in board, f"KDS {w}: ответы")
        check("Geschenkpapier" in board and "Besteck" in board, f"KDS {w}: все ответы")
        sw = pg.evaluate("document.documentElement.scrollWidth <= innerWidth")
        check(sw, f"KDS {w}: без горизонтальной прокрутки")
        pg.goto(U + "/dashboard/orders/")
        link = pg.locator(f"a:has-text('{code}')").first
        if link.count():
            link.click()
            pg.wait_for_load_state()
        card = pg.content()
        pg.screenshot(path=f"{OUT}/card-{w}.png", full_page=True)
        check("data-custom-answers" in card and "Nüsse &lt;b&gt;" in card, f"карточка {w}: ответы")
        ctx.close()


with sync_playwright() as p:
    b = p.chromium.launch(
        executable_path=CHROME, args=[f"--host-resolver-rules=MAP *.{BASE} 127.0.0.1"]
    )
    for lang in ("de", "ru"):
        for js in (True, False):
            for w, h in ((1440, 900), (390, 844)):
                storefront(b, lang, js, w, h)
    if ONLINE:
        online_flow(b, "de", 1440, 900)
        online_flow(b, "ru", 390, 844)
    elif not BEFORE:
        code = order_flow(b)
        if code:
            cabinet(b, code)
    b.close()

print(f"{ok} ✓, {len(fail)} ✗")
for f in fail:
    print("  ✗", f)
sys.exit(1 if fail else 0)
