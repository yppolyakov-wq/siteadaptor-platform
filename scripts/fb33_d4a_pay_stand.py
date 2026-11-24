"""FB-33 D4a: стенд «Jetzt bezahlen» — подтверждение заказа и предложения (1440/390, de/ru,
без JS и с JS).

Шесть состояний `orders.payments.pay_state` задаются ORM-ом в `--setup` (бизнес `shop`, для
«unavailable» — `restaurant_demo` с выключенной онлайн-оплатой): open · processing ·
closed (минуты до автоотмены) · cancelled · paid · unavailable. На подтверждении
`/bestellung/<code>/` и на странице предложения `/o/<token>/`:
- кнопка/ссылка «Jetzt bezahlen» — только у `open` (ссылка ведёт на `/bezahlen/`, по ней
  НЕ переходим — там Stripe; у предложения — форма `action=pay`);
- у прочих — текст состояния `[data-pay-state=…]`, «Pay in store at pickup.» у
  отменённого онлайн-заказа нет;
- контроль: on_site-заказ — ни кнопки, ни текстов состояний.
Каждая страница — `a11y_check` (витрина, 24 px), без гор. скролла, без ошибок JS.

    DB_NAME=<стенд-БД> uv run python scripts/fb33_d4a_pay_stand.py --setup   # пишет коды
    DB_NAME=<стенд-БД> DB_CONN_MAX_AGE=0 uv run python manage.py runserver 0.0.0.0:<порт> \\
        --settings=config.settings.stand --noreload
    STAND_URL=http://shop.siteadaptor.de:<порт> \\
        uv run --with playwright==1.55.0 python scripts/fb33_d4a_pay_stand.py <папка>

Итог «N ✓, 0 ✗».
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from urllib.parse import urlsplit

import standlib as sl

STATE_FILE = Path(os.environ.get("D4A_STATE", "/tmp/fb33_d4a_pay_state.json"))
STATES = ("open", "processing", "closed", "cancelled", "paid", "unavailable")
#: область блока оплаты для проверки контраста: текст состояния, ссылка, форма
PAY_SCOPES = ("[data-pay-state]", 'a[href$="/bezahlen/"]', "form:has(input[value=pay])")

SETUP = r"""
import json, uuid
from datetime import timedelta
from decimal import Decimal
from django.utils import timezone
from django_tenants.utils import schema_context
from apps.tenants.models import Tenant
from apps.catalog.models import Product
from apps.orders import offers, services
from apps.orders.models import Offer, Order

def prep(schema, enabled):
    t = Tenant.objects.get(schema_name=schema)
    t.stripe_connect_id = "acct_stand_d4a"
    t.payments_enabled = enabled
    t.orders_prepay = True
    t.save(update_fields=["stripe_connect_id", "payments_enabled", "orders_prepay"])
    return t

def make(state, method=Order.METHOD_STRIPE):
    product = Product.objects.filter(base_price__gt=0).order_by("pk").first()
    order = services.create_order(
        items=[(product, 1)], name="Stand D4a", email="", payment_method=method
    )
    upd = {}
    hours = 1
    if state == "processing":
        upd["stripe_payment_intent"] = "pi_stand_" + uuid.uuid4().hex[:8]
    elif state == "closed":
        hours = 23.9
    elif state == "cancelled":
        upd.update(status="cancelled", payment_state="refunded")
    elif state == "paid":
        upd.update(payment_state="paid", status="confirmed",
                   stripe_payment_intent="pi_stand_" + uuid.uuid4().hex[:8])
    upd["created_at"] = timezone.now() - timedelta(hours=hours)
    Order.objects.filter(pk=order.pk).update(**upd)
    from apps.inbox.services import start_conversation
    conv = start_conversation(subject="D4a", body="Stand", email="stand-d4a@example.com",
                              name="Stand")
    offer = offers.send_offer(conv, lines=[{"title": "Stand", "unit_price": "10.00", "qty": 1}])
    Offer.objects.filter(pk=offer.pk).update(status=Offer.STATUS_ACCEPTED, order=order)
    return {"code": order.reference_code, "token": str(offer.token)}

out = {}
prep("shop", True)
with schema_context("shop"):
    for st in ("open", "processing", "closed", "cancelled", "paid"):
        out[st] = {"host": "shop", **make(st)}
    out["control"] = {"host": "shop", **make("control", Order.METHOD_ON_SITE)}
prep("restaurant_demo", False)
with schema_context("restaurant_demo"):
    out["unavailable"] = {"host": "restaurant-demo", **make("unavailable")}
print("D4A" + json.dumps(out))
"""


def setup() -> None:
    res = subprocess.run(
        [
            "uv",
            "run",
            "python",
            "manage.py",
            "shell",
            "--settings=config.settings.stand",
            "-c",
            SETUP,
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    line = next((ln for ln in res.stdout.splitlines() if ln.startswith("D4A")), None)
    if line is None:
        sys.exit("setup не прошёл:\n" + res.stderr[-1500:])
    STATE_FILE.write_text(line[3:])
    print(f"setup: {STATE_FILE}")


def base_for(host: str) -> str:
    parts = urlsplit(sl.BASE_URL)
    port = f":{parts.port}" if parts.port else ""
    return f"{parts.scheme}://{host}.{sl.BASE_DOMAIN}{port}"


def check_page(rep, page, tag, state, *, offer: bool, code: str):
    if offer:
        button = page.locator("form input[name=action][value=pay]")
    else:
        button = page.locator(f'a[href$="/bestellung/{code}/bezahlen/"]')
    want = state == "open"
    rep.check(button.count() == int(want), f"{tag}: кнопка оплаты {'есть' if want else 'нет'}")
    if want and not offer:
        href = button.first.get_attribute("href") or ""
        rep.check(href.endswith(f"/bestellung/{code}/bezahlen/"), f"{tag}: href ({href})")
    marks = page.locator("[data-pay-state]").evaluate_all(
        "els => els.map(e => e.getAttribute('data-pay-state'))"
    )
    expected = [state] if state in ("processing", "closed", "unavailable", "cancelled") else []
    rep.check(marks == expected, f"{tag}: текст состояния {marks} = {expected}")
    if state == "cancelled" and not offer:
        rep.check("Pay in store at pickup." not in page.content(), f"{tag}: нет «Pay in store»")


def main() -> None:
    if "--setup" in sys.argv:
        setup()
        return
    out_dir = sys.argv[1] if len(sys.argv) > 1 else "/tmp/fb33_d4a_pay"
    data = json.loads(STATE_FILE.read_text())
    rep = sl.Report()
    pass_no = 0
    with sl.launch() as browser:
        for w, h, lang, js in sl.matrix():
            mode = "js" if js else "nojs"
            page = sl.open_page(browser, w, h, js=js, lang=lang)
            # лимит подтверждений на IP (60 / 10 мин) — свой адрес на каждый проход матрицы
            pass_no += 1
            page.context.set_extra_http_headers(
                {"X-Forwarded-For": f"10.62.{pass_no}.{os.getpid() % 250}"}
            )
            for state in (*STATES, "control"):
                item = data[state]
                base = base_for(item["host"])
                for offer in (False, True):
                    if offer and state == "control":
                        continue
                    path = f"/o/{item['token']}/" if offer else f"/bestellung/{item['code']}/"
                    tag = f"{w} {lang} {mode} {state} {'offer' if offer else 'order'}"
                    resp = page.goto(base + path)
                    sl.settle(page, js, rep)
                    if not rep.check(
                        resp.status == 200, f"{tag}: ответ {resp.status}", code="status"
                    ):
                        continue
                    check_page(
                        rep,
                        page,
                        tag,
                        "" if state == "control" else state,
                        offer=offer,
                        code=item["code"],
                    )
                    over = sl.overflow(page)
                    rep.check(over <= 0, f"{tag}: без гор. скролла ({over}px)", code="overflow")
                    rep.check(not page.js_errors, f"{tag}: без ошибок JS ({page.js_errors[:2]})")
                    # контраст старых серых подписей страницы (text-gray-400) — не этот срез:
                    # вся страница — цели, имена, фокус; контраст — у блока оплаты
                    sl.a11y_check(rep, page, tag, scope="main", minimum=24, contrast=False)
                    pay = next(
                        (sel for sel in PAY_SCOPES if page.locator(sel).count()),
                        None,
                    )
                    if pay:
                        sl.a11y_check(rep, page, f"{tag} [оплата]", scope=pay, minimum=24)
                    sl.shot(
                        page, out_dir, f"{state}_{'offer' if offer else 'order'}_{w}_{lang}_{mode}"
                    )
            page.context.close()
    rep.finish("FB-33 D4a pay_state")


if __name__ == "__main__":
    main()
