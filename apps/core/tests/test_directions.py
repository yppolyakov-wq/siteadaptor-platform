"""AIS-M M-0: реестр направлений — единственный источник ответа «как продаёт бизнес»."""

import pathlib
import re

import pytest

from apps.core import directions, modules, nav_registry
from apps.tenants.models import Tenant
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db

ROOT = pathlib.Path(__file__).resolve().parents[3]


def _tenant(btype, *, off=(), on=(), profile=None):
    disabled = [k for k in modules.default_disabled_for(btype) if k not in on] + list(off)
    config = {"profile": profile} if profile else {}
    return TenantFactory.build(business_type=btype, disabled_modules=disabled, site_config=config)


def test_nav_waren_gate_delegates_to_directions():
    for btype in ("bakery", "hotel", "friseur", "werkstatt"):
        t = _tenant(btype)
        assert nav_registry.direction_active(t, "waren") == directions.is_active(t, "waren")


def test_waren_rules_are_preserved():
    assert directions.is_active(_tenant("bakery"), "waren")  # тип
    assert directions.is_active(_tenant("werkstatt"), "waren")  # Teile (S6b)
    assert not directions.is_active(_tenant("hotel"), "waren")  # нет товаров и заказов
    assert directions.is_active(_tenant("hotel", on=("orders",)), "waren")  # модуль заказов


def test_table_booking_is_not_appointments():
    assert directions.is_active(_tenant("restaurant"), "tisch")
    assert not directions.is_active(_tenant("restaurant"), "termine")
    assert directions.is_active(_tenant("friseur"), "termine")
    assert not directions.is_active(_tenant("friseur"), "tisch")


def test_lite_job_module_is_not_an_inquiry_direction():
    # В лёгком пакете jobs держит заявки по акции — это не направление «Anfragen».
    assert not directions.is_active(_tenant("bakery", on=("jobs",), profile="aktionen"), "anfragen")
    assert directions.is_active(_tenant("handwerker"), "anfragen")


def test_direction_modules_exist_in_module_registry():
    known = {m.key for m in modules.REGISTRY}
    for d in directions.REGISTRY:
        assert set(d.modules) <= known, d.key


def test_defaults_cover_every_business_type():
    types = {t for t, _ in Tenant.BUSINESS_TYPES}
    assert set(directions.DEFAULT_FOR) == types
    keys = {d.key for d in directions.REGISTRY}
    for btype, defaults in directions.DEFAULT_FOR.items():
        assert set(defaults) <= keys, btype
        if btype != "other":  # other выбирает направление в мастере
            assert defaults, btype


def test_direction_constants_live_only_in_directions_module():
    """Замок: наборы типов направлений определяются только в apps/core/directions.py."""
    pattern = re.compile(r"^\s*(WAREN_TYPES|TABLE_TYPES|MENU_TYPES)\s*[:=]", re.MULTILINE)
    offenders = [
        str(path.relative_to(ROOT))
        for path in (ROOT / "apps").rglob("*.py")
        if "tests" not in path.parts
        and path.name != "directions.py"
        and pattern.search(path.read_text(encoding="utf-8"))
    ]
    assert offenders == []
