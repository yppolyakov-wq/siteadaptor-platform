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


def test_product_list_shows_combos_teaser(settings):
    """A4: меню показывает тизер-карточки комбо вверху (Kombo/Tagesgericht на виду)."""
    settings.ROOT_URLCONF = "config.urls_tenant"
    from apps.promotions import public_views as promo_views
    from apps.tenants.tests.factories import TenantFactory

    _combo_with_drink_choice()  # создаёт активное комбо «Menü 1»
    req = RequestFactory().get("/sortiment/")
    SessionMiddleware(lambda r: None).process_request(req)
    MessageMiddleware(lambda r: None).process_request(req)
    req.tenant = TenantFactory.build(name="Bistro")
    body = promo_views.product_list(req).content.decode()
    assert "Menü 1" in body  # карточка комбо в тизере
    assert "9,90" in body or "9.90" in body  # цена комбо


def test_product_list_combos_teaser_hidden_in_category(settings):
    """Регрессия A4: в выбранной категории тизер комбо не дублируется (только ссылка)."""
    settings.ROOT_URLCONF = "config.urls_tenant"
    from apps.catalog.models import Category
    from apps.promotions import public_views as promo_views
    from apps.tenants.tests.factories import TenantFactory

    _combo_with_drink_choice()
    cat = Category.objects.create(name="Burger", slug="burger", is_active=True)
    ProductFactory(category=cat)
    req = RequestFactory().get("/sortiment/", {"kategorie": "burger"})
    SessionMiddleware(lambda r: None).process_request(req)
    MessageMiddleware(lambda r: None).process_request(req)
    req.tenant = TenantFactory.build(name="Bistro")
    body = promo_views.product_list(req).content.decode()
    assert "Menü 1" not in body  # тизер скрыт в категории


# --- MEN-2: поля «набора меню» + included-группы -----------------------------------


def _combo_with_included():
    """Фикс-состав (included) + одна группа выбора."""
    combo = Combo.objects.create(name="Hochzeitsmenü", price=Decimal("45.00"))
    inc = ComboGroup.objects.create(
        combo=combo, label="Im Menü", included=True, min_select=1, max_select=1
    )
    inc_opt = ComboOption.objects.create(
        group=inc, product=ProductFactory(), price_delta=Decimal("5.00")
    )
    choice = ComboGroup.objects.create(combo=combo, label="Dessert", min_select=1, max_select=1)
    tarte = ComboOption.objects.create(group=choice, product=ProductFactory(), price_delta=0)
    return combo, inc_opt, tarte


def test_included_group_not_validated_and_not_priced():
    """MEN-2: included-группа не требует выбора, а id её опций из POST не меняют
    цену — стоимость фикс-состава уже заложена в Combo.price."""
    combo, inc_opt, tarte = _combo_with_included()
    options, error = combos.validate_selection(combo, [str(tarte.pk)])
    assert error == "" and [o.pk for o in options] == [tarte.pk]
    # злонамеренный POST с id included-опции — надбавка НЕ прибавляется
    picked = combos.options_from_ids(combo, [str(inc_opt.pk), str(tarte.pk)])
    assert [o.pk for o in picked] == [tarte.pk]
    assert combos.combo_price(combo, picked) == Decimal("45.00")


def test_combo_price_from_min_deltas():
    """MEN-2: «ab»-цена = фикс + min_select наименьших надбавок обязательных групп;
    опциональные (min=0) и included-группы не входят."""
    combo = Combo.objects.create(name="Wahl", price=Decimal("30.00"))
    g = ComboGroup.objects.create(combo=combo, label="Hauptgang", min_select=2, max_select=2)
    for delta in ("4.00", "1.00", "2.00"):
        ComboOption.objects.create(group=g, product=ProductFactory(), price_delta=Decimal(delta))
    extra = ComboGroup.objects.create(combo=combo, label="Extra", min_select=0, max_select=1)
    ComboOption.objects.create(group=extra, product=ProductFactory(), price_delta=Decimal("9.00"))
    assert combos.combo_price_from(combo) == Decimal("33.00")  # 30 + (1,00 + 2,00)


def test_combo_edit_saves_menu_set_fields(user):
    from apps.catalog.models import Category

    cat = Category.objects.create(name={"de": "Hochzeit"}, slug="men2-hochzeit")
    combo = Combo.objects.create(name="Menü", price=Decimal("42.00"))
    views.combo_edit(
        _post(
            user,
            {
                "name": "Menü",
                "price": "42,00",
                "is_active": "on",
                "category": str(cat.pk),
                "price_per_person": "on",
                "min_persons": "20",
                "event_types": "Hochzeit, Firmenfeier,\nHochzeit",  # дубль схлопывается
                "free_pool": "on",
            },
        ),
        pk=combo.pk,
    )
    combo.refresh_from_db()
    assert combo.category_id == cat.pk
    assert combo.price_per_person is True and combo.min_persons == 20
    assert combo.event_types == ["Hochzeit", "Firmenfeier"]
    assert combo.free_pool is True


def test_combo_group_included_saved(user):
    combo = Combo.objects.create(name="Menü", price=Decimal("10.00"))
    views.combo_group_add(
        _post(user, {"label": "Im Menü", "included": "on", "min": "1", "max": "1"}), pk=combo.pk
    )
    group = combo.groups.get()
    assert group.included is True
    views.combo_group_update(
        _post(user, {"label": "Im Menü", "min": "1", "max": "1"}), pk=combo.pk, gid=group.pk
    )
    group.refresh_from_db()
    assert group.included is False  # чекбокс снят → False (не залип)


def test_product_form_course_choice():
    """MEN-2: Gang сохраняется; чужой код отвергается ChoiceField'ом."""
    from apps.catalog.forms import ProductForm

    product = ProductFactory()
    base = {
        "name_de": "Suppe",
        "base_price": "4.00",
        "currency": "EUR",
        "course": "vorspeise",
    }
    form = ProductForm(base, instance=product)
    assert form.is_valid(), form.errors
    assert form.save().course == "vorspeise"
    bad = ProductForm({**base, "course": "nachtisch"}, instance=product)
    assert not bad.is_valid() and "course" in bad.errors
