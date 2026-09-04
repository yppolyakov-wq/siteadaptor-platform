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


# --- catering (GK-1, 2026-08-11): кейтеринг как основной бизнес --------------
def test_catering_type_registered_and_wired():
    from apps.core.hero_tiles import HERO_TILE_SETS
    from apps.core.seo import _SCHEMA_TYPES
    from apps.tenants.onboarding import BUSINESS_TYPE_META, DEMO_KIT_HOST

    assert "catering" in dict(Tenant.BUSINESS_TYPES)
    assert BUSINESS_TYPE_META["catering"][0]  # иконка карточки мастера
    assert DEMO_KIT_HOST["catering"] == "catering"
    disabled = set(modules.default_disabled_for("catering"))
    assert "jobs" not in disabled  # primary
    assert "promotions" not in disabled and "crm" not in disabled
    for universal in ("reviews", "gift", "blog", "inbox", "customer_account"):
        assert universal not in disabled
    assert "orders" in disabled and "booking" in disabled  # Speisekarte browse-only
    assert KITS["catering"].business_type == "catering"
    assert KITS["catering"].anfrage_form["fields"]  # AF-1 в демо из коробки
    assert KITS["catering"].primary_module == "jobs"
    assert _SCHEMA_TYPES["catering"] == "FoodEstablishment"
    assert "catering" in HERO_TILE_SETS


def test_catering_promo_presets_exist():
    from apps.promotions.presets import PRESETS

    assert any(p["key"] == "fruehbucher" for p in PRESETS["catering"])


# --- online_shop (решение владельца 2026-07-10): «просто онлайн-магазин» -----
def test_online_shop_type_registered_and_wired():
    """Тип в choices; карточка с иконкой/blurb; демо-маппинг на СВОЙ кит; primary=orders
    активен из коробки; универсальные модули не выключены (урок default_disabled_for).

    O-6 (2026-09-03): маппинг переехал с generic-лавки `shop` на выделенный
    аутлет `outlet` — `online_shop` был последним типом без своего демо."""
    from apps.tenants import onboarding

    assert "online_shop" in dict(Tenant.BUSINESS_TYPES)
    icon, blurb = onboarding.BUSINESS_TYPE_META["online_shop"]
    assert icon and "Online-Shop" in blurb
    assert onboarding.DEMO_KIT_HOST["online_shop"] == "outlet"
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
