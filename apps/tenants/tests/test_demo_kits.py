"""M20 demo: киты — полноценная showcase-витрина (apply_kit)."""

import pytest

from apps.catalog.models import (
    Category,
    ModifierGroup,
    ModifierOption,
    Product,
    ProductVariant,
)
from apps.promotions.models import Promotion
from apps.tenants import demo_kits
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db


def _tenant():
    return TenantFactory(schema_name="public", slug="x", name="X", business_type="restaurant")


def test_unknown_kit_returns_false():
    assert demo_kits.apply_kit(_tenant(), "nope") is False


@pytest.mark.parametrize("key", [k for k in demo_kits.KITS if k != "restaurant"])
def test_apply_additional_kit_builds_site(key):
    """Каждый кит (Bäckerei/Café/Friseur/Hotel) собирается без ошибок."""
    kit = demo_kits.KITS[key]
    tenant = TenantFactory(
        schema_name="public", slug=f"{key}-x", name=key, business_type=kit.business_type
    )
    assert demo_kits.apply_kit(tenant, key) is True
    tenant.refresh_from_db()
    assert tenant.site_config.get("sections")  # раскладка собрана
    assert tenant.primary_color == kit.accent
    # движок кита материализован под активным модулем
    if kit.services:
        from apps.booking.models import Service

        assert Service.objects.count() == len(kit.services)
    if kit.stay_units:
        from apps.stays.models import StayUnit

        assert StayUnit.objects.count() == len(kit.stay_units)


def test_demo_image_is_themed_and_deterministic():
    url = demo_kits.demo_image("pizza margherita", lock=5)
    assert url == "https://loremflickr.com/800/600/pizza,margherita?lock=5"


def test_apply_restaurant_kit_builds_full_site():
    tenant = _tenant()
    assert demo_kits.apply_kit(tenant, "restaurant") is True

    # каталог: несколько категорий + товары с фото
    assert Category.objects.filter(slug__startswith="demo-").count() == 4
    products = Product.objects.filter(metadata__demo=True)
    assert products.count() >= 28
    assert all(p.images and p.images[0]["url"].startswith("https://") for p in products)
    # варианты (Pizza klein/groß) и аллергены проставлены
    assert ProductVariant.objects.count() >= 6
    assert products.filter(allergens__contains=["gluten"]).exists()
    # акции (4 — сетка кратна 2)
    assert Promotion.objects.filter(metadata__demo=True).count() == 4

    # site_config: фото-hero, акцент, галерея, контент-секции
    cfg = tenant.site_config
    assert cfg["hero_image"].startswith("https://loremflickr.com/")
    assert tenant.primary_color == "#b45309"
    assert len(cfg["gallery"]) == 6
    assert cfg["faq"] and cfg["testimonials"] and cfg["cta"]["button_url"] == "/sortiment/"
    assert cfg["gallery_video"].startswith("https://")  # T1: видео в галерее
    enabled = {s["key"] for s in cfg["sections"] if s["enabled"]}
    assert {"hero", "products", "promotions", "gallery", "faq", "cta"} <= enabled
    assert cfg["nav"]["style"] == "centered"


def test_restaurant_kit_seeds_pizza_modifiers():
    """Конструктор блюда (A4): пицца получает группы модификаторов с опциями."""
    tenant = _tenant()
    demo_kits.apply_kit(tenant, "restaurant")

    pizza = Product.objects.get(name__de="Pizza Margherita")
    groups = list(pizza.modifier_groups.filter(is_active=True).order_by("sort_order"))
    names = [g.name for g in groups]
    assert "Teig" in names and "Beläge hinzufügen" in names
    # обязательная одиночная группа Teig (radio), множественная Beläge
    teig = next(g for g in groups if g.name == "Teig")
    assert teig.is_required and not teig.is_multi
    belaege = next(g for g in groups if g.name == "Beläge hinzufügen")
    assert belaege.is_multi and not belaege.is_required
    # надбавка цены у опции (Dick +1,00)
    assert ModifierOption.objects.filter(group=teig, label="Dick", price_delta=1).exists()
    # стейк тоже имеет конструктор (Beilage обязательна)
    steak = Product.objects.get(name__de="Rumpsteak")
    assert steak.modifier_groups.filter(name="Beilage", min_select__gte=1).exists()
    assert ModifierGroup.objects.filter(is_active=True).count() >= 5


def test_restaurant_kit_sets_dish_badges():
    """T1: бейджи блюд (Tagesgericht/Neu) проставлены в демо."""
    tenant = _tenant()
    demo_kits.apply_kit(tenant, "restaurant")
    assert Product.objects.get(name__de="Lasagne").badge == "tagesgericht"
    pizza_veg = Product.objects.get(name__de="Pizza Vegetariana")
    assert pizza_veg.badge == "neu" and pizza_veg.badge_label == "Neu"


def test_restaurant_kit_enables_orders_and_delivery():
    """Демо-ресторан показывает онлайн-заказ: модуль orders включён + доставка с зонами."""
    tenant = _tenant()
    demo_kits.apply_kit(tenant, "restaurant")

    assert "orders" not in (tenant.disabled_modules or [])
    assert tenant.is_module_active("orders")
    assert tenant.delivery_enabled is True
    assert tenant.delivery_fee_cents == 290
    assert tenant.delivery_free_cents == 2500
    assert tenant.delivery_min_cents == 1500
    # PLZ-зоны A2a
    plz = {z["plz"] for z in tenant.delivery_zones}
    assert {"40721", "40724"} <= plz


def test_restaurant_kit_seeds_events_catering_loyalty():
    """Демо-ресторан показывает события, кейтеринг (jobs) и лояльность."""
    from apps.events.models import Event
    from apps.promotions.models import LoyaltyProgram

    tenant = _tenant()
    demo_kits.apply_kit(tenant, "restaurant")

    # события опубликованы и в будущем
    events = Event.objects.filter(status=Event.STATUS_PUBLISHED)
    assert events.count() == 4
    assert events.filter(title="Live-Musik: Italienische Nacht").exists()
    # бесплатное (price 0) и платные
    assert events.filter(price_cents=0).exists() and events.filter(price_cents=3500).exists()

    # кейтеринг = модуль jobs активен (форма /anfrage/)
    assert tenant.is_module_active("jobs")

    # программа лояльности (штампы)
    program = LoyaltyProgram.objects.get(is_active=True)
    assert program.stamps_required == 10 and program.reward_label == "1 Gratis-Pizza"


def test_restaurant_kit_seeds_bookable_table():
    """Бронь столика работает: ресурс + недельное расписание → /termin/ даёт слоты."""
    from apps.booking import availability
    from apps.booking.models import AvailabilityRule, Resource

    tenant = _tenant()
    demo_kits.apply_kit(tenant, "restaurant")
    assert Resource.objects.filter(is_active=True).count() == 1
    assert AvailabilityRule.objects.count() == 7  # все дни недели
    resource = Resource.objects.first()
    # на ближайший день недельного окна есть свободные слоты
    from datetime import timedelta

    from django.utils import timezone

    found = any(
        availability.free_slots_with_spots(resource, (timezone.localdate() + timedelta(days=d)))
        for d in range(1, 8)
    )
    assert found
