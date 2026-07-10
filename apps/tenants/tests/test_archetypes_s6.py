"""S6 (упрощение кабинета): реальные архетипы friseur/handwerker/werkstatt/events.

Проверяет: новые типы в choices, демо-киты помечены новым business_type, primary-модуль
каждого архетипа включён из коробки (default_disabled_for его не выключает)."""

import pytest

from apps.core import modules
from apps.tenants.demo_kits import KITS
from apps.tenants.models import Tenant

NEW_TYPES = ("friseur", "handwerker", "werkstatt", "events")


def test_new_business_types_registered():
    codes = dict(Tenant.BUSINESS_TYPES)
    for bt in NEW_TYPES:
        assert bt in codes
    # прежние 10 не потеряны
    assert "bakery" in codes and "hotel" in codes and "other" in codes


@pytest.mark.parametrize(
    ("business_type", "primary_module"),
    [
        ("friseur", "booking"),  # Termin
        ("handwerker", "jobs"),  # Angebote/Kostenvoranschlag
        ("werkstatt", "jobs"),  # Werkstatt-Auftrag (+ booking тоже вкл)
        ("werkstatt", "booking"),  # Termin
        ("events", "events"),  # Tickets
    ],
)
def test_primary_module_enabled_by_default(business_type, primary_module):
    # primary архетипа НЕ в стартовом disabled → активен из коробки при онбординге.
    assert primary_module not in modules.default_disabled_for(business_type)


def test_universal_modules_enabled_for_new_types():
    # reviews/gift/blog/inbox/customer_account — из коробки у всех архетипов.
    for bt in NEW_TYPES:
        disabled = set(modules.default_disabled_for(bt))
        for universal in ("reviews", "gift", "blog", "inbox", "customer_account"):
            assert universal not in disabled, f"{universal} должен быть вкл для {bt}"


@pytest.mark.parametrize(
    ("kit_key", "expected_type"),
    [
        ("friseur", "friseur"),
        ("werkstatt", "werkstatt"),
        ("handwerker", "handwerker"),
        ("retreat", "events"),
    ],
)
def test_demo_kits_mapped_to_new_types(kit_key, expected_type):
    assert KITS[kit_key].business_type == expected_type


# --- online_shop (решение владельца 2026-07-10): «просто онлайн-магазин» -----
def test_online_shop_type_registered_and_wired():
    """Тип в choices; карточка с иконкой/blurb; демо-маппинг на shop; primary=orders
    активен из коробки; универсальные модули не выключены (урок default_disabled_for)."""
    from apps.tenants import onboarding

    assert "online_shop" in dict(Tenant.BUSINESS_TYPES)
    icon, blurb = onboarding.BUSINESS_TYPE_META["online_shop"]
    assert icon and "Online-Shop" in blurb
    assert onboarding.DEMO_KIT_HOST["online_shop"] == "shop"
    disabled = modules.default_disabled_for("online_shop")
    assert "orders" not in disabled  # primary: продажи
    for mod in ("reviews", "gift", "blog", "inbox", "customer_account", "promotions"):
        assert mod not in disabled, mod


def test_online_shop_demo_and_presets():
    """Light-seed товары и промо-пресеты есть для online_shop (мастер/AB3 не пустой)."""
    from apps.promotions.presets import PRESETS
    from apps.tenants.demo import _PRODUCTS

    assert len(_PRODUCTS["online_shop"]) >= 6
    assert any(p["key"] == "sale" for p in PRESETS["online_shop"])
