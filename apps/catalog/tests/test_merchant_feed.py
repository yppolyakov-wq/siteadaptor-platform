"""M23b.1: фид товаров для Google Merchant Center (план docs/m23b-merchant-feed-plan-2026-10-18.md).

Решения владельца В-1…В-8 — §2 плана. Старый `/feed/google.xml` (общий с Meta) не ломаем."""

from __future__ import annotations

import uuid
from decimal import Decimal
from xml.dom import minidom

import pytest
from django.test import RequestFactory

from apps.catalog import google
from apps.catalog.feed import build_google_feed
from apps.catalog.models import ProductVariant
from apps.catalog.tests.factories import CategoryFactory, ProductFactory
from apps.promotions import public_views
from apps.publishing.models import Channel
from apps.tenants.tests.factories import TenantFactory

pytestmark = [pytest.mark.django_db, pytest.mark.urls("config.urls_tenant")]

IMG = [{"url": "/media/p.webp", "is_primary": True}]
TOKEN = "t0ken-" + "x" * 26


def _product(**kw):
    kw.setdefault("images", IMG)
    kw.setdefault("description", {"de": "Frisch."})
    return ProductFactory(**kw)


def _channel(enabled=True, token=TOKEN):
    """M23b.2: токен хранится шифротекстом в `merchant_feed_token` (не в `merchant_feed`)."""
    from apps.secrets import crypto

    return Channel.objects.update_or_create(
        type=Channel.GOOGLE_BUSINESS,
        defaults={
            "config": {
                "merchant_feed": {"enabled": enabled},
                "merchant_feed_token": crypto.encrypt(token),
            }
        },
    )[0]


def _get(token=TOKEN, ip=None, **headers):
    request = RequestFactory().get(f"/feed/merchant/{token}/products.xml", **headers)
    request.META["REMOTE_ADDR"] = ip or f"10.9.{uuid.uuid4().int % 250}.{uuid.uuid4().int % 250}"
    request.tenant = TenantFactory.build(schema_name="t_mf", name="Laden")
    return public_views.merchant_feed_xml(request, token)


# --- отбор (google.eligibility) -----------------------------------------------------------


def test_hidden_product_and_hidden_or_inactive_branch_excluded():
    parent = CategoryFactory(hide_in_google=True)
    child = CategoryFactory(parent=parent)
    inactive = CategoryFactory(is_active=False)
    ok = _product()
    own = _product(hide_in_google=True)
    via_parent = _product(category=child)
    via_inactive = _product(category=inactive)
    assert google.eligibility(ok)[0] is True
    assert google.eligibility(own) == (False, ["hidden"], [])
    assert "category_hidden" in google.eligibility(via_parent)[1]
    assert "category_hidden" in google.eligibility(via_inactive)[1]


def test_no_image_and_no_price_are_reasons():
    assert "no_image" in google.eligibility(_product(images=[]))[1]
    assert "no_price" in google.eligibility(_product(base_price="0"))[1]


def test_warnings_do_not_exclude():
    ok, reasons, warnings = google.eligibility(_product(description={}))
    assert ok and reasons == []
    assert "no_identifier" in warnings and "no_description" in warnings


def test_summary_counts_match_feed():
    _product()
    _product(images=[])
    _product(hide_in_google=True)
    s = google.summary()
    assert s["included"] == 1
    assert s["excluded"] == {"no_image": 1, "hidden": 1}


# --- вывод фида ---------------------------------------------------------------------------


def _merchant_xml(products):
    return build_google_feed(
        products=products,
        title="Laden",
        link="https://shop.test/",
        description="Produkte",
        product_url=lambda p: f"https://shop.test/p/{p.pk}/",
        absolutize=lambda u: u if u.startswith("http") else f"https://shop.test{u}",
        merchant=True,
    )


@pytest.mark.parametrize(
    "condition,expected",
    [("", "new"), ("neu", "new"), ("neu_ohne_ovp", "new"), ("retoure", "used"), ("gut", "used")],
)
def test_condition_mapping(condition, expected):
    xml = _merchant_xml([_product(condition=condition)])
    assert f"<g:condition>{expected}</g:condition>" in xml


def test_brand_field_wins_over_metadata():
    xml = _merchant_xml([_product(brand="Hausmarke", metadata={"brand": "Alt"})])
    assert "<g:brand>Hausmarke</g:brand>" in xml


def test_control_characters_never_break_xml():
    xml = _merchant_xml([_product(name={"de": "Brot\x0b\x01 frisch"})])
    minidom.parseString(xml.encode())
    assert "Brot frisch" in xml


def test_constant_queries_for_many_products(django_assert_max_num_queries):
    for _ in range(12):
        p = _product()
        ProductVariant.objects.create(product=p, label="S", price=Decimal("5"), stock_quantity=2)
        ProductVariant.objects.create(product=p, label="M", price=Decimal("6"), stock_quantity=0)
    with django_assert_max_num_queries(6):
        _merchant_xml(google.merchant_products())


def test_variants_listed_with_own_stock():
    p = _product()
    ProductVariant.objects.create(product=p, label="S", price=Decimal("5"), stock_quantity=0)
    ProductVariant.objects.create(product=p, label="Alt", price=Decimal("5"), is_active=False)
    xml = _merchant_xml(google.merchant_products())
    assert xml.count("<item>") == 1
    assert "<g:availability>out_of_stock</g:availability>" in xml
    assert f"<g:item_group_id>{p.pk}</g:item_group_id>" in xml


def test_zero_price_variant_not_emitted():
    p = _product()
    ProductVariant.objects.create(product=p, label="Gratis", price=Decimal("0"))
    ProductVariant.objects.create(product=p, label="M", price=Decimal("6"))
    xml = _merchant_xml(google.merchant_products())
    assert xml.count("<item>") == 1 and "Gratis" not in xml


def test_category_cycle_is_hidden():
    a = CategoryFactory()
    b = CategoryFactory(parent=a)
    type(a).all_objects.filter(pk=a.pk).update(parent=b)
    assert "category_hidden" in google.eligibility(_product(category=b))[1]


# --- публичная вьюха ----------------------------------------------------------------------


def test_feed_by_token_lists_only_eligible(isolated_ratelimit):
    _channel()
    ok = _product()
    _product(images=[])
    resp = _get()
    body = resp.content.decode()
    assert resp.status_code == 200 and resp["Content-Type"].startswith("application/xml")
    assert f"<g:id>{ok.pk}</g:id>" in body and body.count("<item>") == 1
    assert "noindex" in resp["X-Robots-Tag"]
    assert "no-store" in resp.get("Cache-Control", "") or getattr(resp, "no_store", False)


@pytest.mark.parametrize("token", ["wrong", TOKEN + "x", ""])
def test_unknown_token_404(isolated_ratelimit, token):
    _channel()
    assert _get(token=token).status_code == 404


def test_no_channel_or_no_token_404(isolated_ratelimit):
    assert _get().status_code == 404
    _channel(token="")
    assert _get(token="").status_code == 404


def test_short_stored_token_never_matches(isolated_ratelimit):
    _channel(token="kurz")
    assert _get(token="kurz").status_code == 404


def test_disabled_returns_valid_empty_feed(isolated_ratelimit):
    _channel(enabled=False)
    _product()
    resp = _get()
    assert resp.status_code == 200
    body = resp.content.decode()
    minidom.parseString(body.encode())
    assert "<item>" not in body


def test_etag_not_modified(isolated_ratelimit):
    _channel()
    _product()
    first = _get(ip="10.1.1.1")
    second = _get(ip="10.1.1.2", HTTP_IF_NONE_MATCH=first["ETag"])
    assert second.status_code == 304


def test_rate_limited(isolated_ratelimit, monkeypatch):
    monkeypatch.setattr(public_views, "MERCHANT_FEED_RATE_LIMIT", 2)
    _channel()
    codes = [_get(ip="10.2.2.2").status_code for _ in range(3)]
    assert codes == [200, 200, 429]


def test_old_feed_unchanged_by_default():
    """Старый адрес (Meta) — прежний вывод: марка из metadata, condition всегда new."""
    p = _product(brand="Neu", condition="retoure", metadata={"brand": "Alt"})
    xml = build_google_feed(
        products=[p],
        title="Laden",
        link="https://shop.test/",
        description="Produkte",
        product_url=lambda x: "https://shop.test/x/",
        absolutize=lambda u: u,
    )
    assert "<g:brand>Alt</g:brand>" in xml and "<g:condition>new</g:condition>" in xml


# --- формы --------------------------------------------------------------------------------


def test_forms_expose_hide_in_google():
    from apps.catalog.forms import CategoryForm, ProductForm

    assert "hide_in_google" in ProductForm().fields
    assert "hide_in_google" in CategoryForm().fields


# --- M23b.3: фид наличия в магазине ---------------------------------------------------------

LOCAL_CODE = "Laden-01"


def _local(token=TOKEN, ip=None, **headers):
    request = RequestFactory().get(f"/feed/merchant/{token}/local.xml", **headers)
    request.META["REMOTE_ADDR"] = ip or f"10.8.{uuid.uuid4().int % 250}.{uuid.uuid4().int % 250}"
    request.tenant = TenantFactory.build(schema_name="t_mf", name="Laden")
    return public_views.merchant_local_xml(request, token)


def _with_store(code=LOCAL_CODE, enabled=True):
    channel = _channel(enabled=enabled)
    Channel.update_config(channel.pk, lambda c: c["merchant_feed"].update({"store_code": code}))
    return channel


def _ids(xml):
    doc = minidom.parseString(xml.encode())
    return [n.firstChild.data for n in doc.getElementsByTagName("g:id")]


def test_merchant_ids_fit_google_limit_and_match_between_feeds(isolated_ratelimit):
    _with_store()
    p = _product()
    for label in ("S", "M"):
        ProductVariant.objects.create(product=p, label=label, price=Decimal("5"), stock_quantity=3)
    ProductVariant.objects.create(product=p, label="Gratis", price=Decimal("0"), stock_quantity=1)
    _product()  # без вариантов
    products_ids = _ids(_get().content.decode())
    local_ids = _ids(_local().content.decode())
    assert len(products_ids) == 3 and all(len(i) <= 50 for i in products_ids)
    assert sorted(products_ids) == sorted(local_ids)


def test_legacy_feed_keeps_old_variant_ids():
    from apps.catalog.models import Product

    p = _product()
    v = ProductVariant.objects.create(product=p, label="S", price=Decimal("5"))
    xml = build_google_feed(
        products=Product.objects.filter(pk=p.pk),
        title="t",
        link="https://x/",
        description="d",
        product_url=lambda _p: "https://x/p",
        absolutize=lambda u: "https://x" + u,
    )
    assert f"<g:id>{p.pk}:{v.pk}</g:id>" in xml


@pytest.mark.parametrize(
    ("stock", "availability", "quantity"),
    [(None, "in_stock", None), (4, "in_stock", 4), (0, "out_of_stock", 0), (-2, "out_of_stock", 0)],
)
def test_local_availability_mapping(stock, availability, quantity):
    from apps.catalog.feed import local_availability

    assert local_availability(stock) == (availability, quantity)


def test_local_feed_lists_stock_and_never_limited(isolated_ratelimit):
    _with_store()
    tracked = _product(stock_quantity=7)
    untracked = _product(stock_quantity=None)
    sold_out = _product(stock_quantity=0)
    _product(images=[], stock_quantity=5)  # не годится в фид товаров — и в локальный нет
    body = _local().content.decode()
    minidom.parseString(body.encode())
    assert body.count("<item>") == 3
    assert body.count(f"<g:store_code>{LOCAL_CODE}</g:store_code>") == 3
    assert f"<g:id>{tracked.pk}</g:id><g:store_code>{LOCAL_CODE}</g:store_code>" in body
    assert "<g:quantity>7</g:quantity>" in body and "<g:quantity>0</g:quantity>" in body
    assert body.count("<g:quantity>") == 2  # без ведения остатка количества нет
    assert "limited_availability" not in body
    assert str(untracked.pk) in body and str(sold_out.pk) in body


def test_local_feed_escapes_store_code():
    from apps.catalog.feed import build_local_inventory_feed

    xml = build_local_inventory_feed(
        products=[_product()], store_code="a<b&c", title="t", link="https://x/"
    )
    minidom.parseString(xml.encode())
    assert "<g:store_code>a&lt;b&amp;c</g:store_code>" in xml


@pytest.mark.parametrize(("code", "enabled"), [("", True), (LOCAL_CODE, False)])
def test_local_feed_empty_without_code_or_disabled(isolated_ratelimit, code, enabled):
    _with_store(code=code, enabled=enabled)
    _product()
    resp = _local()
    assert resp.status_code == 200
    doc = minidom.parseString(resp.content)
    assert b"<item>" not in resp.content
    assert doc.getElementsByTagName("channel")[0].getElementsByTagName("description")


def test_local_feed_guard_and_headers(isolated_ratelimit):
    _with_store()
    _product()
    assert _local(token="wrong").status_code == 404
    resp = _local(ip="10.3.3.3")
    assert resp.status_code == 200 and resp["Content-Type"].startswith("application/xml")
    assert "noindex" in resp["X-Robots-Tag"] and resp["Cache-Control"] == "private, no-cache"
    again = _local(ip="10.3.3.4", HTTP_IF_NONE_MATCH=resp["ETag"])
    assert again.status_code == 304


def test_both_feeds_share_one_rate_limit_bucket(isolated_ratelimit, monkeypatch):
    monkeypatch.setattr(public_views, "MERCHANT_FEED_RATE_LIMIT", 2)
    _with_store()
    codes = [
        _get(ip="10.4.4.4").status_code,
        _local(ip="10.4.4.4").status_code,
        _local(ip="10.4.4.4").status_code,
    ]
    assert codes == [200, 200, 429]


def test_local_feed_constant_queries(isolated_ratelimit, django_assert_max_num_queries):
    _with_store()
    for _ in range(6):
        p = _product()
        ProductVariant.objects.create(product=p, label="S", price=Decimal("5"), stock_quantity=1)
    with django_assert_max_num_queries(6):
        _local()


def test_overview_counts_local_positions():
    _product(stock_quantity=3)
    _product(stock_quantity=0)
    _product(stock_quantity=None)
    p = _product()
    ProductVariant.objects.create(product=p, label="S", price=Decimal("5"), stock_quantity=0)
    ProductVariant.objects.create(product=p, label="M", price=Decimal("5"), stock_quantity=None)
    assert google.overview()["local"] == {"tracked": 3, "untracked": 2, "out_of_stock": 2}


# --- M23b.4: цена акции в фиде Merchant -----------------------------------------------------


def _promo(product, **kw):
    from apps.promotions.tests.factories import PromotionFactory

    kw.setdefault("promo_type", "discount")
    kw.setdefault("available_quantity", None)
    return PromotionFactory(product=product, **kw)


def _items(xml):
    doc = minidom.parseString(xml.encode())
    out = {}
    for item in doc.getElementsByTagName("item"):
        fields = {
            n.tagName[2:]: n.firstChild.data if n.firstChild else ""
            for n in item.childNodes
            if n.nodeType == n.ELEMENT_NODE
        }
        out[fields["id"]] = fields
    return out


def test_active_promo_adds_sale_price_equal_to_checkout_price():
    from apps.promotions.price_layer import product_promo_map, promo_line_price

    p = _product(base_price=Decimal("10.00"))
    promo = _promo(p, price_override=Decimal("7.50"), ends_at=None)
    item = _items(_merchant_xml(google.merchant_products()))[str(p.pk)]
    assert item["price"] == "10.00 EUR"
    assert item["sale_price"] == "7.50 EUR"
    charged = promo_line_price(product_promo_map([p.pk])[p.pk], p)
    assert item["sale_price"] == f"{charged:.2f} EUR"
    assert "sale_price_effective_date" not in item  # без конца акции даты нет
    assert promo.pk


def test_variants_follow_cart_rule():
    p = _product(base_price=Decimal("10.00"))
    free = ProductVariant.objects.create(product=p, label="S")
    own = ProductVariant.objects.create(product=p, label="XL", price=Decimal("12.00"))
    _promo(p, price_override=Decimal("8.00"))
    items = _items(_merchant_xml(google.merchant_products()))
    assert items[free.pk.hex]["sale_price"] == "8.00 EUR"
    assert "sale_price" not in items[own.pk.hex]


@pytest.mark.parametrize(
    "kw",
    [
        {"status": "scheduled"},
        {"metadata": {"price_condition": {"kind": "nth", "n": 2}}, "discount_percent": 50},
    ],
)
def test_scheduled_or_conditional_promo_has_no_sale_price(kw):
    p = _product(base_price=Decimal("10.00"))
    kw.setdefault("price_override", Decimal("5.00"))
    _promo(p, **kw)
    item = _items(_merchant_xml(google.merchant_products()))[str(p.pk)]
    assert "sale_price" not in item and item["price"] == "10.00 EUR"


def test_mystery_promo_keeps_regular_price_without_leaking():
    """SF-9: сюрприз не часть цены товара — в фиде обычная цена, секрета нет."""
    p = _product(base_price=Decimal("10.00"))
    _promo(p, price_override=Decimal("6.37"), discount_style="mystery")
    xml = _merchant_xml(google.merchant_products())
    item = _items(xml)[str(p.pk)]
    assert item["price"] == "10.00 EUR" and "sale_price" not in item
    assert "6.37" not in xml
    assert "promo_mystery" not in google.overview()["excluded"]


def test_cheaper_mystery_does_not_block_regular_promo():
    p = _product(base_price=Decimal("10.00"))
    _promo(p, price_override=Decimal("9.00"))
    _promo(p, price_override=Decimal("6.00"), discount_style="mystery")
    xml = _merchant_xml(google.merchant_products())
    assert _items(xml)[str(p.pk)]["sale_price"] == "9.00 EUR" and "6.00" not in xml


def test_exhausted_limit_returns_regular_price_remaining_limit_sells():
    """SF-10: исчерпанная акция снята с витрины — товар в фиде по обычной цене."""
    gone = _product(base_price=Decimal("10.00"))
    _promo(gone, price_override=Decimal("7.00"), available_quantity=0)
    left = _product(base_price=Decimal("10.00"))
    _promo(left, price_override=Decimal("7.00"), available_quantity=3)
    items = _items(_merchant_xml(google.merchant_products()))
    assert items[str(gone.pk)]["price"] == "10.00 EUR" and "sale_price" not in items[str(gone.pk)]
    assert items[str(left.pk)]["sale_price"] == "7.00 EUR"
    assert "promo_sold_out" not in google.overview()["excluded"]


def test_promo_above_base_price_charges_promo_price_without_sale():
    p = _product(base_price=Decimal("9.00"))
    _promo(p, compare_at_price=Decimal("12.00"), price_override=Decimal("10.00"))
    item = _items(_merchant_xml(google.merchant_products()))[str(p.pk)]
    assert item["price"] == "10.00 EUR" and "sale_price" not in item


def test_effective_date_format_and_stable():
    import re
    from datetime import timedelta

    from django.utils import timezone

    p = _product(base_price=Decimal("10.00"))
    start = timezone.now() - timedelta(days=1)
    _promo(p, price_override=Decimal("8.00"), starts_at=start, ends_at=start + timedelta(days=5))
    first = _items(_merchant_xml(google.merchant_products()))[str(p.pk)]
    second = _items(_merchant_xml(google.merchant_products()))[str(p.pk)]
    value = first["sale_price_effective_date"]
    stamp = r"\d{4}-\d\d-\d\dT\d\d:\d\d[+-]\d{4}"
    assert re.fullmatch(f"{stamp}/{stamp}", value)
    assert value == second["sale_price_effective_date"]


def test_effective_date_falls_back_to_created_at():
    from datetime import timedelta

    from django.utils import timezone

    from apps.catalog.feed import _effective_date

    p = _product()
    promo = _promo(p, price_override=Decimal("1.00"), ends_at=timezone.now() + timedelta(days=2))
    start = _effective_date(promo).split("/")[0]
    assert start == timezone.localtime(promo.created_at).strftime("%Y-%m-%dT%H:%M%z")


def test_legacy_feed_ignores_promotions():
    from apps.catalog.models import Product

    p = _product(base_price=Decimal("10.00"))
    _promo(p, price_override=Decimal("7.50"))
    xml = build_google_feed(
        products=Product.objects.filter(pk=p.pk),
        title="t",
        link="https://x/",
        description="d",
        product_url=lambda _p: "https://x/p",
        absolutize=lambda u: "https://x" + u,
    )
    assert "sale_price" not in xml and "<g:price>10.00 EUR</g:price>" in xml


def test_overview_counts_sale_rows_like_feed():
    for i in range(3):
        p = _product(base_price=Decimal("10.00"))
        if i:
            _promo(p, price_override=Decimal("8.00"))
    xml = _merchant_xml(google.merchant_products())
    assert google.overview()["on_sale"] == xml.count("<g:sale_price>") == 2


def test_promo_feed_constant_queries(django_assert_max_num_queries):
    for i in range(12):
        p = _product()
        ProductVariant.objects.create(product=p, label="S", price=Decimal("5"), stock_quantity=2)
        if i % 2:
            _promo(p, price_override=Decimal("1.00"))
    with django_assert_max_num_queries(7):
        _merchant_xml(google.merchant_products())


def test_no_sale_when_storefront_announces_no_reduction():
    """§11 PAngV: цена акции не ниже минимума 30 дней — витрина снижение не объявляет,
    фид тоже (но корзина списывает цену акции → она и есть g:price)."""
    from datetime import timedelta

    from django.utils import timezone

    from apps.catalog.models import PriceLog

    p = _product(base_price=Decimal("10.00"))
    log = PriceLog.objects.create(product=p, price=Decimal("7.00"))
    PriceLog.objects.filter(pk=log.pk).update(created_at=timezone.now() - timedelta(days=5))
    _promo(p, price_override=Decimal("7.50"), starts_at=timezone.now() - timedelta(days=1))
    item = _items(_merchant_xml(google.merchant_products()))[str(p.pk)]
    assert "sale_price" not in item and item["price"] == "7.50 EUR"
    assert google.overview()["on_sale"] == 0


def test_ended_but_still_active_promo_charges_without_sale():
    from datetime import timedelta

    from django.utils import timezone

    p = _product(base_price=Decimal("10.00"))
    now = timezone.now()
    _promo(
        p,
        price_override=Decimal("8.00"),
        starts_at=now - timedelta(days=3),
        ends_at=now - timedelta(minutes=5),
    )
    item = _items(_merchant_xml(google.merchant_products()))[str(p.pk)]
    assert "sale_price" not in item and item["price"] == "8.00 EUR"


def test_equal_price_tie_is_stable():
    from apps.promotions.price_layer import product_promo_map

    p = _product(base_price=Decimal("10.00"))
    first = _promo(p, price_override=Decimal("8.00"))
    _promo(p, price_override=Decimal("8.00"), discount_style="mystery")
    assert product_promo_map([p.pk])[p.pk] == first
    assert str(p.pk) in _merchant_xml(google.merchant_products())
