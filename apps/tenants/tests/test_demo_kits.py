"""M20 demo: киты — полноценная showcase-витрина (apply_kit)."""

import pytest

from apps.catalog.models import Category, Product, ProductVariant
from apps.promotions.models import Promotion
from apps.tenants import demo_kits
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db


def _tenant():
    return TenantFactory(schema_name="public", slug="x", name="X", business_type="restaurant")


def test_unknown_kit_returns_false():
    assert demo_kits.apply_kit(_tenant(), "nope") is False


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
    # акции
    assert Promotion.objects.filter(metadata__demo=True).count() == 3

    # site_config: фото-hero, акцент, галерея, контент-секции
    cfg = tenant.site_config
    assert cfg["hero_image"].startswith("https://loremflickr.com/")
    assert tenant.primary_color == "#b45309"
    assert len(cfg["gallery"]) == 6
    assert cfg["faq"] and cfg["testimonials"] and cfg["cta"]["button_url"] == "/sortiment/"
    enabled = {s["key"] for s in cfg["sections"] if s["enabled"]}
    assert {"hero", "products", "promotions", "gallery", "faq", "cta"} <= enabled
    assert cfg["nav"]["style"] == "centered"
