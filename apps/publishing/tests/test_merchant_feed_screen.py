"""M23b.2: экран «Google Merchant Center» — включение фида, адрес, новый адрес, что в фиде.

План — docs/m23b-merchant-feed-plan-2026-10-18.md §3 (раздел M23b.2)."""

from __future__ import annotations

import uuid

import pytest
from django.contrib.auth.models import AnonymousUser
from django.contrib.messages.middleware import MessageMiddleware
from django.contrib.sessions.middleware import SessionMiddleware
from django.test import RequestFactory
from django.urls import reverse

from apps.catalog import google
from apps.catalog.tests.factories import ProductFactory
from apps.promotions import public_views
from apps.publishing import merchant, views
from apps.publishing.models import Channel
from apps.secrets import crypto
from apps.tenants.tests.factories import TenantFactory

pytestmark = [pytest.mark.django_db, pytest.mark.urls("config.urls_tenant")]

IMG = [{"url": "/media/p.webp", "is_primary": True}]


@pytest.fixture
def owner(django_user_model):
    from apps.core.models import Membership

    user = django_user_model.objects.create_user(username=f"o{uuid.uuid4().hex[:6]}", password="x")
    Membership.objects.create(user=user, role=Membership.ROLE_OWNER)
    return user


@pytest.fixture
def staff(django_user_model):
    from apps.core.models import Membership

    user = django_user_model.objects.create_user(username=f"s{uuid.uuid4().hex[:6]}", password="x")
    Membership.objects.create(user=user, role=Membership.ROLE_STAFF)
    return user


def _req(method, user, data=None, tenant=None):
    rf = RequestFactory()
    path = "/dashboard/channels/google/merchant/"
    request = rf.post(path, data or {}) if method == "post" else rf.get(path)
    SessionMiddleware(lambda r: None).process_request(request)
    MessageMiddleware(lambda r: None).process_request(request)
    request.user = user
    request.tenant = tenant or TenantFactory.build(schema_name="t_mfs", business_type="shop")
    return request


def _post(user, **data):
    return views.merchant_feed(_req("post", user, data))


def _config():
    return Channel.objects.get(type=Channel.GOOGLE_BUSINESS).config


def _token():
    return merchant.feed_state(Channel.objects.get(type=Channel.GOOGLE_BUSINESS))["token"]


def _feed(token):
    request = RequestFactory().get(f"/feed/merchant/{token}/products.xml")
    request.META["REMOTE_ADDR"] = f"10.7.{uuid.uuid4().int % 250}.{uuid.uuid4().int % 250}"
    request.tenant = TenantFactory.build(schema_name="t_mfs", name="Laden")
    return public_views.merchant_feed_xml(request, token)


# --- доступ ---------------------------------------------------------------------------


def test_owner_sees_screen_staff_does_not(owner, staff):
    resp = views.merchant_feed(_req("get", owner))
    assert resp.status_code == 200 and "no-store" in resp["Cache-Control"]
    assert views.merchant_feed(_req("get", staff)).status_code == 403
    anon = views.merchant_feed(_req("get", AnonymousUser()))
    assert anon.status_code == 302 and "login" in anon["Location"]


def test_middleware_owner_prefix_covers_screen():
    from apps.core.middleware import CabinetOwnerAccessMiddleware

    path = reverse("gbp-merchant")
    assert any(path.startswith(p) for p in CabinetOwnerAccessMiddleware._OWNER_ONLY)


# --- включение и токен ------------------------------------------------------------------


def test_enable_without_google_connection_stores_encrypted_token(owner, isolated_ratelimit):
    assert not Channel.objects.filter(type=Channel.GOOGLE_BUSINESS).exists()
    resp = _post(owner, action="enable")
    assert resp.status_code == 302
    channel = Channel.objects.get(type=Channel.GOOGLE_BUSINESS)
    assert channel.is_enabled is False  # переключатель публикации акций не трогаем
    config = channel.config
    assert config["merchant_feed"]["enabled"] is True
    stored = config[merchant.TOKEN_KEY]
    token = crypto.decrypt(stored)
    assert token and stored != token
    assert len(token) >= 32 and all(c.isalnum() or c in "-_" for c in token)
    assert "token" not in config["merchant_feed"]


def test_feed_works_with_issued_token(owner, isolated_ratelimit):
    ProductFactory(images=IMG, description={"de": "Frisch."})
    _post(owner, action="enable")
    resp = _feed(_token())
    assert resp.status_code == 200 and resp.content.count(b"<item>") == 1


def test_enable_twice_keeps_url_disable_keeps_token(owner, isolated_ratelimit):
    ProductFactory(images=IMG)
    _post(owner, action="enable")
    first = _token()
    _post(owner, action="enable")
    assert _token() == first
    _post(owner, action="disable")
    assert _config()["merchant_feed"]["enabled"] is False
    resp = _feed(first)
    assert resp.status_code == 200 and b"<item>" not in resp.content
    _post(owner, action="enable")
    assert _token() == first


def test_rotate_needs_confirm_and_kills_old_url(owner, isolated_ratelimit):
    _post(owner, action="enable")
    old = _token()
    _post(owner, action="rotate")
    assert _token() == old
    _post(owner, action="rotate", confirm="rotate")
    new = _token()
    assert new != old
    assert _feed(old).status_code == 404
    assert _feed(new).status_code == 200
    assert _config()["merchant_feed"]["enabled"] is True


def test_actions_keep_foreign_config_keys(owner, isolated_ratelimit):
    Channel.objects.create(
        type=Channel.GOOGLE_BUSINESS,
        config={
            "refresh_token": "enc-rt",
            "location": "accounts/1/locations/2",
            "gbp_sync": {"x": 1},
        },
    )
    for data in (
        {"action": "enable"},
        {"action": "rotate", "confirm": "rotate"},
        {"action": "disable"},
    ):
        _post(owner, **data)
    config = _config()
    assert config["refresh_token"] == "enc-rt"
    assert config["location"] == "accounts/1/locations/2"
    assert config["gbp_sync"] == {"x": 1}


def test_oauth_reconnect_keeps_feed(owner, isolated_ratelimit):
    _post(owner, action="enable")
    token = _token()
    channel = Channel.objects.get(type=Channel.GOOGLE_BUSINESS)
    Channel.update_config(channel.pk, lambda c: c.update({"refresh_token": "new"}))
    assert _token() == token and _config()["merchant_feed"]["enabled"] is True


def test_rate_limited_post_changes_nothing(owner, isolated_ratelimit, monkeypatch):
    monkeypatch.setattr(views, "MERCHANT_ADMIN_LIMIT", 1)
    _post(owner, action="enable")
    token = _token()
    _post(owner, action="rotate", confirm="rotate")
    assert _token() == token


# --- строгое чтение токена фидом -----------------------------------------------------------


@pytest.mark.parametrize("stored", ["p" * 43, "gAAAAA" + "x" * 80])
def test_feed_rejects_plaintext_or_foreign_ciphertext(isolated_ratelimit, stored):
    Channel.objects.create(
        type=Channel.GOOGLE_BUSINESS,
        config={"merchant_feed": {"enabled": True}, merchant.TOKEN_KEY: stored},
    )
    assert _feed(stored).status_code == 404


def test_legacy_plaintext_token_is_not_read(isolated_ratelimit):
    legacy = "t0ken-" + "x" * 30
    Channel.objects.create(
        type=Channel.GOOGLE_BUSINESS, config={"merchant_feed": {"enabled": True, "token": legacy}}
    )
    assert _feed(legacy).status_code == 404


def test_token_key_is_rotated_by_secret_rotation():
    from apps.publishing.secrets import SECRET_KEYS

    assert merchant.TOKEN_KEY in SECRET_KEYS


# --- обзор и рендер ---------------------------------------------------------------------


def test_overview_matches_summary_and_caps_items():
    for _ in range(3):
        ProductFactory(images=[])
    ProductFactory(images=IMG, hide_in_google=True)
    ProductFactory(images=IMG, description={})
    data = google.overview(limit_per_group=2)
    assert data["included"] == 1
    assert data["excluded"]["no_image"]["count"] == 3
    assert len(data["excluded"]["no_image"]["items"]) == 2
    assert google.summary() == {"included": 1, "excluded": {"no_image": 3, "hidden": 1}}
    assert data["warnings"]["no_description"]["count"] == 1


def test_overview_constant_queries(django_assert_max_num_queries):
    for _ in range(15):
        ProductFactory(images=[])
    with django_assert_max_num_queries(4):
        google.overview()


def test_screen_lists_reasons_with_edit_links_and_no_secrets(owner, isolated_ratelimit):
    Channel.objects.create(type=Channel.GOOGLE_BUSINESS, config={"refresh_token": "enc-RT-secret"})
    bad = ProductFactory(images=[])
    _post(owner, action="enable")
    body = views.merchant_feed(_req("get", owner)).content.decode()
    assert 'data-merchant-reason="no_image"' in body
    assert reverse("catalog:product-edit", args=[bad.pk]) in body
    assert reverse("storefront-merchant-feed", args=[_token()]) in body
    assert "enc-RT-secret" not in body
    assert _config()[merchant.TOKEN_KEY] not in body


def test_feed_url_uses_primary_domain(owner, isolated_ratelimit):
    from apps.tenants.models import Domain

    tenant = TenantFactory(schema_name=f"t_{uuid.uuid4().hex[:8]}", slug=f"s{uuid.uuid4().hex[:6]}")
    Domain.objects.create(tenant=tenant, domain="laden-example.de", is_primary=True)
    _post(owner, action="enable")
    body = views.merchant_feed(_req("get", owner, tenant=tenant)).content.decode()
    assert "://laden-example.de/feed/merchant/" in body


def test_entry_points_link_to_screen(owner, isolated_ratelimit):
    from apps.publishing.tests.test_gbp_sync_views import _req as gbp_req

    request = gbp_req("get", "/dashboard/channels/google/", owner)
    assert reverse("gbp-merchant") in views.gbp_sync(request).content.decode()
    source = open("templates/publishing/channels.html", encoding="utf-8").read()
    assert "{% url 'gbp-merchant' %}" in source


def test_nav_registry_entry_is_owner_only():
    from apps.core import nav_registry

    entries = [e for e in nav_registry.ENTRIES if e.url_name == "gbp-merchant"]
    assert entries and entries[0].owner_only


def test_unreadable_token_offers_new_address_without_confirm(owner, isolated_ratelimit):
    Channel.objects.create(
        type=Channel.GOOGLE_BUSINESS,
        config={"merchant_feed": {"enabled": True}, merchant.TOKEN_KEY: "gAAAAA" + "x" * 80},
    )
    body = views.merchant_feed(_req("get", owner)).content.decode()
    assert "data-merchant-unreadable" in body and 'value="rotate"' in body
    _post(owner, action="rotate")
    assert _token() and _feed(_token()).status_code == 200


# --- M23b.3: код магазина и второй адрес ------------------------------------------------------


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("  Laden-01 ", "Laden-01"),
        ("", ""),
        ("   ", ""),
        ("mit Leerzeichen", None),
        ("Bäckerei", None),
        ("x" * 65, None),
        ("x" * 64, "x" * 64),
        (None, None),
    ],
)
def test_clean_store_code(raw, expected):
    assert merchant.clean_store_code(raw) == expected


def _store_code():
    return _config().get("merchant_feed", {}).get("store_code")


def test_store_code_saved_kept_by_actions_and_removed(owner, isolated_ratelimit):
    _post(owner, action="enable")
    _post(owner, action="store_code", store_code="Laden-01")
    assert _store_code() == "Laden-01"
    for data in ({"action": "rotate", "confirm": "rotate"}, {"action": "disable"}):
        _post(owner, **data)
    assert _store_code() == "Laden-01"
    _post(owner, action="store_code", store_code="Bäckerei 1")
    assert _store_code() == "Laden-01"  # недопустимое не перезаписывает
    _post(owner, action="store_code", store_code="")
    assert _store_code() is None


def test_store_code_from_google(owner, isolated_ratelimit, monkeypatch):
    from apps.publishing import gbp

    Channel.objects.create(type=Channel.GOOGLE_BUSINESS, config={"refresh_token": "enc"})
    monkeypatch.setattr(gbp, "location_ids", lambda config: ("v4", "locations/2"))
    monkeypatch.setattr(gbp, "access_token", lambda config: "at")
    monkeypatch.setattr(gbp, "get_store_code", lambda token, v1: "G-77")
    _post(owner, action="store_from_google")
    assert _store_code() == "G-77"
    monkeypatch.setattr(gbp, "get_store_code", lambda token, v1: "")
    _post(owner, action="store_from_google")
    assert _store_code() == "G-77"  # пустой ответ Google код не стирает
    monkeypatch.setattr(gbp, "get_store_code", lambda token, v1: "Köln 1")
    _post(owner, action="store_from_google")
    assert _store_code() == "G-77"  # недопустимый код из Google не записывается


def test_store_code_from_google_error_changes_nothing(owner, isolated_ratelimit, monkeypatch):
    from apps.publishing import gbp

    def fail(config):
        raise gbp.GbpError("not_configured")

    monkeypatch.setattr(gbp, "location_ids", fail)
    resp = _post(owner, action="store_from_google")
    assert resp.status_code == 302
    assert _store_code() is None


def test_screen_shows_local_address_and_warning(owner, isolated_ratelimit):
    _post(owner, action="enable")
    body = views.merchant_feed(_req("get", owner)).content.decode()
    assert reverse("storefront-merchant-local-feed", args=[_token()]) in body
    assert 'data-merchant-copy-group="products"' in body
    assert 'data-merchant-copy-group="local"' in body
    assert "data-merchant-no-store-code" in body
    _post(owner, action="store_code", store_code="Laden-01")
    body = views.merchant_feed(_req("get", owner)).content.decode()
    assert "data-merchant-no-store-code" not in body and 'value="Laden-01"' in body


# --- M23b.4: цена акции на экране -----------------------------------------------------------


def test_screen_counts_sale_rows(owner, isolated_ratelimit):
    from decimal import Decimal

    from apps.promotions.tests.factories import PromotionFactory

    sale = ProductFactory(images=IMG, base_price=Decimal("10.00"))
    PromotionFactory(product=sale, promo_type="discount", price_override=Decimal("8.00"))
    secret = ProductFactory(images=IMG, base_price=Decimal("10.00"))
    PromotionFactory(
        product=secret,
        promo_type="discount",
        price_override=Decimal("6.00"),
        discount_style="mystery",
    )
    _post(owner, action="enable")
    body = views.merchant_feed(_req("get", owner)).content.decode()
    assert 'data-merchant-on-sale="1"' in body
    # SF-9: сюрприз не исключает товар — он в фиде по обычной цене.
    assert 'data-merchant-reason="promo_mystery"' not in body
    feed = _feed(_token()).content
    assert feed.count(b"<g:sale_price>") == 1 and str(secret.pk).encode() in feed
