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
def test_order_detail_status_actions_sit_in_the_status_card():
    """SH-10 (2026-08-20) требовал кнопки статуса в шапке. DC-1 (ТЗ владельца
    2026-08-25, «статус перенести во вторую колонку») переносит их в карточку
    статуса правой колонки — ОДНУ на все виды сделок; приёмник generic
    (board-action), тот же путь, что доска и списки. Замок переписан осознанно:
    отдельной карточки действий по-прежнему нет, статус — ровно один блок."""
    from apps.core import views as core_views  # noqa: F401
    from apps.orders import views as order_views

    order = _order(code="O-SH0004")
    req = _req(f"/dashboard/orders/{order.pk}/")
    body = order_views.order_detail(req, order.pk).content.decode()
    assert "O-SH0004" in body
    assert body.count('data-deal-block="status"') == 1
    assert body.index("data-deal-rail") < body.index('data-deal-block="status"')
    assert f"/dashboard/board/order/{order.pk}/action/" in body


# --- п.15: клиенты вкладкой в продажах (решение владельца «всем архетипам») ---
def test_customers_tab_shows_crm_list_inside_sales():
    from apps.promotions.models import Customer

    Customer.objects.create(name="Klara Kundin", email="k@t.de")
    body = views.verkaeufe(_req(data={"tab": "kunden"})).content.decode()
    assert "Klara Kundin" in body
    assert "data-kunden-tab" in body
    # У вкладки клиентов нет ни видов, ни «Abläufe» — только «＋» и кросс-входы
    assert "data-sales-view-switch" not in body


def test_customers_tab_works_without_crm_module():
    """Решение владельца: вкладка «Kunden» — у ВСЕХ архетипов, БЕЗ включения CRM.
    Модуль остаётся гейтом карточки/тегов/экспорта, поэтому ссылок туда нет."""
    from apps.core.modules import default_disabled_for
    from apps.promotions.models import Customer

    no_crm = _tenant(disabled_modules=list(default_disabled_for("retail")) + ["crm"])
    Customer.objects.create(name="Ohne CRM", email="o@t.de")
    body = views.verkaeufe(_req(data={"tab": "kunden"}, tenant=no_crm)).content.decode()
    assert "data-kunden-tab" in body
    assert "Ohne CRM" in body  # список читается
    assert "/crm/" not in body  # ссылок в гейтнутый модуль нет (класс 404 из X-сверки)
    assert "data-no-crm" in body


def test_customer_list_screen_and_sales_tab_share_one_body():
    """Один партиал/один контекст — расхождению данных взяться неоткуда."""
    from apps.crm.views import customer_list
    from apps.promotions.models import Customer

    Customer.objects.create(name="Klara Kundin", email="k2@t.de")
    tenant = _tenant()
    screen = customer_list(_req("/dashboard/crm/", tenant=tenant)).content.decode()
    tab = views.verkaeufe(_req(data={"tab": "kunden"}, tenant=tenant)).content.decode()
    assert "Klara Kundin" in screen and "Klara Kundin" in tab


# --- п.14: доставка отдельным входом ------------------------------------------
def test_delivery_filter_narrows_the_order_list():
    _order(code="O-SH0005", name="Lieferkunde", fulfillment="delivery")
    _order(code="O-SH0006", name="Abholkunde")
    all_body = views.verkaeufe(_req(data={"tab": "order", "view": "liste"})).content.decode()
    assert "O-SH0005" in all_body and "O-SH0006" in all_body
    only = views.verkaeufe(
        _req(data={"tab": "order", "view": "liste", "versand": "1"})
    ).content.decode()
    assert "O-SH0005" in only and "O-SH0006" not in only


def test_delivery_entry_is_a_sidebar_subitem_of_sales():
    from apps.core import nav_registry as nr

    board = next(a for a in nr.ANCHORS if a.nav_key == "board")
    children = {(e.url_name, e.query) for e in nr.sidebar_children(board)}
    # R7-3 (осознанная переписка SH-14): доставка — СВОЯ страница с накладными
    # и трек-номерами, а не фильтр списка (фидбэк владельца 2026-08-24).
    assert ("orders:deliveries", "") in children
    assert ("verkaeufe", "?tab=kunden") in children


def test_delivery_filter_forces_a_view_that_honors_it():
    """Ревью 2026-08-19: фильтр в адресе обязан быть исполнен — доска ?versand=
    не понимает, поэтому вид падает на «Liste»."""
    assert sales_page.view_for_filters("order", "board", {"versand": "1"}) == "liste"
    assert sales_page.view_for_filters("order", "liste", {"versand": "1"}) == "liste"


# --- п.5: правка клиента на ВСЕХ архетипах ------------------------------------
def test_deal_customer_edit_works_for_every_kind():
    """Приёмник kind-агностичный: у каждой сделки есть `customer`, поэтому
    контакт правится и у брони номера, и у записи, и у заявки — не только у заказа."""
    from datetime import date, timedelta

    from django.test import RequestFactory

    from apps.core import views as core_views
    from apps.stays.models import Customer as StayCustomer
    from apps.stays.models import StayBooking, StayUnit

    unit = StayUnit.objects.create(name="Zimmer 2", max_guests=2, price_cents=9000)
    booking = StayBooking.objects.create(
        unit=unit,
        customer=StayCustomer.objects.create(name="Alt", email="alt@t.de"),
        arrival=date.today() + timedelta(days=2),
        departure=date.today() + timedelta(days=4),
        guests=2,
        reference_code="S-SH0100",
    )
    req = RequestFactory().post(
        f"/dashboard/kunde/stay/{booking.pk}/",
        {"name": "Neu Gast", "phone": "+49 222", "next": "/dashboard/verkaeufe/"},
    )
    SessionMiddleware(lambda r: None).process_request(req)
    MessageMiddleware(lambda r: None).process_request(req)
    req.user = _User()
    req.tenant = _tenant("hotel")
    resp = core_views.deal_customer_edit(req, "stay", booking.pk)
    assert resp.status_code == 302 and resp["Location"] == "/dashboard/verkaeufe/"
    booking.refresh_from_db()
    assert booking.customer.name == "Neu Gast" and booking.customer.phone == "+49 222"
    assert booking.customer.email == "alt@t.de"  # пустое поле не затирает


def test_deal_customer_edit_rejects_unknown_kind():
    from django.http import Http404
    from django.test import RequestFactory

    from apps.core import views as core_views

    req = RequestFactory().post("/dashboard/kunde/hack/00000000-0000-0000-0000-000000000000/")
    SessionMiddleware(lambda r: None).process_request(req)
    MessageMiddleware(lambda r: None).process_request(req)
    req.user = _User()
    req.tenant = _tenant()
    with pytest.raises(Http404):
        core_views.deal_customer_edit(req, "hack", "00000000-0000-0000-0000-000000000000")
