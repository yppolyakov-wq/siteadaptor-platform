"""A4 Gastro: модификаторы/Extras блюда — модель и CRUD-вьюхи (кабинет)."""

from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from django.contrib.messages.middleware import MessageMiddleware
from django.contrib.sessions.middleware import SessionMiddleware
from django.test import RequestFactory

from apps.catalog import views
from apps.catalog.models import ModifierGroup, ModifierOption
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


# --- модель -----------------------------------------------------------------------


def test_has_modifiers_needs_active_group_with_active_option():
    product = ProductFactory()
    assert product.has_modifiers is False

    group = ModifierGroup.objects.create(product=product, name="Extras")
    assert product.has_modifiers is False  # группа без опций не считается

    opt = ModifierOption.objects.create(group=group, label="Käse", price_delta=Decimal("1.00"))
    assert product.has_modifiers is True

    opt.is_active = False
    opt.save(update_fields=["is_active"])
    assert product.has_modifiers is False  # все опции неактивны


def test_group_required_and_multi_flags():
    product = ProductFactory()
    single = ModifierGroup.objects.create(product=product, name="Größe", min_select=1, max_select=1)
    multi = ModifierGroup.objects.create(product=product, name="Extras", min_select=0, max_select=0)
    assert single.is_required is True
    assert single.is_multi is False
    assert multi.is_required is False
    assert multi.is_multi is True


def test_modifier_groups_active_excludes_inactive():
    product = ProductFactory()
    ModifierGroup.objects.create(product=product, name="A")
    ModifierGroup.objects.create(product=product, name="B", is_active=False)
    names = [g.name for g in product.modifier_groups_active]
    assert names == ["A"]


# --- вьюхи ------------------------------------------------------------------------


def test_group_add(user):
    product = ProductFactory()
    resp = views.modifier_group_add(
        _post(user, {"name": "Größe", "min": "1", "max": "1"}), pk=product.pk
    )
    assert resp.status_code == 302
    group = ModifierGroup.objects.get(product=product)
    assert group.name == "Größe"
    assert group.min_select == 1 and group.max_select == 1


def test_group_add_requires_name(user):
    product = ProductFactory()
    views.modifier_group_add(_post(user, {"name": "  "}), pk=product.pk)
    assert ModifierGroup.objects.filter(product=product).count() == 0


def test_group_update_toggles_active(user):
    product = ProductFactory()
    group = ModifierGroup.objects.create(product=product, name="Extras")
    views.modifier_group_update(
        _post(user, {"name": "Beilage", "min": "0", "max": "2"}), pk=product.pk, gid=group.pk
    )
    group.refresh_from_db()
    assert group.name == "Beilage"
    assert group.max_select == 2
    assert group.is_active is False  # чекбокс не передан → снят


def test_option_add_and_delta(user):
    product = ProductFactory()
    group = ModifierGroup.objects.create(product=product, name="Extras")
    views.modifier_option_add(
        _post(user, {"label": "Pommes", "delta": "2,50"}), pk=product.pk, gid=group.pk
    )
    opt = ModifierOption.objects.get(group=group)
    assert opt.label == "Pommes"
    assert opt.price_delta == Decimal("2.50")


def test_option_add_defaults_delta_to_zero(user):
    product = ProductFactory()
    group = ModifierGroup.objects.create(product=product, name="Extras")
    views.modifier_option_add(_post(user, {"label": "Ketchup"}), pk=product.pk, gid=group.pk)
    assert ModifierOption.objects.get(group=group).price_delta == Decimal("0")


def test_option_delete_scoped_to_product_and_group(user):
    product = ProductFactory()
    group = ModifierGroup.objects.create(product=product, name="Extras")
    opt = ModifierOption.objects.create(group=group, label="X")
    views.modifier_option_delete(_post(user, {}), pk=product.pk, gid=group.pk, oid=opt.pk)
    assert not ModifierOption.objects.filter(pk=opt.pk).exists()
