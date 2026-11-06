"""AIS-M M-1d: пресеты модулей согласованы с направлениями по умолчанию."""

import pytest

from apps.core import directions, modules
from apps.tenants.models import Tenant

TYPES = [t for t, _label in Tenant.BUSINESS_TYPES]


def test_tour_operator_preset_has_anfragen_without_booking():
    disabled = set(modules.default_disabled_for("tour_operator"))
    assert "booking" in disabled
    assert "jobs" not in disabled
    assert "promotions" not in disabled


def test_hotel_preset_promotions_on_customer_account_off():
    disabled = set(modules.default_disabled_for("hotel"))
    assert "promotions" not in disabled
    assert "customer_account" in disabled


# werkstatt: «Waren» = запчасти без онлайн-заказов (orders остаётся выключен).
_EXCEPTIONS = {("werkstatt", "waren")}


@pytest.mark.parametrize("btype", TYPES)
def test_default_directions_modules_are_in_preset(btype):
    disabled = set(modules.default_disabled_for(btype))
    for key in directions.defaults_for(btype):
        if (btype, key) in _EXCEPTIONS:
            continue
        for mod in directions.get(key).modules:
            assert mod not in disabled, (btype, key, mod)


# --- Гейт «Aktionen» в меню (M-1d) -------------------------------------------
from types import SimpleNamespace  # noqa: E402

from apps.core import nav_registry  # noqa: E402

_PROMO_LIST = nav_registry.entry_for("marketing", "promotions:promotion-list")
_QUICK = next(e for e in nav_registry.ENTRIES if e.url_name == "promotions:promotion-quick")


def _tenant(btype, has):
    t = SimpleNamespace(business_type=btype, disabled_modules=[], site_config={})
    t._m1d_has_promos = has
    t.is_module_active = lambda key: True
    return t


@pytest.mark.parametrize("btype", sorted(nav_registry.LATE_PROMO_TYPES))
def test_late_types_hide_aktionen_until_first_promo(btype):
    assert nav_registry.late_promo_hidden(_PROMO_LIST, _tenant(btype, False))
    assert not nav_registry.late_promo_hidden(_PROMO_LIST, _tenant(btype, True))


def test_other_types_never_query(monkeypatch):
    monkeypatch.setattr(nav_registry, "has_promotions", lambda t: pytest.fail("no query"))
    assert not nav_registry.late_promo_hidden(_PROMO_LIST, SimpleNamespace(business_type="bakery"))


def test_palette_only_new_aktion_stays():
    assert not nav_registry.late_promo_hidden(_QUICK, _tenant("hotel", False))


@pytest.mark.django_db
def test_has_promotions_fails_open_outside_tenant_schema():
    t = SimpleNamespace(schema_name="nope", site_config={})
    assert nav_registry.has_promotions(t) is True


@pytest.mark.django_db
def test_menu_gate_only_in_menu(monkeypatch):
    from apps.tenants.tests.factories import TenantFactory

    t = TenantFactory(business_type="hotel", disabled_modules=[])
    t._m1d_has_promos = False
    assert nav_registry.entry_visible(_PROMO_LIST, t)  # ссылки/счётчики — как прежде
    assert not nav_registry.entry_visible(_PROMO_LIST, t, menu=True)
