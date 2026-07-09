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
