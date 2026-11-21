"""FB-33 M2i-7 (решение владельца 2026-11-21): онлайн-оплата заказа без e-mail в форме.

Снято решение M2i-3a («без e-mail онлайн-оплата не оформляется»): если форма адрес не
спросила или гость его не дал, заказ всё равно уходит в Stripe, а адрес берётся из
`customer_details.email` вебхука — только у оплаченной сессии (`paid`, в т.ч.
`async_payment_succeeded`), только в пустой `Customer.email`, только валидный. Письма
`created` и `confirmed` уходят ровно по разу (dedupe_key), выключенный канал и отписка
уважаются, аккаунт клиента не создаётся и заказ к другому клиенту не перепривязывается.
Введённый, но невалидный e-mail при онлайн-оплате — отказ с возвратом введённого.
"""

import logging
import uuid
from decimal import Decimal

import pytest
from django.contrib.messages.middleware import MessageMiddleware
from django.contrib.sessions.middleware import SessionMiddleware
from django.db import connection
from django.test import RequestFactory

from apps.billing import webhooks
from apps.catalog.tests.factories import ProductFactory
from apps.notifications.models import Notification
from apps.orders import public_views, services
from apps.orders.models import Order
from apps.orders.state_machine import OrderSM
from apps.orders.tests.test_payment_methods import _configure, _prepay_tenant, _pub_req
from apps.promotions.models import Customer
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db

ACCOUNT = "acct_m2i7"
PAYER = "zahler@example.com"
_MISSING = object()


@pytest.fixture(autouse=True)
def _tenant_urlconf(settings):
    settings.ROOT_URLCONF = "config.urls_tenant"


@pytest.fixture
def biz():
    """Тенант текущей схемы с connected account — вебхук принимает только его события."""
    return TenantFactory(schema_name=connection.schema_name, stripe_connect_id=ACCOUNT)


def _order(email="", **kw):
    return services.create_order(
        items=[(ProductFactory(base_price=Decimal("10.00")), 1)],
        name="Kunde",
        email=email,
        payment_method=Order.METHOD_STRIPE,
        **kw,
    )


def _obj(order, *, status="paid", details=_MISSING, email=PAYER):
    obj = {
        "payment_intent": f"pi_{uuid.uuid4().hex[:8]}",
        "payment_status": status,
        "metadata": {
            "kind": "order_payment",
            "tenant_schema": connection.schema_name,
            "order_id": str(order.id),
        },
    }
    if details is _MISSING:
        obj["customer_details"] = {"email": email, "name": "Zahler"}
    elif details is not None:
        obj["customer_details"] = details
    return obj


def _hook(order, event="checkout.session.completed", account=ACCOUNT, **kw):
    webhooks.handle_event(event, _obj(order, **kw), account=account)
    order.refresh_from_db()
    return order


def _mails(order, event):
    return Notification.objects.filter(dedupe_key=f"order:{order.id}:{event}:customer")


def _email_of(order):
    return Customer.objects.get(pk=order.customer_id).email


# ───────────── 1–2: витрина ─────────────


@pytest.mark.xfail(strict=True, reason="M2i-7 C2: отказ M2i-3a ещё не снят")
@pytest.mark.parametrize("cfg", [{}, {"form_fields": {"checkout": {"mode": {"email": "off"}}}}])
def test_online_payment_without_email_goes_to_stripe(settings, monkeypatch, cfg):
    """1. Без e-mail (форма не спросила или поле пустое) заказ создаётся и уходит в Stripe."""
    _configure(settings)
    seen = []
    monkeypatch.setattr(
        public_views.order_payments,
        "order_checkout_url",
        lambda o, t, **kw: seen.append(o.pk) or "https://stripe/x",
    )
    tenant = _prepay_tenant()
    tenant.site_config = cfg
    product = ProductFactory(base_price=Decimal("10.00"))
    request = _pub_req(
        {"name": "Kunde", "email": ""}, tenant=tenant, session={"cart": {str(product.pk): 1}}
    )
    resp = public_views.checkout(request)
    order = Order.objects.get()
    assert resp.url == "https://stripe/x" and seen == [order.pk]
    assert order.payment_method == Order.METHOD_STRIPE and order.customer.email == ""


def test_online_payment_with_an_invalid_email_is_refused_with_the_input_kept(settings):
    """2. Введённый, но невалидный адрес при онлайн-оплате — отказ, введённое ждёт в корзине."""
    _configure(settings)
    product = ProductFactory(base_price=Decimal("10.00"))
    data = {"name": "Kim", "email": "kein-email", "phone": "0171", "note": "Ohne Nüsse"}
    request = _pub_req(data, tenant=_prepay_tenant(), session={"cart": {str(product.pk): 1}})
    resp = public_views.checkout(request)
    assert resp.url.endswith("/warenkorb/") and not Order.objects.exists()
    assert request.session[public_views.CHECKOUT_INPUT_KEY] == data


# ───────────── 3–11: вебхук ─────────────


def test_email_from_the_form_wins_over_the_payer_email(biz):
    """3. A в форме, B в Stripe → у клиента A, письма — на A."""
    order = _hook(_order("form@example.com"))
    assert _email_of(order) == "form@example.com"
    assert order.payment_state == Order.PAYMENT_PAID
    assert not Notification.objects.filter(recipient=PAYER).exists()


@pytest.mark.xfail(strict=True, reason="M2i-7 C1: вебхук ещё не берёт адрес плательщика")
def test_paid_session_adopts_the_payer_email_and_mails_once(biz):
    """4. paid → адрес записан, created и confirmed — по одному письму; повтор — без новых."""
    order = _order()
    assert not _mails(order, "created").exists()
    _hook(order)
    _hook(order)
    assert _email_of(order) == PAYER
    assert order.status == Order.STATUS_CONFIRMED and order.payment_state == Order.PAYMENT_PAID
    for event in ("created", "confirmed"):
        mails = list(_mails(order, event))
        assert [m.recipient for m in mails] == [PAYER], event
    created, confirmed = _mails(order, "created").get(), _mails(order, "confirmed").get()
    assert created.pk < confirmed.pk  # сначала «принят», потом «подтверждён»


@pytest.mark.xfail(strict=True, reason="M2i-7 C1: вебхук ещё не берёт адрес плательщика")
def test_delayed_payment_adopts_the_email_once_money_arrives(biz):
    """4. unpaid → async_payment_succeeded: адрес и письма — только по зачислении, по разу."""
    order = _hook(_order(), status="unpaid")
    assert _email_of(order) == "" and order.payment_state != Order.PAYMENT_PAID
    _hook(order, "checkout.session.async_payment_succeeded")
    _hook(order, "checkout.session.async_payment_succeeded")
    assert _email_of(order) == PAYER and order.payment_state == Order.PAYMENT_PAID
    assert _mails(order, "created").count() == 1 and _mails(order, "confirmed").count() == 1


def test_unpaid_session_writes_nothing(biz):
    """5. Деньги в пути (unpaid) — ни адреса, ни писем, ни оплаты."""
    order = _hook(_order(), status="unpaid")
    assert _email_of(order) == "" and order.payment_state == Order.PAYMENT_UNPAID
    assert not Notification.objects.filter(recipient=PAYER).exists()


@pytest.mark.parametrize(
    "details",
    [
        {"email": "x"},
        {"email": "k@example.com\r\nBcc: evil@example.com"},
        {"email": ("a" * 250) + "@example.com"},
        {"email": None},
        {"email": 42},
        {},
        None,
        "kaputt",
    ],
    ids=["no-at", "crlf", "too-long", "none", "number", "no-email", "no-details", "not-a-dict"],
)
def test_bad_payer_email_is_ignored_and_the_order_still_paid(biz, details):
    """6. Плохой адрес/нет details — без записи и без исключения; заказ оплачен."""
    order = _hook(_order(), details=details)
    assert _email_of(order) == ""
    assert order.payment_state == Order.PAYMENT_PAID and order.status == Order.STATUS_CONFIRMED
    assert not _mails(order, "created").exists() and not _mails(order, "confirmed").exists()


def test_foreign_account_writes_no_email(biz):
    """7. Событие с чужого connected account отбрасывается целиком (SEC-D1) — адреса нет."""
    order = _hook(_order(), account="acct_evil")
    assert _email_of(order) == "" and order.payment_state == Order.PAYMENT_UNPAID


@pytest.mark.xfail(strict=True, reason="M2i-7 C1: вебхук ещё не берёт адрес плательщика")
def test_order_is_not_moved_to_another_customer(biz):
    """8. Есть клиент с адресом плательщика — заказ не перепривязывается, аккаунт не создаётся;
    у клиента с адресом из формы customer_id и адрес не меняются."""
    from django.contrib.auth import get_user_model

    other = Customer.objects.create(name="Alt", email=PAYER)
    users = get_user_model().objects.count()
    order = _order()
    own = order.customer_id
    _hook(order)
    assert order.customer_id == own != other.pk and _email_of(order) == PAYER
    assert get_user_model().objects.count() == users

    known = _order("known@example.com")
    known_id = known.customer_id
    _hook(known)
    assert known.customer_id == known_id and _email_of(known) == "known@example.com"


def test_payer_email_never_reaches_the_logs(biz, caplog):
    """9. Ни принятый, ни отвергнутый адрес плательщика не пишется в логи."""
    caplog.set_level(logging.DEBUG)
    _hook(_order())
    _hook(_order(), email="evil\r\n@example.com")
    _hook(_order(), status="unpaid")
    text = caplog.text
    assert PAYER not in text and "evil" not in text and "zahler" not in text


@pytest.mark.xfail(strict=True, reason="M2i-7 C1: вебхук ещё не берёт адрес плательщика")
def test_switched_off_channel_writes_the_email_without_mails(biz):
    """10. Канал e-mail выключен у бизнеса — адрес записан, писем нет."""
    biz.site_config = {
        "notify": {
            "customer": {
                "order:created": {"email": False},
                "order:confirmed": {"email": False},
            }
        }
    }
    biz.save(update_fields=["site_config"])
    order = _hook(_order())
    assert _email_of(order) == PAYER
    assert not _mails(order, "created").exists() and not _mails(order, "confirmed").exists()


@pytest.mark.xfail(strict=True, reason="M2i-7 C1: вебхук ещё не берёт адрес плательщика")
def test_unsubscribed_customer_gets_the_email_but_no_mails(biz):
    """10 (развилка b). Отписка уважается: адрес записан, писем нет."""
    order = _order()
    Customer.objects.filter(pk=order.customer_id).update(unsubscribed=True)
    _hook(order)
    assert _email_of(order) == PAYER
    assert not _mails(order, "created").exists() and not _mails(order, "confirmed").exists()


@pytest.mark.xfail(strict=True, reason="M2i-7 C1: вебхук ещё не берёт адрес плательщика")
def test_order_cancelled_before_payment_gets_the_email_without_created(biz):
    """11. Заказ отменён до прихода денег — адрес записан, письма «принят» нет."""
    order = _order()
    OrderSM().apply(order, Order.STATUS_CANCELLED)
    _hook(order)
    assert _email_of(order) == PAYER and order.status == Order.STATUS_CANCELLED
    assert not _mails(order, "created").exists() and not _mails(order, "confirmed").exists()


@pytest.mark.xfail(strict=True, reason="M2i-7 C1: вебхук ещё не берёт адрес плательщика")
def test_owner_confirmed_before_payment_still_mails_confirmed_once(biz):
    """4 (край). Владелец подтвердил заказ до оплаты (адреса ещё не было) — «confirmed»
    уходит после записи адреса один раз; «принят» — нет (заказ уже не новый)."""
    order = _order()
    OrderSM().apply(order, Order.STATUS_CONFIRMED)
    _hook(order)
    _hook(order)
    assert _email_of(order) == PAYER
    assert _mails(order, "confirmed").count() == 1 and not _mails(order, "created").exists()


# ───────────── 12: страница подтверждения ─────────────


def _confirmation(order, query=""):
    request = RequestFactory().get(f"/bestellung/{order.reference_code}/{query}")
    SessionMiddleware(lambda r: None).process_request(request)
    MessageMiddleware(lambda r: None).process_request(request)
    request.tenant = _prepay_tenant()
    return public_views.order_confirmation(request, code=order.reference_code).content.decode()


HINT = "Die Bestätigung senden wir an die E-Mail-Adresse aus der Zahlung."


@pytest.mark.xfail(strict=True, reason="M2i-7 C3: подсказки на подтверждении ещё нет")
def test_confirmation_page_says_where_the_mail_goes_without_the_address():
    """12. Онлайн-заказ без адреса: подсказка «письмо — на адрес из оплаты», без самого адреса."""
    from django.utils import translation

    order = _order()
    with translation.override("de"):
        html = _confirmation(order, "?paid=1")
    assert HINT in html
    line = html[html.rindex("<p", 0, html.index(HINT)) : html.index("</p>", html.index(HINT))]
    assert "@" not in line and "mailto" not in line
    with_email = _order("k@example.com")
    with translation.override("de"):
        assert HINT not in _confirmation(with_email, "?paid=1")
