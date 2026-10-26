"""KA-12 GA-9 (Gastro): Tageskarte — блюдо только в определённые дни недели.

Предзаказ на нужный день возможен (in_stock не трогаем); заказ на «чужой» день выдачи
отказывает до списания склада; фасет «Heute auf der Karte»; форма с сентинелом."""

from datetime import date, datetime, time, timedelta
from decimal import Decimal

import pytest
from django.utils import timezone

from apps.catalog.facets import CatalogFacets
from apps.catalog.forms import ProductForm
from apps.catalog.models import Product
from apps.catalog.pdf import build_menu_pdf
from apps.catalog.tests.factories import ProductFactory
from apps.orders import services
from apps.orders.models import Order
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db

TODAY = timezone.localdate()
OTHER = (TODAY.weekday() + 1) % 7


def _next(weekday):
    d = TODAY + timedelta(days=1)
    while d.weekday() != weekday:
        d += timedelta(days=1)
    return d


def _slot(day):
    return datetime.combine(day, time(12), tzinfo=timezone.get_current_timezone())


def test_available_on_and_label():
    p = ProductFactory(available_weekdays=[0, 2])
    assert p.available_on(date(2026, 10, 26))  # Montag
    assert not p.available_on(date(2026, 10, 27))  # Dienstag
    assert p.weekdays_label  # «Mo · Mi»
    assert ProductFactory(available_weekdays=[]).weekdays_label == ""
    assert ProductFactory(available_weekdays=list(range(7))).weekdays_label == ""
    # мусор не делает блюдо недоступным навсегда
    assert ProductFactory(available_weekdays=["x", 99]).available_on(TODAY)


def test_preorder_stays_possible_in_stock_untouched():
    p = ProductFactory(available_weekdays=[OTHER])
    assert p.in_stock and not p.is_on_menu_today


def test_create_order_refuses_wrong_pickup_day_without_touching_stock():
    p = ProductFactory(base_price=Decimal("9.50"), stock_quantity=5, available_weekdays=[OTHER])
    with pytest.raises(services.NotOnMenu) as exc:
        services.create_order(items=[(p, 1)], name="K")  # без слота — сегодня
    assert exc.value.days == p.weekdays_label
    assert isinstance(exc.value, services.OutOfStock)  # старые обработчики ловят
    wrong = _next((OTHER + 1) % 7)
    with pytest.raises(services.NotOnMenu):
        services.create_order(items=[(p, 1)], name="K", pickup_slot=_slot(wrong))
    assert Order.objects.count() == 0
    p.refresh_from_db()
    assert p.stock_quantity == 5
    order = services.create_order(items=[(p, 2)], name="K", pickup_slot=_slot(_next(OTHER)))
    assert order.pk
    p.refresh_from_db()
    assert p.stock_quantity == 3


def test_facet_heute_filters_and_counts():
    always = ProductFactory(available_weekdays=[])
    today = ProductFactory(available_weekdays=[TODAY.weekday()])
    other = ProductFactory(available_weekdays=[OTHER])
    qs = Product.objects.filter(pk__in=[always.pk, today.pk, other.pk])
    got = set(CatalogFacets().apply(qs, {"heute": "1"}).values_list("pk", flat=True))
    assert got == {always.pk, today.pk}
    assert CatalogFacets().present(qs, {})["heute_count"] == 2
    plain = Product.objects.filter(pk=always.pk)
    assert CatalogFacets().present(plain, {})["heute_count"] == 0  # нет расписаний — чипа нет


def _form_data(**over):
    data = {"name_de": "Fischteller", "base_price": "14.50", "currency": "EUR"}
    data.update(over)
    return data


def test_form_saves_days_with_sentinel_and_keeps_without():
    form = ProductForm(_form_data(weekdays_present="1", available_weekdays=["4"]))
    assert form.is_valid(), form.errors
    p = form.save()
    p.refresh_from_db()
    assert p.available_weekdays == [4]
    # без сентинела (мастер/импорт) расписание не стирается
    form = ProductForm(_form_data(), instance=p)
    assert form.is_valid(), form.errors
    form.save()
    p.refresh_from_db()
    assert p.available_weekdays == [4]
    # все 7 дней = каждый день
    form = ProductForm(
        _form_data(weekdays_present="1", available_weekdays=[str(i) for i in range(7)]),
        instance=p,
    )
    assert form.is_valid(), form.errors
    form.save()
    p.refresh_from_db()
    assert p.available_weekdays == []
    assert ProductForm(instance=p).fields["available_weekdays"].initial == []


def test_menu_pdf_renders_with_weekday_note():
    p = ProductFactory(available_weekdays=[4])
    pdf = build_menu_pdf(TenantFactory.build(), [("Karte", [p])])
    assert pdf[:4] == b"%PDF"
