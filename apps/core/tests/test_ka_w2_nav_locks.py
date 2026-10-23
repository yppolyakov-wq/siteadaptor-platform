"""KA-12 Волна 2 (E8.12): замки структуры кабинета.

План — docs/ka-12-w2-structure-plan-2026-10-23.md, батч 1. Сначала с базовой линией долга:
батчи 2–3 её обнуляют. Новая запись без гейта, раздутое подменю или рабочий экран только в
палитре краснят CI сразу.
"""

from uuid import uuid4

import pytest

from apps.core import modules, nav_registry
from apps.tenants.models import Tenant
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db

BUSINESS_TYPES = [code for code, _label in Tenant.BUSINESS_TYPES]

# Записи без гейта — долг погашен батчем 2 (пункт «Kunden» снят из подменю продаж).
GATE_DEBT: set[str] = set()

MAX_SUBMENU = 7
# Подменю больше семи пунктов — долг батча 3 (подзаголовки групп).
SUBMENU_DEBT = {
    "marketing-home": 13,
    "einstellungen-home": 14,
    "sellable-manage": 9,
    "verkaeufe": 8,
}

# Экраны только в Ctrl+K — с причиной; рабочий экран сюда не попадает без решения.
PALETTE_ONLY_OK = {
    "billing-payments": "секция «Zahlarten»",
    "booking:passes": "абонементы — вход с услуги",
    "crm:company-list": "фирмы — вход из «Kunden»",
    "events:teacher-list": "ведущие — вход с события",
    "finance:bank": "банк — вход из «Offene Posten» (батч 3 → меню Finanzen)",
    "finance:ergebnis": "батч 3 → меню Finanzen",
    "finance:expenses": "батч 3 → меню Finanzen",
    "finance:invoices": "батч 3 → меню Finanzen",
    "finance:offene": "батч 3 → меню Finanzen",
    "gbp-merchant": "вход с экрана каналов",
    "gbp-sync": "вход с экрана каналов",
    "google-reviews-settings": "вход из «Integrationen»",
    "imports:website": "вход с экрана импорта",
    "orders:table-qr": "вход из KDS",
    "promotions:promotion-quick": "ассистент — кнопка «＋»",
    "verkaeufe?tab=reservation": "резервы — вкладка продаж (с первой записи)",
    "verkaeufe-zusatz": "вход из тулбара Verkäufe",
}


def _key(e):
    return e.url_name + (e.query or "")


def test_every_entry_has_gate():
    missing = {_key(e) for e in nav_registry.ENTRIES if not nav_registry.entry_gate(e)}
    assert missing - GATE_DEBT == set(), "запись без гейта и без причины в UNIVERSAL"
    assert GATE_DEBT - missing == set(), "долг погашен — убрать из GATE_DEBT"


def test_no_work_screen_palette_only():
    only = {_key(e) for e in nav_registry.ENTRIES if e.palette_only}
    assert only - set(PALETTE_ONLY_OK) == set()


@pytest.mark.parametrize("business_type", BUSINESS_TYPES)
def test_submenu_size(business_type):
    tenant = TenantFactory(
        slug=f"w2-{business_type[:8]}-{uuid4().hex[:4]}",
        business_type=business_type,
        disabled_modules=modules.default_disabled_for(business_type),
    )
    for item in modules.sidebar_nav(tenant):
        limit = max(MAX_SUBMENU, SUBMENU_DEBT.get(item["url_name"], 0))
        assert len(item["children"]) <= limit, (
            f"{business_type}: подменю «{item['url_name']}» — {len(item['children'])} пунктов"
        )


def test_entry_visible_honours_new_gates():
    from types import SimpleNamespace

    hidden = nav_registry.NavEntry("x", "X", "x", "h", modules_any=("nonexistent",))
    tenant = SimpleNamespace(business_type="friseur", disabled_modules=[], site_config={})
    assert nav_registry.entry_visible(hidden, tenant) is False
    waren = nav_registry.NavEntry("x", "X", "x", "h", direction="waren")
    assert nav_registry.entry_visible(waren, SimpleNamespace(business_type="bakery")) is True
    gastro = nav_registry.NavEntry("x", "X", "x", "h", direction="gastro")
    assert nav_registry.entry_visible(gastro, SimpleNamespace(business_type="hotel")) is False
