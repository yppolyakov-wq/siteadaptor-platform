"""FB-33 M2i-34: корзина по настройке `form_fields.checkout` — витрина, сервер, снимок ответов.

План — scratchpad `m2i34-plan.md` (C0–C4). Без настройки корзина байт-в-байт прежняя (снимки
`test_fb33_m2h_before`); с настройкой — режимы e-mail/телефон/заметка, свои вопросы, проверка
сервера ДО любой записи и брони склада; ответы — неизменяемый снимок `Order.custom_answers`
(подпись на момент заказа), его показывают карточка, письмо владельцу, кухонная доска и ЛК.
Суммы ответы не трогают.
"""

import re
import uuid
from decimal import Decimal

import pytest
from django.contrib.messages import get_messages
from django.contrib.messages.middleware import MessageMiddleware
from django.contrib.sessions.middleware import SessionMiddleware
from django.db import connection
from django.test import RequestFactory
from django.test.utils import CaptureQueriesContext
from django.utils import translation

from apps.catalog.tests.factories import ProductFactory
from apps.core import deal_card, form_answers
from apps.core.tests import test_fb31p5_detail_golden as _p5
from apps.core.tests import test_fb33_m2h_before as _m2h
from apps.orders import public_views, services, views
from apps.orders.models import Order
from apps.orders.tests.test_kitchen import _req as _cab_req
from apps.orders.tests.test_payment_methods import _configure, _prepay_tenant, _pub_req
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db


TODO_C4 = pytest.mark.xfail(strict=True, reason="FB-33 M2i-34 C4")

QUESTIONS = [
    {"id": "q1", "type": "text", "label": "Allergien", "mode": "req"},
    {"id": "q2", "type": "number", "label": "Personen"},
    {"id": "q3", "type": "choice", "label": "Besteck", "options": ["Ja", "Nein"]},
    {"id": "q4", "type": "bool", "label": "Geschenkpapier"},
]


def _ff(mode=None, labels=None, custom=QUESTIONS):
    entry = {"custom": custom, "next_id": len(custom)} if custom else {}
    if mode:
        entry["mode"] = mode
    if labels:
        entry["labels"] = labels
    return {"form_fields": {"checkout": entry}}


@pytest.fixture(autouse=True)
def _tenant_urlconf(settings):
    settings.ROOT_URLCONF = "config.urls_tenant"


def _tenant(cfg=None, **kw):
    return TenantFactory.build(site_config=cfg or {}, **kw)


def _cart(tenant, session=None):
    request = RequestFactory().get("/warenkorb/")
    SessionMiddleware(lambda r: None).process_request(request)
    MessageMiddleware(lambda r: None).process_request(request)
    product = ProductFactory(base_price=Decimal("10.00"))
    request.session["cart"] = {str(product.pk): 1}
    request.session.update(session or {})
    request.tenant = tenant
    return public_views.cart_view(request).content.decode()


def _checkout_form(html):
    start = html.index('id="checkout-form"')
    return html[start : html.index("</form>", start)]


def _post(data, tenant, *, stock=None, table=""):
    product = ProductFactory(base_price=Decimal("10.00"), stock_quantity=stock)
    session = {"cart": {str(product.pk): 2}}
    if table:
        session["table"] = table
    request = _pub_req(data, tenant=tenant, session=session)
    resp = public_views.checkout(request)
    return request, resp, product


# ───────────── C0: без настройки корзина прежняя ─────────────


def test_settings_of_other_forms_do_not_touch_the_cart(frozen_now):
    """Настройка заявки (`form_fields.anfrage`) корзину не меняет — снимок M2h «bare»."""
    cfg = {"form_fields": {"anfrage": {"mode": {"phone": "req"}, "custom": QUESTIONS[:1]}}}
    _m2h._check("cart-bare", _p5._normalize(_m2h.cart_html(cfg)))


frozen_now = _p5.frozen_now


def test_kitchen_board_queries_do_not_grow_with_orders():
    """Ответы лежат в строке заказа: доска не делает запроса на заказ (замок до C4)."""
    req = _cab_req()

    def count():
        with CaptureQueriesContext(connection) as ctx:
            views.kitchen_board(req)
        return len(ctx.captured_queries)

    empty = count()
    for _i in range(3):
        order = services.create_order(items=[(ProductFactory(name={"de": "Brot"}), 1)], name="K")
        Order.objects.filter(pk=order.pk).update(
            custom_answers={"q1": {"label": "Allergien", "value": "Nüsse"}}
        )
    assert (empty, count()) == (1, 2)  # заказы (+клиент) и позиции одним prefetch


# ───────────── C3: витрина ─────────────


def test_cart_draws_the_configured_fields():
    cfg = _ff({"email": "off", "phone": "req"}, {"note": "Wünsche an die Küche"})
    form = _checkout_form(_cart(_tenant(cfg)))
    assert 'name="email"' not in form
    phone = re.search(r'<input[^>]*name="phone"[^>]*>', form).group(0)
    assert " required" in phone
    assert "Pflichtfeld" in form and "Wünsche an die Küche" in form
    assert 'name="q1"' in form and 'name="q3"' in form and 'type="checkbox" name="q4"' in form
    q1 = re.search(r'<input[^>]*name="q1"[^>]*>', form).group(0)
    assert " required" in q1


def test_table_cart_asks_note_and_questions_only():
    cfg = _ff({"email": "req", "phone": "req"})
    form = _checkout_form(_cart(_tenant(cfg), {"table": "7"}))
    assert 'name="email"' not in form and 'name="phone"' not in form and 'name="name"' not in form
    assert 'name="note"' in form and 'name="q1"' in form


def test_online_payment_shows_the_email_even_when_off(settings):
    _configure(settings)
    tenant = _prepay_tenant()
    tenant.site_config = _ff({"email": "off"})
    assert 'name="email"' in _checkout_form(_cart(tenant))


def test_cart_escapes_labels():
    cfg = _ff(custom=[{"id": "q1", "type": "text", "label": "<script>x()</script>"}])
    form = _checkout_form(_cart(_tenant(cfg)))
    assert "<script>x()" not in form and "&lt;script&gt;x()" in form


# ───────────── C3: сервер ─────────────


def test_missing_required_field_refuses_before_anything_is_written():
    tenant = _tenant(_ff({"phone": "req"}))
    request, resp, product = _post({"name": "Kim", "q1": "Nüsse", "q2": "3"}, tenant, stock=5)
    assert resp.status_code == 302 and resp.url.endswith("/warenkorb/")
    assert not Order.objects.exists()
    product.refresh_from_db()
    assert product.stock_quantity == 5  # склад не тронут
    said = [str(m) for m in get_messages(request)]
    assert any("Telefon" in m or "Phone" in m for m in said), said
    kept = request.session[public_views.CHECKOUT_INPUT_KEY]
    assert kept["name"] == "Kim" and kept["answers"] == {"q1": "Nüsse", "q2": "3"}


def test_missing_required_question_refuses():
    _request, resp, _p = _post({"name": "Kim", "phone": "1"}, _tenant(_ff()))
    assert resp.url.endswith("/warenkorb/") and not Order.objects.exists()


def test_kept_answers_come_back_once_into_the_form():
    tenant = _tenant(_ff({"phone": "req"}))
    data = {"name": "Kim", "q1": "Nüsse <b>", "q3": "Nein", "q4": "1", "q99": "fremd"}
    request, _resp, _p = _post(data, tenant)
    kept = request.session[public_views.CHECKOUT_INPUT_KEY]
    assert "q99" not in kept["answers"]
    html = _cart(tenant, {public_views.CHECKOUT_INPUT_KEY: kept})
    form = _checkout_form(html)
    assert 'value="Nüsse &lt;b&gt;"' in form
    assert re.search(r'<option value="Nein"[^>]*selected', form)
    assert re.search(r'name="q4" value="1"[^>]*checked', form)


def test_answers_are_a_snapshot_and_switched_off_fields_are_dropped():
    tenant = _tenant(_ff({"email": "off"}))
    data = {
        "name": "Kim",
        "email": "kim@example.com",
        "q1": "Nüsse",
        "q2": "zwei",  # битое число — нет ответа
        "q3": "Vielleicht",  # не из вариантов
        "q4": "1",
        "q99": "fremd",
    }
    _request, resp, _p = _post(data, tenant)
    order = Order.objects.get()
    assert order.customer.email == ""
    assert order.custom_answers == {
        "q1": {"label": "Allergien", "value": "Nüsse", "type": "text"},
        "q4": {"label": "Geschenkpapier", "value": True, "type": "bool"},
    }


def test_answers_do_not_change_the_money():
    without = _tenant()
    _post({"name": "Kim"}, without)
    with_answers = _tenant(_ff())
    _post({"name": "Kim", "q1": "Nüsse", "q2": "99"}, with_answers)
    a, b = Order.objects.order_by("created_at")
    assert (a.total, a.shipping_cents, a.discount_cents) == (
        b.total,
        b.shipping_cents,
        b.discount_cents,
    )
    assert [(i.qty, i.unit_price) for i in a.items.all()] == [
        (i.qty, i.unit_price) for i in b.items.all()
    ]
    assert b.custom_answers["q2"]["value"] == 99


def test_table_order_needs_no_contacts():
    tenant = _tenant(_ff({"email": "req", "phone": "req"}))
    _request, resp, _p = _post({"q1": "Nüsse"}, tenant, table="7")
    order = Order.objects.get()
    assert order.table_number == "7" and order.custom_answers["q1"]["value"] == "Nüsse"


def test_online_payment_without_email_is_still_refused(settings, monkeypatch):
    _configure(settings)
    monkeypatch.setattr(
        public_views.order_payments, "order_checkout_url", lambda o, t, **kw: "https://stripe/x"
    )
    tenant = _prepay_tenant()
    tenant.site_config = _ff({"email": "off"}, custom=[])
    _request, resp, _p = _post({"name": "Kim"}, tenant)
    assert resp.url.endswith("/warenkorb/") and not Order.objects.exists()


def test_snapshot_keeps_the_main_language_label_on_a_translated_storefront():
    custom = [
        {"id": "q1", "type": "text", "label": "Allergien", "label_i18n": {"ru": "Аллергии"}},
    ]
    tenant = _tenant(_ff(custom=custom))
    with translation.override("ru"):
        _post({"name": "Kim", "q1": "орехи"}, tenant)
    assert Order.objects.get().custom_answers["q1"]["label"] == "Allergien"


def test_create_order_without_answers_stores_nothing():
    order = services.create_order(items=[(ProductFactory(), 1)], name="K")
    assert order.custom_answers == {}


# ───────────── C4: показ снимка ─────────────

SNAP = {
    "q1": {"label": "Allergien", "value": "Nüsse <script>a()</script>", "type": "text"},
    "q4": {"label": "Geschenk<b>", "value": True, "type": "bool"},
}


def _order_with_answers(**kw):
    order = services.create_order(
        items=[(ProductFactory(name={"de": "Brot"}), 1)],
        name="Kim",
        email=f"k-{uuid.uuid4().hex[:6]}@example.com",
        **kw,
    )
    Order.objects.filter(pk=order.pk).update(custom_answers=dict(SNAP))
    order.refresh_from_db()
    return order


@TODO_C4
def test_card_shows_the_snapshot_escaped():
    order = _order_with_answers()
    body = views.order_detail(_cab_req(path=f"/dashboard/orders/{order.pk}/"), pk=order.pk)
    html = body.content.decode()
    assert "data-custom-answers" in html and "Allergien" in html
    assert "<script>a()" not in html and "&lt;script&gt;a()" in html and "Geschenk&lt;b&gt;" in html


@TODO_C4
def test_kitchen_board_shows_the_same_rows_as_the_card():
    order = _order_with_answers()
    html = views.kitchen_board(_cab_req()).content.decode()
    rows = deal_card._custom_answers(order)
    assert rows == form_answers.rows(order.custom_answers) and len(rows) == 2
    with translation.override("de"):
        html = views.kitchen_board(_cab_req()).content.decode()
    assert "data-kds-answers" in html
    assert "&lt;script&gt;a()" in html and "<script>a()" not in html
    assert "Geschenk&lt;b&gt;" in html


@TODO_C4
def test_renamed_question_keeps_the_old_label_everywhere():
    order = _order_with_answers()
    order.custom_answers = {"q1": {"label": "Allergien", "value": "Nüsse", "type": "text"}}
    order.save(update_fields=["custom_answers"])
    # владелец переименовал вопрос после заказа — снимок остаётся
    cab = views.order_detail(_cab_req(path=f"/dashboard/orders/{order.pk}/"), pk=order.pk)
    assert "Allergien" in cab.content.decode()
    assert "Allergien" in views.kitchen_board(_cab_req()).content.decode()


def test_status_change_through_the_fsm_keeps_the_snapshot():
    from apps.orders.state_machine import OrderSM

    order = _order_with_answers()
    OrderSM().apply(order, "confirmed")
    order.refresh_from_db()
    assert order.custom_answers == SNAP


@TODO_C4
def test_owner_mail_lists_the_answers_and_the_customer_mail_does_not(monkeypatch):
    from apps.orders import notifications

    sent = []
    monkeypatch.setattr(notifications, "notify", lambda **kw: sent.append(kw))
    monkeypatch.setattr(notifications, "_owner_email", lambda tenant: "owner@example.com")
    monkeypatch.setattr(notifications, "channel_enabled", lambda *a: True)
    order = _order_with_answers()
    sent.clear()
    with translation.override("de"):
        notifications.enqueue_order_email(order, "created")
    by_type = {m["type"]: m for m in sent}
    owner = by_type["order_created_owner"]["body"]
    assert "Allergien: Nüsse &lt;script&gt;a()&lt;/script&gt;" in owner
    assert "Geschenk&lt;b&gt;: " in owner
    customer = [m for m in sent if m["type"] != "order_created_owner"]
    assert customer and all("Allergien" not in (m["body"] + m["html"]) for m in customer)


@TODO_C4
def test_the_customer_sees_own_order_answers_in_the_account():
    from apps.account import account_data
    from apps.promotions.models import Customer

    order = _order_with_answers()
    customer = Customer.objects.get(pk=order.customer_id)
    section = account_data._orders(customer)
    assert section["items"][0]["answers"] == form_answers.rows(SNAP)
