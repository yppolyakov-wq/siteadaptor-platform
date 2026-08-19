"""X4 (план x4-navigation-plan-2026-08-19): подпункты по смыслу, сироты, глоссарий.

Инварианты волны:
- подпункты якорей архетипны — салон видит «Leistungen», отель «Zimmer & Preise»,
  и НИКТО не видит склад в подпунктах сайдбара (он в ящике таб-бара);
- у каждого бывшего сироты есть вход (X7.3 держит класс, здесь — точечно);
- гастро-экраны (KDS/Tisch-QR) не показываются негастро ни в одной поверхности;
- гейт business_types fail-open без тенанта (простые тест-рендеры хрома).
"""

from types import SimpleNamespace
from uuid import uuid4

import pytest
from django.template import Context, Template

from apps.core import modules, nav_registry
from apps.core.modules import default_disabled_for
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _urlconf(settings):
    settings.ROOT_URLCONF = "config.urls_tenant"


def _tenant(business_type, enable=()):
    """Тенант с РЕАЛЬНЫМ пресетом модулей архетипа (урок: disabled_modules=[]
    — нереалистичный набор). `enable` включает точечно (у гастро-типов модуль
    заказов по умолчанию выключён, а гейт KDS проверяем именно на нём)."""
    off = [m for m in default_disabled_for(business_type) if m not in enable]
    return TenantFactory(
        slug=f"x4-{business_type[:8]}-{uuid4().hex[:4]}",
        name="X4",
        business_type=business_type,
        disabled_modules=off,
    )


def _children(tenant, anchor_url):
    return [
        c["url_name"]
        for it in modules.sidebar_nav(tenant)
        if it["url_name"] == anchor_url
        for c in it["children"]
    ]


# --- подпункты «Sortiment» архетипны -----------------------------------------


def test_sortiment_children_are_archetype_entities():
    """Главный дефект исследования §3: у салона в подпунктах «его товаров» висели
    Lager/Einkauf/Kombi/Import, а экран услуг был сиротой. Теперь наоборот."""
    friseur = _children(_tenant("friseur"), "sellable-manage")
    assert "booking:services" in friseur
    assert not {"stock", "purchasing", "imports:start", "catalog:combo-list"} & set(friseur)

    hotel = _children(_tenant("hotel"), "sellable-manage")
    assert "stays:units" in hotel  # номера — «товар» отеля

    shop = _children(_tenant("shop"), "sellable-manage")
    assert "catalog:product-list" in shop and "booking:services" not in shop


def test_stock_group_stays_reachable_in_catalog_drawer():
    """Склад ушёл из сайдбара, но НЕ из кабинета: ящик «Erweitert» таб-бара."""
    tabs = {t[0] for t in nav_registry.legacy_hub_tabs()["catalog"]}
    assert {"stock", "purchasing", "catalog:combo-list", "imports:start"} <= tabs


# --- подпункты «Verkäufe» — рабочие входы дня ---------------------------------


def test_verkaeufe_children_working_entries_before_reports():
    salon = _children(_tenant("friseur"), "verkaeufe")
    assert "booking:resources" in salon and "booking:availability" in salon
    # рабочие входы — ДО отчётной группы
    assert salon.index("booking:resources") < salon.index("ablaeufe")

    hotel = _children(_tenant("hotel"), "verkaeufe")
    assert "stays:checkins" in hotel
    assert "stays:checkins" not in salon  # чужой модуль


# --- гейт гастро --------------------------------------------------------------


def test_kds_children_gated_by_business_type():
    # модуль orders включён у обоих — скрывает именно ТИП бизнеса
    cafe = _tenant("cafe", enable=("orders",))
    salon = _tenant("friseur", enable=("orders",))
    assert cafe.is_module_active("orders") and salon.is_module_active("orders")
    assert "orders:kitchen" in _children(cafe, "verkaeufe")
    assert "orders:kitchen" not in _children(salon, "verkaeufe")


def _palette(tenant):
    html = Template("{% load cabinet %}{% nav_palette %}").render(
        Context({"request": SimpleNamespace(tenant=tenant, user=None)})
    )
    return html


def test_palette_gates_gastro_screens():
    assert "/tisch-qr/" in _palette(_tenant("restaurant", enable=("orders",)))
    assert "/tisch-qr/" not in _palette(_tenant("clothing", enable=("orders",)))


def test_business_gate_fail_open_without_tenant():
    assert nav_registry.allowed_for_business("orders:kitchen", None) is True
    assert nav_registry.allowed_for_business("catalog:product-list", None) is True


# --- сироты получили вход -----------------------------------------------------


def test_former_orphans_are_reachable_from_palette():
    """x4-navigation-plan §4: у каждого бывшего сироты — вход (подпункт или
    Ctrl+K). Проверяем самые дорогие: приём оплат, Channel Manager, Firmen,
    Reservierungen, Rechnungen, Karten & Abos, Gastgeber."""
    listed = {e["url_name"] for e in nav_registry.palette_entries()}
    for name in (
        "booking:services",
        "booking:resources",
        "booking:availability",
        "booking:passes",
        "stays:units",
        "stays:checkins",
        "stays:channels",
        "orders:kitchen",
        "orders:table-qr",
        "events:teacher-list",
        "crm:company-list",
        "promotions:reservation-list",
        "finance:invoices",
        "jobs:anfrage-form-settings",
        "billing-payments",
    ):
        assert name in listed, name


def test_palette_only_entries_stay_out_of_tab_bars():
    """Сироты попали в палитру, но таб-бары остались компактными."""
    tabs = {u for hub in nav_registry.legacy_hub_tabs().values() for (u, *_r) in hub}
    for name in ("stays:channels", "crm:company-list", "billing-payments", "finance:invoices"):
        assert name not in tabs, name


# --- глоссарий ----------------------------------------------------------------


def test_glossary_sortiment_replaces_angebote_in_cabinet_nav():
    """«Angebot» = оферта клиенту (Sofort-Angebot/смета). Раздел того, что бизнес
    продаёт, во ВСЕХ точках навигации зовётся «Sortiment»."""
    anchor = next(a for a in nav_registry.ANCHORS if a.url_name == "sellable-manage")
    assert str(anchor.label) == "Sortiment"
    for hub in ("catalog", "sellables"):
        label = next(t[1] for t in nav_registry.legacy_hub_tabs()[hub] if t[0] == "sellable-manage")
        assert str(label) == "Sortiment"
    # «Tickets» осталось за вкладкой СДЕЛОК страницы Verkäufe, сущность — событие
    label = next(t[1] for t in nav_registry.legacy_hub_tabs()["sellables"] if t[0] == "events:list")
    assert str(label) == "Veranstaltungen"


def test_entity_pages_highlight_sortiment_anchor():
    """Причина «где я» из разведки §1.3: все страницы booking/stays эмитили
    nav="booking"/"stays" → подсветка уходила на «Verkäufe». Сущностные экраны
    получили свои ключи."""
    for nav_key in ("services", "units", "passes", "events", "tours"):
        assert nav_registry.anchor_for(nav_key) == "sellables", nav_key
    # операционные экраны остались за «Verkäufe»
    for nav_key in ("booking", "stays", "orders", "jobs"):
        assert nav_registry.anchor_for(nav_key) == "board", nav_key
