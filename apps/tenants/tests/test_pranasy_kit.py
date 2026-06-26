"""Pranasy — полноценная двуязычная демо-витрина (PR-D…H).

Restaurant (меню + «Bald geöffnet», покупка вкл.) и Shop (подкатегории) — две
отдельные сущности; ретриты (события), кетеринг (jobs), лояльность, «О нас».
Контент двуязычный (DE+EN): товары/категории/события + оверлей site_config.
"""

import pytest
from django.contrib.messages.middleware import MessageMiddleware
from django.contrib.sessions.middleware import SessionMiddleware
from django.test import RequestFactory
from django.utils import translation

from apps.catalog.models import Category, Product
from apps.events.models import Event
from apps.promotions import public_views
from apps.tenants import demo_kits, menu, siteconfig
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db


def _req(tenant, path="/"):
    request = RequestFactory().get(path)
    SessionMiddleware(lambda r: None).process_request(request)
    MessageMiddleware(lambda r: None).process_request(request)
    request.tenant = tenant
    return request


def _tenant():
    return TenantFactory(
        schema_name="public", slug="pranasy", name="Pranasy", business_type="restaurant"
    )


def test_pranasy_applies_full_bilingual_site():
    tenant = _tenant()
    assert demo_kits.apply_kit(tenant, "pranasy") is True

    # Restaurant — отдельная верхнеуровневая категория, 8 блюд, покупка включена.
    restaurant = Category.objects.get(slug="demo-restaurant")
    assert restaurant.parent_id is None
    dishes = Product.objects.filter(category=restaurant)
    assert dishes.count() == 8
    assert all(p.is_active for p in dishes)  # «купить сразу» — товары активны

    # Shop — отдельная верхнеуровневая категория с тремя подкатегориями.
    shop = Category.objects.get(slug="demo-shop")
    assert shop.parent_id is None
    subs = Category.objects.filter(parent=shop)
    assert subs.count() == 3
    by_slug = {c.slug: c for c in subs}
    assert Product.objects.filter(category=by_slug["demo-wuerstchen"]).count() == 3
    assert Product.objects.filter(category=by_slug["demo-aufschnitt"]).count() == 3
    assert Product.objects.filter(category=by_slug["demo-suesses"]).count() == 6


def test_pranasy_products_are_bilingual():
    tenant = _tenant()
    demo_kits.apply_kit(tenant, "pranasy")
    # каждая категория и каждый товар несут DE и EN.
    cats = Category.objects.all()
    assert cats.exists()
    assert all(c.name.get("de") and c.name.get("en") for c in cats)
    prods = Product.objects.all()
    assert all(p.name.get("de") and p.name.get("en") for p in prods)


def test_pranasy_has_six_bilingual_retreats():
    tenant = _tenant()
    demo_kits.apply_kit(tenant, "pranasy")
    events = Event.objects.all()
    assert events.count() == 6
    # двуязычные заголовки: EN-локаль даёт английский title_text.
    sample = events.first()
    with translation.override("en"):
        assert sample.title_text == sample.title_i18n.get("en", sample.title)
    assert all(e.title_i18n.get("en") for e in events)


def test_pranasy_site_config_localizes():
    tenant = _tenant()
    demo_kits.apply_kit(tenant, "pranasy")
    cfg = tenant.site_config
    assert cfg["i18n"]["en"]  # оверлей переводов есть
    de = siteconfig.localize(cfg, "de")
    en = siteconfig.localize(cfg, "en")
    assert de["hero_title"] and en["hero_title"]
    assert "i18n" not in en  # служебный ключ не утекает
    # heroes-слайдер: «Bald geöffnet» для ресторана → EN отличается.
    assert de["heroes"] and en["heroes"]


def test_pranasy_menu_has_separate_restaurant_and_shop():
    tenant = _tenant()
    demo_kits.apply_kit(tenant, "pranasy")
    with translation.override("de"):
        top = menu.resolve_menu(tenant, "top")
    labels = [i["label"] for i in top]
    # Restaurant и Shop — отдельные пункты меню.
    assert "Restaurant" in labels
    assert "Shop" in labels
    # EN-локаль: «Über uns» → «About us».
    with translation.override("en"):
        top_en = menu.resolve_menu(tenant, "top")
    labels_en = [i["label"] for i in top_en]
    assert "About us" in labels_en


def test_pranasy_enables_modules_and_loyalty():
    tenant = _tenant()
    demo_kits.apply_kit(tenant, "pranasy")
    for mod in ("orders", "events", "jobs", "loyalty"):
        assert tenant.is_module_active(mod)


def test_pranasy_storefront_renders_de_and_en(settings):
    """Render-smoke: главная витрина pranasy отдаётся 200 на DE и EN без падений."""
    settings.ROOT_URLCONF = "config.urls_tenant"
    tenant = _tenant()
    demo_kits.apply_kit(tenant, "pranasy")
    with translation.override("de"):
        resp_de = public_views.storefront_home(_req(tenant))
    assert resp_de.status_code == 200
    body_de = resp_de.content.decode()
    assert "Bald geöffnet" in body_de  # hero-слайд ресторана
    with translation.override("en"):
        resp_en = public_views.storefront_home(_req(tenant))
    assert resp_en.status_code == 200
    # EN-локаль: оверлей перевёл hero-заголовок (отличается от DE).
    assert resp_en.content.decode() != body_de
