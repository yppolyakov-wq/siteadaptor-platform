"""M20: демо-контент витрины (load/clear), идемпотентность и точное удаление."""

import pytest

from apps.booking.models import Service
from apps.catalog.models import Product
from apps.events.models import Event
from apps.promotions.models import Promotion
from apps.stays.models import StayUnit
from apps.tenants import demo
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db


def _tenant(business_type="bakery"):
    # schema_name=public → catalog/promotions таблицы доступны (как в test-настройке)
    return TenantFactory(schema_name="public", slug="x", name="X", business_type=business_type)


def test_load_demo_creates_catalog_and_promotions():
    tenant = _tenant("bakery")
    assert demo.load_demo(tenant) is True
    assert demo.has_demo(tenant) is True
    assert Product.objects.filter(metadata__demo=True).count() == 10  # bakery — 10 товаров
    promos = Promotion.objects.filter(metadata__demo=True)
    assert promos.count() == 3  # до 3 демо-акций
    assert all(p.status == "active" for p in promos)
    assert len(tenant.site_config["demo"]["promotions"]) == 3


def test_load_demo_is_idempotent():
    tenant = _tenant()
    assert demo.load_demo(tenant) is True
    assert demo.load_demo(tenant) is False  # повторно не дублирует
    assert Product.objects.filter(metadata__demo=True).count() == 10


def test_hotel_gets_stay_units_not_other_types():
    tenant = _tenant("hotel")
    demo.load_demo(tenant)
    assert StayUnit.objects.count() == 4  # номера для отеля
    assert Event.objects.count() == 1  # одно событие
    # бизнес без booking-услуг по типу → услуги не создаются
    assert Service.objects.count() == 0


def test_tour_operator_gets_services_and_events():
    tenant = _tenant("tour_operator")
    demo.load_demo(tenant)
    assert Service.objects.count() == 4
    assert Event.objects.count() == 2
    assert StayUnit.objects.count() == 0  # не отель → без номеров


def test_bakery_has_no_services_or_stays():
    tenant = _tenant("bakery")
    demo.load_demo(tenant)
    assert Service.objects.count() == 0
    assert StayUnit.objects.count() == 0
    assert Event.objects.count() == 0


def test_clear_demo_removes_all_kinds_keeps_foreign():
    tenant = _tenant("hotel")
    keep = Product.objects.create(name={"de": "Echt"}, base_price=1)  # не-демо
    demo.load_demo(tenant)
    assert demo.clear_demo(tenant) is True
    assert demo.has_demo(tenant) is False
    assert not Product.objects.filter(metadata__demo=True).exists()
    assert not Promotion.objects.filter(metadata__demo=True).exists()
    assert StayUnit.objects.count() == 0
    assert Event.objects.count() == 0
    assert Product.objects.filter(pk=keep.pk).exists()  # чужое цело


def test_clear_demo_noop_when_absent():
    tenant = _tenant()
    assert demo.clear_demo(tenant) is False


def test_load_demo_self_heals_orphan_category():
    """Регрессия: прерванная прошлая загрузка оставила категорию demo-beliebt
    (UNIQUE uniq_category_slug_alive) → повторный «Demo laden» 500-ил.
    Теперь load_demo подчищает осиротевшие демо-объекты и проходит."""
    from apps.catalog.models import Category

    tenant = _tenant("bakery")
    # осиротевшие остатки (refs в site_config НЕ сохранены → has_demo False)
    Category.objects.create(name={"de": "Beliebt"}, slug="demo-beliebt", is_active=True)
    orphan = Product.objects.create(name={"de": "Alt"}, base_price=1, metadata={"demo": True})

    assert demo.has_demo(tenant) is False
    assert demo.load_demo(tenant) is True  # больше не падает на слаге
    assert Category.objects.filter(slug="demo-beliebt").count() == 1  # без дублей
    assert not Product.objects.filter(pk=orphan.pk).exists()  # сирота убрана
    assert Product.objects.filter(metadata__demo=True).count() == 10  # свежий набор


def test_fallback_products_for_unknown_type():
    tenant = _tenant("other")
    demo.load_demo(tenant)
    assert Product.objects.filter(metadata__demo=True).count() == 3  # fallback-набор


# --- W3: демо-контент новых архетипов (friseur/werkstatt/events) --------------
def test_friseur_gets_services():
    tenant = _tenant("friseur")
    demo.load_demo(tenant)
    assert Service.objects.count() == 4  # услуги салона (booking primary)
    assert StayUnit.objects.count() == 0


def test_werkstatt_gets_services():
    tenant = _tenant("werkstatt")
    demo.load_demo(tenant)
    assert Service.objects.count() == 4  # услуги мастерской (Termin)


def test_events_type_gets_events():
    tenant = _tenant("events")
    demo.load_demo(tenant)
    assert Event.objects.count() == 3  # билеты (events primary)
    assert Service.objects.count() == 0
