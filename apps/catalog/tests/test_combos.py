"""A4 Gastro: комбо-наборы — модель, расчёт/валидация, CRUD-вьюхи (кабинет)."""

from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from django.contrib.messages.middleware import MessageMiddleware
from django.contrib.sessions.middleware import SessionMiddleware
from django.test import RequestFactory

from apps.catalog import combos, views
from apps.catalog.models import Combo, ComboGroup, ComboOption
from apps.catalog.tests.factories import ProductFactory

pytestmark = pytest.mark.django_db


@pytest.fixture
def user(db):
    return get_user_model().objects.create_user(
        username="o", email="o@test.de", password="pw12345678"
    )


def _post(user, data):
    req = RequestFactory().post("/x/", data)
    SessionMiddleware(lambda r: None).process_request(req)
    MessageMiddleware(lambda r: None).process_request(req)
    req.user = user
    return req


def _combo_with_drink_choice():
    """Комбо: фикс бургер (группа 1 опция) + выбор напитка (надбавка за Groß)."""
    combo = Combo.objects.create(name="Menü 1", price=Decimal("9.90"))
    burger = ProductFactory(base_price=Decimal("7.00"))
    drink_g = ComboGroup.objects.create(combo=combo, label="Getränk", min_select=1, max_select=1)
    cola = ComboOption.objects.create(group=drink_g, product=ProductFactory(), price_delta=0)
    cola_gr = ComboOption.objects.create(
        group=drink_g, product=ProductFactory(), price_delta=Decimal("1.00")
    )
    fixed_g = ComboGroup.objects.create(combo=combo, label="Burger", min_select=1, max_select=1)
    ComboOption.objects.create(group=fixed_g, product=burger, price_delta=0)
    return combo, cola, cola_gr


# --- расчёт / валидация -----------------------------------------------------------


def test_combo_price_adds_option_deltas():
    combo, cola, cola_gr = _combo_with_drink_choice()
    assert combos.combo_price(combo, []) == Decimal("9.90")
    assert combos.combo_price(combo, [cola_gr]) == Decimal("10.90")  # +1,00 за Groß


def test_validate_requires_each_group_choice():
    combo, cola, _ = _combo_with_drink_choice()
    # без выбора напитка — ошибка (min_select=1 у обеих групп)
    options, error = combos.validate_selection(combo, [])
    assert options == [] and error


def test_validate_ok_with_one_per_group():
    combo, cola, _ = _combo_with_drink_choice()
    fixed_opt = combo.groups.get(label="Burger").options.first()
    options, error = combos.validate_selection(combo, [str(cola.pk), str(fixed_opt.pk)])
    assert error == "" and {o.pk for o in options} == {cola.pk, fixed_opt.pk}


def test_validate_max_exceeded():
    combo = Combo.objects.create(name="X", price=Decimal("5"))
    g = ComboGroup.objects.create(combo=combo, label="Beilage", min_select=0, max_select=1)
    a = ComboOption.objects.create(group=g, product=ProductFactory(), price_delta=0)
    b = ComboOption.objects.create(group=g, product=ProductFactory(), price_delta=0)
    options, error = combos.validate_selection(combo, [str(a.pk), str(b.pk)])
    assert error  # больше max


# --- CRUD-вьюхи -------------------------------------------------------------------


def test_combo_create_and_group_option(user):
    views.combo_create(_post(user, {"name": "Menü", "price": "9,90", "is_active": "on"}))
    combo = Combo.objects.get()
    assert combo.price == Decimal("9.90")

    views.combo_group_add(_post(user, {"label": "Getränk", "min": "1", "max": "1"}), pk=combo.pk)
    group = combo.groups.get()
    product = ProductFactory()
    views.combo_option_add(
        _post(user, {"product": str(product.pk), "delta": "1,00"}), pk=combo.pk, gid=group.pk
    )
    opt = group.options.get()
    assert opt.product_id == product.pk and opt.price_delta == Decimal("1.00")
