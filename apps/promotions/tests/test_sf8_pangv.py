"""SF-8 (план sf8-pangv-city-perishable-plan-2026-10-16): исключение § 11 Abs. 4 PAngV
(schnell verderblich) + референс цены в каталоге города. Замки написаны ДО кода."""

from datetime import timedelta
from decimal import Decimal

import pytest
from django.test import RequestFactory, override_settings
from django.utils import timezone

from apps.aggregator import open_feed, tasks, views
from apps.aggregator.models import AggregatorListing, AggregatorPortal
from apps.catalog.models import PriceLog, Product
from apps.promotions.forms import PromotionForm
from apps.promotions.models import Promotion
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db

PHOTO = [{"url": "https://cdn.example/x.webp", "is_primary": True}]


def _product(price, **kw):
    p = Product.objects.create(name={"de": "Brot"}, base_price=Decimal(price), images=PHOTO, **kw)
    PriceLog.objects.filter(product=p).update(created_at=timezone.now() - timedelta(days=40))
    return p


def _raise(product, price, *, days_ago):
    product.base_price = Decimal(price)
    product.save()
    PriceLog.objects.filter(product=product, price=Decimal(price)).update(
        created_at=timezone.now() - timedelta(days=days_ago)
    )


def _promo(product=None, **kw):
    kw.setdefault("status", "active")
    kw.setdefault("starts_at", timezone.now())
    kw.setdefault("title", {"de": "Aktion"})
    return Promotion.objects.create(product=product, **kw)


def _mondpreis_promo(perishable):
    p = _product("8.00")
    _raise(p, "10.00", days_ago=5)
    meta = {"perishable": True} if perishable else {}
    return _promo(p, discount_percent=20, metadata=meta)


# --- SF-8b: флаг и выключатель ------------------------------------------------------


def test_perishable_flag_lifts_the_30_day_cap():
    promo = _mondpreis_promo(perishable=True)
    assert promo.is_perishable is True
    assert promo.old_price == Decimal("10.00")
    assert promo.has_discount is True
    assert promo.discount_percent_display == 20
    assert promo.lowest_30d_display is None  # строки «Niedrigster Preis…» нет
    assert promo.price_reference == ""


def test_without_flag_cap_applies_as_in_sf7():
    promo = _mondpreis_promo(perishable=False)
    assert promo.is_perishable is False
    assert promo.old_price == Decimal("8.00")
    assert promo.has_discount is False


@override_settings(PANGV_PERISHABLE_EXEMPTION=False)
def test_kill_switch_ignores_the_flag():
    promo = _mondpreis_promo(perishable=True)
    assert promo.is_perishable is False
    assert promo.old_price == Decimal("8.00")
    assert promo.has_discount is False


def test_perishable_note_on_promotion_detail():
    from django.contrib.messages.middleware import MessageMiddleware
    from django.contrib.sessions.middleware import SessionMiddleware

    from apps.promotions import public_views

    promo = _mondpreis_promo(perishable=True)
    req = RequestFactory().get(f"/p/{promo.pk}/")
    SessionMiddleware(lambda r: None).process_request(req)
    MessageMiddleware(lambda r: None).process_request(req)
    req.tenant = TenantFactory.build(business_type="bakery")
    body = public_views.promotion_detail(req, pk=promo.pk).content.decode()
    assert "Abs. 4 PAngV" in body
    assert "letzten 30 Tage" not in body


# --- SF-8b: формы ----------------------------------------------------------------


def _form_data(**extra):
    return {
        "title_de": "Brot vom Tag",
        "promo_type": "discount",
        "max_per_customer": 1,
        "reservation_ttl_hours": 24,
        **extra,
    }


def test_cabinet_form_sets_and_clears_flag_with_sentinel():
    tenant = TenantFactory(schema_name="public", slug="sf8f")
    form = PromotionForm(_form_data(perishable_present="1", perishable="on"), tenant=tenant)
    assert form.is_valid(), form.errors
    promo = form.save()
    assert promo.metadata.get("perishable") is True

    form = PromotionForm(_form_data(perishable_present="1"), instance=promo, tenant=tenant)
    assert form.is_valid(), form.errors
    promo = form.save()
    assert "perishable" not in promo.metadata


def test_cabinet_form_without_sentinel_keeps_flag():
    """W0: чужой POST (форма без чекбокса) не стирает выбор владельца."""
    tenant = TenantFactory(schema_name="public", slug="sf8g")
    promo = _promo(metadata={"perishable": True, "response": "reserve"})
    form = PromotionForm(_form_data(), instance=promo, tenant=tenant)
    assert form.is_valid(), form.errors
    promo = form.save()
    assert promo.metadata.get("perishable") is True
    assert promo.metadata.get("response") == "reserve"


@override_settings(PANGV_PERISHABLE_EXEMPTION=False)
def test_cabinet_form_hides_checkbox_when_switched_off():
    tenant = TenantFactory(schema_name="public", slug="sf8h")
    assert "perishable" not in PromotionForm(tenant=tenant).fields


def test_quick_form_builds_flag_and_repeat_carries_it():
    from apps.promotions import quick

    tenant = TenantFactory(schema_name="public", slug="sf8q", business_type="bakery")
    form = quick.QuickPromotionForm(
        {
            "title": "Feierabendbrot",
            "new_price": "2.00",
            "old_price": "4.00",
            "term": "today",
            "customer_response": "reserve",
            "perishable": "on",
        },
        tenant=tenant,
    )
    assert form.is_valid(), form.errors
    promo = form.build()
    assert promo.metadata.get("perishable") is True
    promo.save()
    assert quick.initial_from(promo).get("perishable") is True


# --- SF-8a: снимок каталога города --------------------------------------------------


def _city_tenant():
    return TenantFactory(schema_name="public", slug="sf8c", name="Brot & Co", city="Solingen")


def test_product_snapshot_marks_uvp_reference():
    _city_tenant()
    product = _product("89.00", list_price=Decimal("120.00"), slug="jacke")
    assert tasks.sync_product_listing("public", product.pk) == "upserted"
    row = AggregatorListing.objects.get(listing_kind="product", source_ref=str(product.pk))
    assert row.old_price == Decimal("120.00") and row.price_reference == "uvp"


def test_promo_snapshot_marks_lowest30_only_with_history():
    _city_tenant()
    p = _product("10.00")
    promo = _promo(p, discount_percent=20)
    assert tasks.sync_listing("public", str(promo.id)) == "upserted"
    row = AggregatorListing.objects.get(promo_uuid=promo.id)
    assert row.old_price == Decimal("10.00") and row.price_reference == "lowest30"

    free = _promo(None, compare_at_price=Decimal("5.00"), price_override=Decimal("4.00"))
    tasks.sync_listing("public", str(free.id))
    assert AggregatorListing.objects.get(promo_uuid=free.id).price_reference == ""


def test_perishable_promo_snapshot_has_no_reference_but_keeps_discount():
    _city_tenant()
    promo = _mondpreis_promo(perishable=True)
    tasks.sync_listing("public", str(promo.id))
    row = AggregatorListing.objects.get(promo_uuid=promo.id)
    assert row.old_price == Decimal("10.00")
    assert row.discount_percent == 20
    assert row.price_reference == ""


# --- SF-8a: рендер портала и фид ----------------------------------------------------

_HOST = "solingen.example.test"


def _portal():
    return AggregatorPortal.objects.create(
        host=_HOST, kind="city", city="Solingen", title={"de": "Solingen"}, is_active=True
    )


def _listing(**kw):
    defaults = {
        "tenant_schema": "t1",
        "tenant_slug": "brot",
        "business_name": "Brot & Co",
        "business_type": "bakery",
        "city": "Solingen",
        "listing_kind": "promotion",
        "source_ref": "x",
        "title": {"de": "Brotkorb"},
        "new_price": "4.50",
        "old_price": "6.00",
        "currency": "EUR",
        "detail_url": "https://brot.siteadaptor.de/p/1/",
        "is_active": True,
    }
    defaults.update(kw)
    return AggregatorListing.objects.create(**defaults)


def _offer_price_block(portal, lst):
    """Блок цены САМОГО предложения (ниже — карточки «похожих», там чужие референсы)."""
    req = RequestFactory().get("/", HTTP_HOST=_HOST)
    req.portal = portal
    html = views.offer_page(req, lst.pk).content.decode()
    i = html.index("data-offer-price")
    return html[i : html.index('<div class="mt-auto', i)]


@override_settings(ROOT_URLCONF="config.urls_portal")
def test_offer_page_prints_uvp_label_or_30_day_line_by_reference():
    portal = _portal()
    uvp = _listing(listing_kind="product", source_ref="p", price_reference="uvp")
    block = _offer_price_block(portal, uvp)
    assert "UVP" in block and "letzten 30 Tage" not in block

    low = _listing(source_ref="l", price_reference="lowest30")
    block = _offer_price_block(portal, low)
    assert "letzten 30 Tage" in block and "6,00" in block and "UVP" not in block

    plain = _listing(source_ref="n", price_reference="")
    block = _offer_price_block(portal, plain)
    assert "UVP" not in block and "letzten 30 Tage" not in block


@override_settings(ROOT_URLCONF="config.urls_portal")
def test_cards_print_uvp_label_and_30_day_line():
    from apps.aggregator import portal_views

    portal = _portal()
    _listing(listing_kind="product", source_ref="p", title={"de": "Jacke"}, price_reference="uvp")
    _listing(source_ref="l", title={"de": "Brotkorb"}, price_reference="lowest30")
    req = RequestFactory().get("/?kind=product", HTTP_HOST=_HOST)
    req.portal = portal
    html = portal_views.portal_home(req).content.decode()
    assert "UVP" in html and "letzten 30 Tage" not in html
    req = RequestFactory().get("/?kind=angebote", HTTP_HOST=_HOST)
    req.portal = portal
    html = portal_views.portal_home(req).content.decode()
    assert "letzten 30 Tage" in html


@override_settings(ROOT_URLCONF="config.urls_portal")
def test_feed_item_carries_price_reference():
    portal = _portal()
    lst = _listing(price_reference="lowest30")
    lst.refresh_from_db()  # Decimal, как в проде (фабрика выше пишет строки)
    req = RequestFactory().get("/feed.json", HTTP_HOST=_HOST)
    req.portal = portal
    item = open_feed.feed_item(lst, request=req, preview=False)
    assert item["_siteadaptor"]["price_reference"] == "lowest30"


def test_demo_surprise_bags_carry_perishable_flag():
    """Демо-носитель SF-8b: Überraschungstüte (остатки дня) сеется с исключением Abs. 4."""
    from apps.tenants import demo_kits

    tenant = TenantFactory(schema_name="public", slug="sf8d", name="Markt", business_type="shop")
    assert demo_kits.apply_kit(tenant, "aktionsmarkt") is True
    bags = Promotion.objects.filter(is_surprise=True)
    assert bags.exists()
    assert all(p.is_perishable for p in bags)
    # exclude по отсутствующему JSON-ключу = NULL-семантика → сверяем в Python.
    others = Promotion.objects.filter(is_surprise=False)
    assert others.exists() and not any(p.is_perishable for p in others)
