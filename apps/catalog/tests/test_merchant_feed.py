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
    minidom.parseString(resp.content)
    assert b"<item>" not in resp.content


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
