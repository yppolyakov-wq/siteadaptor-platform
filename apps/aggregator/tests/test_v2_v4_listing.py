"""В2/В4-1 (план v2-v4-conditions-condition-plan-2026-10-16): условие цены и состояние
товара в каталоге города — снимок, карточка, страница предложения, JSON-LD, фид, поиск.
Замки написаны ДО кода."""

from datetime import timedelta
from decimal import Decimal
from unittest import mock

import pytest
from django.test import RequestFactory, override_settings
from django.utils import timezone, translation

from apps.aggregator import open_feed, structured, tasks, views
from apps.aggregator.models import AggregatorListing, AggregatorPortal
from apps.catalog.models import PriceLog, Product
from apps.promotions.models import Promotion
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db

PHOTO = [{"url": "https://cdn.example/x.webp", "is_primary": True}]
PIZZA = {"kind": "nth", "n": 2, "pay": None, "note": {}}
_HOST = "solingen.example.test"


def _tenant():
    return TenantFactory(
        schema_name="public",
        slug="v2l",
        name="Pizzeria",
        city="Solingen",
        business_type="restaurant",
    )


def _product(price="9.00", **kw):
    p = Product.objects.create(
        name={"de": "Pizza Verdure"}, base_price=Decimal(price), images=PHOTO, **kw
    )
    PriceLog.objects.filter(product=p).update(created_at=timezone.now() - timedelta(days=40))
    return p


def _promo(product=None, cond=PIZZA, **kw):
    kw.setdefault("status", "active")
    kw.setdefault("starts_at", timezone.now())
    kw.setdefault("title", {"de": "Pizza-Abend: zweite Pizza −50 %"})
    kw.setdefault("discount_percent", 50)
    meta = {"price_condition": cond} if cond else {}
    return Promotion.objects.create(product=product, metadata=meta, **kw)


# --- снимок -----------------------------------------------------------------------


def test_conditional_promo_listing_has_unit_price_and_condition():
    _tenant()
    promo = _promo(_product())
    assert tasks.sync_listing("public", str(promo.id)) == "upserted"
    row = AggregatorListing.objects.get(promo_uuid=promo.id)
    assert row.new_price == Decimal("9.00")  # цена ШТУКИ, не 4,50
    assert row.old_price is None and row.discount_percent is None
    assert row.price_condition == {"kind": "nth", "n": 2, "pay": None, "note": {}, "percent": 50}
    with translation.override("de"):
        assert row.price_condition_label == "2. Stück −50 %"


def test_mystery_listing_has_no_condition():
    _tenant()
    promo = _promo(_product(), discount_style="mystery")
    tasks.sync_listing("public", str(promo.id))
    row = AggregatorListing.objects.get(promo_uuid=promo.id)
    assert row.price_condition == {} and row.new_price is None


def test_condition_change_updates_existing_row():
    _tenant()
    promo = _promo(_product())
    tasks.sync_listing("public", str(promo.id))
    promo.metadata = {"price_condition": {"kind": "x_for_y", "n": 2, "pay": 1}}
    promo.save()
    assert tasks.sync_listing("public", str(promo.id)) == "upserted"
    row = AggregatorListing.objects.get(promo_uuid=promo.id)
    assert row.price_condition["kind"] == "x_for_y"


def test_product_condition_and_note_overlay():
    _tenant()
    product = _product(
        condition="retoure",
        condition_note="Karton geöffnet",
        condition_note_i18n={"en": "Box opened", "ru": " "},
    )
    tasks.sync_product_listing("public", product.pk)
    row = AggregatorListing.objects.get(listing_kind="product", source_ref=str(product.pk))
    assert row.item_condition == "retoure"
    assert row.item_condition_note == {"de": "Karton geöffnet", "en": "Box opened"}
    with translation.override("en"):
        assert row.item_condition_note_text == "Box opened"
    with translation.override("de"):
        assert row.item_condition_label == "Retoure – geprüft"


def test_promo_on_used_product_carries_item_condition():
    _tenant()
    promo = _promo(_product(condition="wie_neu"), cond=None)
    tasks.sync_listing("public", str(promo.id))
    assert AggregatorListing.objects.get(promo_uuid=promo.id).item_condition == "wie_neu"


def test_every_builder_writes_new_fields():
    """`_upsert_listing` сравнивает только переданные ключи: вид, забывший поле,
    никогда его не обновит. Каждый вызов в построителях обязан нести все три."""
    import inspect

    src = inspect.getsource(tasks)
    calls = src.count("_upsert_listing(\n")
    assert calls >= 8
    assert src.count("**_neutral_v2v4(),") == calls


def test_unchanged_product_is_not_rewritten():
    _tenant()
    product = _product(condition="neu")
    tasks.sync_product_listing("public", product.pk)
    row = AggregatorListing.objects.get(listing_kind="product", source_ref=str(product.pk))
    before = row.updated_at
    with mock.patch.object(AggregatorListing.objects, "update_or_create") as upd:
        tasks.sync_product_listing("public", product.pk)
    assert not upd.called
    row.refresh_from_db()
    assert row.updated_at == before


# --- вывод ------------------------------------------------------------------------


def _portal():
    return AggregatorPortal.objects.create(
        host=_HOST, kind="city", city="Solingen", title={"de": "Solingen"}, is_active=True
    )


def _listing(**kw):
    defaults = {
        "tenant_schema": "t1",
        "tenant_slug": "pizza",
        "business_name": "Pizzeria",
        "business_type": "restaurant",
        "city": "Solingen",
        "listing_kind": "promotion",
        "source_ref": "x",
        "title": {"de": "Pizza-Abend"},
        "new_price": Decimal("9.00"),
        "currency": "EUR",
        "detail_url": "https://pizza.siteadaptor.de/p/1/",
        "is_active": True,
        "price_condition": {"kind": "nth", "n": 2, "pay": None, "note": {}, "percent": 50},
    }
    defaults.update(kw)
    return AggregatorListing.objects.create(**defaults)


def _req(portal, path="/"):
    req = RequestFactory().get(path, HTTP_HOST=_HOST)
    req.portal = portal
    return req


@override_settings(ROOT_URLCONF="config.urls_portal")
def test_card_and_offer_show_condition_not_percent():
    from apps.aggregator import portal_views

    portal = _portal()
    lst = _listing(discount_percent=50)
    with translation.override("de"):
        html = portal_views.portal_home(_req(portal, "/?kind=angebote")).content.decode()
        assert "data-price-condition" in html and "2. Stück −50 %" in html
        assert ">−50 %</span>" not in html
        body = views.offer_page(_req(portal), lst.pk).content.decode()
    assert "Preis gilt nur: 2. Stück −50 %" in body


@override_settings(ROOT_URLCONF="config.urls_portal")
def test_condition_badge_distinct_from_new_in_store():
    portal = _portal()
    lst = _listing(
        listing_kind="product",
        source_ref="p",
        price_condition={},
        is_new=True,
        item_condition="retoure",
        item_condition_note={"de": "Karton geöffnet"},
    )
    with translation.override("de"):
        body = views.offer_page(_req(portal), lst.pk).content.decode()
    assert 'data-condition="retoure"' in body and "Retoure – geprüft" in body
    assert "Karton geöffnet" in body and "Neu im Sortiment" in body


@pytest.mark.parametrize(
    "code, iri",
    [
        ("neu", "https://schema.org/NewCondition"),
        ("neu_ohne_ovp", "https://schema.org/NewCondition"),
        ("ausstellung", "https://schema.org/UsedCondition"),
        ("retoure", "https://schema.org/RefurbishedCondition"),
        ("wie_neu", "https://schema.org/UsedCondition"),
        ("gut", "https://schema.org/UsedCondition"),
    ],
)
def test_jsonld_item_condition_mapping(code, iri):
    lst = _listing(listing_kind="product", source_ref=code, price_condition={}, item_condition=code)
    offer = structured.offer_data(lst, url=lst.detail_url)
    assert offer["itemCondition"] == iri


def test_jsonld_no_item_condition_when_unknown():
    lst = _listing(listing_kind="product", source_ref="n", price_condition={})
    assert "itemCondition" not in structured.offer_data(lst, url=lst.detail_url)


@override_settings(ROOT_URLCONF="config.urls_portal")
def test_feed_carries_condition_and_item_condition():
    portal = _portal()
    lst = _listing(item_condition="gut", item_condition_note={"de": "Kratzer"})
    lst.refresh_from_db()
    with translation.override("de"):
        ext = open_feed.feed_item(lst, request=_req(portal, "/feed.json"), preview=False)[
            "_siteadaptor"
        ]
    assert ext["price"] == "9.00"
    assert ext["price_condition"]["kind"] == "nth" and ext["price_condition"]["percent"] == 50
    assert ext["price_condition"]["label"] == "2. Stück −50 %"
    assert ext["item_condition"] == "gut"
    assert ext["item_condition_iri"] == "https://schema.org/UsedCondition"
    assert ext["item_condition_note"] == "Kratzer"


def test_search_finds_item_by_condition_label():
    from apps.aggregator import search

    lst = _listing(
        listing_kind="product", source_ref="s", price_condition={}, item_condition="retoure"
    )
    lst.save()  # индекс собирается в save()
    ids = list(
        search.match(AggregatorListing.objects.all(), "Retoure", lang="de").values_list(
            "pk", flat=True
        )
    )
    assert lst.pk in ids


# --- ревью ветки -----------------------------------------------------------------


@pytest.mark.parametrize("kw", [{"discount_style": "mystery"}, {"is_surprise": True}])
def test_hidden_promo_does_not_leak_item_condition(kw):
    _tenant()
    product = _product(condition="retoure", condition_note="Dyson V11, Akku defekt")
    promo = _promo(product, cond=None, **kw)
    tasks.sync_listing("public", str(promo.id))
    row = AggregatorListing.objects.get(promo_uuid=promo.id)
    assert row.item_condition == "" and row.item_condition_note == {}


def test_note_keeps_only_known_locales():
    _tenant()
    product = _product(
        condition="gut", condition_note="Kratzer", condition_note_i18n={"en": "Scratch", "xx": "j"}
    )
    tasks.sync_product_listing("public", product.pk)
    row = AggregatorListing.objects.get(listing_kind="product", source_ref=str(product.pk))
    assert set(row.item_condition_note) == {"de", "en"}


@override_settings(ROOT_URLCONF="config.urls_portal")
def test_atom_summary_strips_control_chars_from_condition_note():
    from types import SimpleNamespace

    portal = _portal()
    _listing(price_condition={"kind": "other", "n": None, "pay": None, "note": {"de": "a\x01b"}})
    page = SimpleNamespace(items=list(AggregatorListing.objects.all()), next_cursor=None)
    with translation.override("de"):
        xml = open_feed.atom_feed(
            _req(portal, "/feed.xml"),
            title="T",
            home_url="https://x.test/",
            page=page,
            preview=False,
        )
    assert "\x01" not in xml and "ab" in xml


def test_stock_save_does_not_query_promotions(django_assert_num_queries):
    _tenant()
    product = _product()
    with mock.patch("apps.aggregator.stock_sync.touch_promotion") as touch:
        tasks.resync_on_product_save(Product, product, update_fields=["stock"])
        assert not touch.called
    _promo(product, cond=None)
    with mock.patch("apps.aggregator.stock_sync.touch_promotion") as touch:
        tasks.resync_on_product_save(Product, product, update_fields=["condition"])
        assert touch.called
