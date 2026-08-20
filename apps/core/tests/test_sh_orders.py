"""SH-волна (фидбэк владельца 2026-08-20 по разделу продаж магазина).

План — `docs/sh-order-wave-plan-2026-08-20.md`. Группа A — «быстрые»: список как
главная поверхность магазина (без пустого календаря), смена статуса из строки,
порядковый номер и покупатель в строке, мельче шрифт, свёрнутый сайдбар полосой
иконок, вход в настройки оплаты/доставки из настроек раздела.
"""

import uuid

import pytest
from django.contrib.messages.middleware import MessageMiddleware
from django.contrib.sessions.middleware import SessionMiddleware
from django.test import RequestFactory

from apps.core import sales_page, views
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _urlconf(settings):
    settings.ROOT_URLCONF = "config.urls_tenant"


class _User:
    is_authenticated = True
    is_active = True
    username = "owner"


def _tenant(business_type="retail", **kw):  # «Shop» владельца = Einzelhandel
    from apps.core.modules import default_disabled_for

    kw.setdefault("disabled_modules", list(default_disabled_for(business_type)))
    return TenantFactory(schema_name=f"t{uuid.uuid4().hex[:8]}", business_type=business_type, **kw)


def _req(path="/dashboard/verkaeufe/", data=None, tenant=None, **tkw):
    req = RequestFactory().get(path, data or {})
    SessionMiddleware(lambda r: None).process_request(req)
    MessageMiddleware(lambda r: None).process_request(req)
    req.user = _User()
    req.tenant = tenant if tenant is not None else _tenant(**tkw)
    return req


def _order(code="O-SH0001", name="Anna Beispiel", **kw):
    from apps.orders.models import Customer, Order

    customer = Customer.objects.create(name=name, email=f"{uuid.uuid4().hex[:6]}@t.de")
    return Order.objects.create(customer=customer, reference_code=code, **kw)


# --- п.1: «календарь не нужен, главная страница продаж — список» -------------
def test_order_calendar_view_hidden_without_pickup_slots():
    """Auftragsbuch (V3) осмыслен только когда слоты выдачи реально ставятся.
    У магазина их нет — вид всегда пуст и читается как поломка."""
    tenant = _tenant()
    assert "kalender" not in sales_page.views_for("order", tenant)
    assert sales_page.views_for("stay", tenant) == ("kalender", "board", "liste")


def test_order_calendar_view_returns_when_slots_are_used():
    from datetime import timedelta

    from django.utils import timezone

    _order(code="O-SH0009", pickup_slot=timezone.now() + timedelta(days=1))
    assert "kalender" in sales_page.views_for("order", _tenant("bakery"))


# --- пп.11/12/16: строка списка ----------------------------------------------
def test_order_list_row_has_index_customer_and_status_menu():
    _order(code="O-SH0002")
    body = views.verkaeufe(_req(data={"tab": "order", "view": "liste"})).content.decode()
    assert "O-SH0002" in body
    assert "👤 Anna Beispiel" in body  # SH-12: покупатель прямо в строке
    assert "data-row-status" in body  # SH-11: меню смены статуса в строке
    # SH-11: приёмник — общий board-action (тот же путь, что у доски)
    assert "/dashboard/board/order/" in body and "/action/" in body


def test_generic_list_row_has_status_menu_for_other_kinds():
    """«Проверяй остальные архетипы»: механика строки общая для stay/booking/
    job/ticket — generic-список идёт через тот же партиал."""
    from datetime import date, timedelta

    from apps.stays.models import Customer, StayBooking, StayUnit

    unit = StayUnit.objects.create(name="Zimmer 1", max_guests=2, price_cents=9000)
    StayBooking.objects.create(
        unit=unit,
        customer=Customer.objects.create(name="Herr Gast", email="g@t.de"),
        arrival=date.today() + timedelta(days=3),
        departure=date.today() + timedelta(days=5),
        guests=2,
        reference_code="S-SH0001",
    )
    tenant = _tenant("hotel")
    body = views.verkaeufe(
        _req(data={"tab": "stay", "view": "liste"}, tenant=tenant)
    ).content.decode()
    assert "S-SH0001" in body and "👤 Herr Gast" in body
    assert "data-row-status" in body


def test_kanban_card_font_is_smaller():
    """SH-16: на доске помещается больше сделок — заголовок 13px, детали 11px."""
    _order(code="O-SH0003")
    body = views.verkaeufe(_req(data={"tab": "order", "view": "board"})).content.decode()
    assert "text-[13px] font-medium text-gray-900" in body
    assert "text-sm font-medium text-gray-900" not in body


# --- п.13: вход в настройки оплаты/доставки из настроек раздела --------------
def test_ablaeufe_links_to_payment_settings_for_orders():
    body = views.ablaeufe_view(
        _req("/dashboard/ablaeufe/", data={"kind": "order"})
    ).content.decode()
    assert "Zahlung & Lieferung einstellen" in body
    assert "/dashboard/settings/payments/" in body
    # У направления без оплаты заказов карточки нет (ссылка в сайдбаре не в счёт)
    hotel = _tenant("hotel")
    other = views.ablaeufe_view(
        _req("/dashboard/ablaeufe/", data={"kind": "stay"}, tenant=hotel)
    ).content.decode()
    assert "Zahlung & Lieferung einstellen" not in other


# --- п.17: свёрнутый сайдбар = полоса иконок ---------------------------------
def test_collapsed_sidebar_keeps_icons():
    body = views.verkaeufe(_req()).content.decode()
    assert "body.sb-min #sidebar { display: none; }" not in body
    assert "body.sb-min #sidebar { width: 3.5rem; }" in body
    assert "sb-label" in body  # скрываются подписи, не сам сайдбар


# --- п.10: смена статуса в одной строке с номером ----------------------------
def test_order_detail_status_actions_sit_in_the_header():
    from apps.core import views as core_views  # noqa: F401
    from apps.orders import views as order_views

    order = _order(code="O-SH0004")
    req = _req(f"/dashboard/orders/{order.pk}/")
    body = order_views.order_detail(req, order.pk).content.decode()
    assert "O-SH0004" in body
    # Кнопка перехода живёт ДО карточки позиций, отдельной карточки действий нет
    assert body.index('name="action"') < body.index("divide-y divide-gray-100 border-y")
    assert body.count(f"/dashboard/orders/{order.pk}/action/") == 1
