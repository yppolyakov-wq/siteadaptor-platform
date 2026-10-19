"""T-8.10f F-4a: ядро «ожидающих действий» ассистента (план
docs/t8-10f-f4-plan-2026-10-19.md, Д-1, Д-9, Д-11, Д-12).

Замки: токен одноразовый, в кэше нет ни токена, ни адреса открытым текстом, срок не
дольше суток и конца акции, предпроверка не трогает данные человека."""

import uuid
from datetime import timedelta

import pytest
from django.core.cache.backends.locmem import LocMemCache
from django.test import RequestFactory, override_settings
from django.utils import timezone

from apps.aggregator.mcp import actions
from apps.aggregator.tests.test_machine_readable import _listing
from apps.promotions import response
from apps.promotions.tests.factories import PromotionFactory
from apps.tenants.models import Domain
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def store(monkeypatch, isolated_ratelimit):
    """Кэш ожидающих действий — приватный (xdist делит один Redis, урок CI #2683)."""
    cache = LocMemCache(f"mcp-actions-{uuid.uuid4()}", {})
    monkeypatch.setattr(actions, "cache", cache)
    return cache


@pytest.fixture
def tenant():
    return TenantFactory(schema_name="t1", slug="baeckerei", city="Solingen")


def _pending(**kw):
    defaults = {
        "op": actions.OP_RESERVE,
        "schema": "t1",
        "promo_id": uuid.uuid4(),
        "listing_id": 7,
        "portal_id": 1,
        "email": "Anna@Example.com",
        "name": "Anna",
        "qty": 2,
        "lang": "ru",
    }
    defaults.update(kw)
    return actions.create_pending(**defaults)


# --- токен ---------------------------------------------------------------------------


def test_store_keeps_neither_token_nor_address_in_clear(store):
    token, ttl = _pending()
    keys = list(store._cache)
    assert keys and all(token not in k for k in keys)
    dump = repr(dict(store._cache))
    assert "anna@example.com" not in dump.lower() and "Anna" not in dump
    loaded = actions.load_pending(token)
    assert loaded["email"] == "anna@example.com" and loaded["name"] == "Anna"
    assert loaded["qty"] == 2 and loaded["lang"] == "ru" and loaded["op"] == "reserve"
    assert ttl == 86400


def test_ttl_is_capped_by_promotion_end():
    soon = timezone.now() + timedelta(hours=2)
    _token, ttl = _pending(ends_at=soon)
    assert 7000 < ttl <= 7200


def test_ended_promotion_gives_no_pending():
    assert _pending(ends_at=timezone.now() - timedelta(minutes=1)) is None


@override_settings(MCP_ACTION_TTL=60)
def test_ttl_follows_setting():
    assert _pending()[1] == 60


def test_claim_is_one_time_and_finish_keeps_outcome():
    token, _ttl = _pending()
    assert actions.claim(token) is True
    assert actions.claim(token) is False  # двойной клик/гонка
    actions.finish(token, {"result": "reserved", "code": "R-ABC123"})
    assert actions.outcome(token)["code"] == "R-ABC123"
    assert actions.load_pending(token) is None  # адрес удалён после исполнения


def test_garbage_tokens_are_rejected():
    for bad in ("", "x", "a" * 500, None, 123):
        assert actions.load_pending(bad) is None
        assert actions.claim(bad) is False
        assert actions.outcome(bad) is None


def test_release_allows_retry():
    token, _ttl = _pending()
    assert actions.claim(token)
    actions.release(token)
    assert actions.claim(token)


def test_unknown_op_is_programming_error():
    with pytest.raises(ValueError):
        _pending(op="buy")


# --- почта ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "backend,ready",
    [
        ("django.core.mail.backends.console.EmailBackend", False),
        ("django.core.mail.backends.dummy.EmailBackend", False),
        ("django.core.mail.backends.filebased.EmailBackend", False),
        ("django.core.mail.backends.smtp.EmailBackend", True),
        ("anymail.backends.resend.EmailBackend", True),
        ("django.core.mail.backends.locmem.EmailBackend", True),
    ],
)
def test_mail_ready_only_for_real_delivery(backend, ready):
    with override_settings(EMAIL_BACKEND=backend):
        assert actions.mail_ready() is ready


def test_enabled_needs_switch_and_real_mail():
    with override_settings(MCP_ACTIONS_ENABLED=False):
        assert actions.enabled() is False
    with override_settings(
        MCP_ACTIONS_ENABLED=True, EMAIL_BACKEND="django.core.mail.backends.console.EmailBackend"
    ):
        assert actions.enabled() is False
    with override_settings(MCP_ACTIONS_ENABLED=True):
        assert actions.enabled() is True


# --- предпроверка --------------------------------------------------------------------


def _promo_listing(promo, **kw):
    return _listing(source_ref=str(promo.pk), **kw)


def _code(listing, op, qty=1):
    with pytest.raises(actions.PrecheckError) as err:
        actions.precheck(listing, op, qty)
    return err.value.code


def test_precheck_accepts_matching_response(tenant):
    promo = PromotionFactory(metadata={"response": response.RESERVE})
    checked = actions.precheck(_promo_listing(promo), actions.OP_RESERVE, 2)
    assert checked.promo_id == str(promo.pk) and checked.tenant.pk == tenant.pk


def test_precheck_refusals(tenant):
    coupon = PromotionFactory(metadata={"response": response.COUPON})
    assert _code(_promo_listing(coupon), actions.OP_RESERVE) == actions.NOT_RESERVABLE
    reserve = PromotionFactory(metadata={"response": response.RESERVE})
    assert _code(_promo_listing(reserve), actions.OP_COUPON) == actions.NOT_COUPON
    sold = PromotionFactory(metadata={"response": response.RESERVE}, available_quantity=1)
    assert _code(_promo_listing(sold), actions.OP_RESERVE, 2) == actions.SOLD_OUT
    capped = PromotionFactory(metadata={"response": response.RESERVE}, max_per_customer=1)
    assert _code(_promo_listing(capped), actions.OP_RESERVE, 2) == actions.LIMIT
    paused = PromotionFactory(metadata={"response": response.RESERVE}, status="paused")
    assert _code(_promo_listing(paused), actions.OP_RESERVE) == actions.NOT_FOUND
    ended = PromotionFactory(
        metadata={"response": response.RESERVE}, ends_at=timezone.now() - timedelta(hours=1)
    )
    assert _code(_promo_listing(ended), actions.OP_RESERVE) == actions.NOT_FOUND
    assert _code(_listing(listing_kind="stay"), actions.OP_RESERVE) == actions.NOT_FOUND
    assert _code(_listing(source_ref="kein-uuid"), actions.OP_RESERVE) == actions.NOT_FOUND


def test_precheck_refuses_business_out_of_catalog(tenant):
    tenant.in_city_catalog = False
    tenant.save(update_fields=["in_city_catalog"])
    promo = PromotionFactory(metadata={"response": response.RESERVE})
    assert _code(_promo_listing(promo), actions.OP_RESERVE) == actions.NOT_FOUND


def test_precheck_never_touches_customers(tenant, monkeypatch):
    from apps.promotions import models as pm

    def boom(*a, **k):
        raise AssertionError("Customer queried before consent")

    monkeypatch.setattr(pm.Customer.objects, "filter", boom)
    monkeypatch.setattr(pm.Customer.objects, "get_or_create", boom)
    promo = PromotionFactory(metadata={"response": response.RESERVE})
    actions.precheck(_promo_listing(promo), actions.OP_RESERVE)


def test_precheck_uses_one_schema_context(tenant, monkeypatch):
    import django_tenants.utils as tu

    calls = []
    real = tu.schema_context
    monkeypatch.setattr(tu, "schema_context", lambda s: calls.append(s) or real(s))
    promo = PromotionFactory(metadata={"response": response.RESERVE})
    actions.precheck(_promo_listing(promo), actions.OP_RESERVE)
    assert calls == ["t1"]


# --- лимиты --------------------------------------------------------------------------


def _req(ip="10.0.0.1"):
    req = RequestFactory().post("/mcp/")
    req.META["REMOTE_ADDR"] = ip
    return req


def test_same_address_and_offer_gets_already_sent_on_repeat():
    assert actions.check_limits(_req(), email="a@b.de", listing_id=1) is None
    assert actions.check_limits(_req(), email="A@b.de", listing_id=1) == actions.ALREADY_SENT


@override_settings(MCP_ACTION_RATE_EMAIL=2)
def test_address_limit_across_offers():
    assert actions.check_limits(_req(), email="a@b.de", listing_id=1) is None
    assert actions.check_limits(_req(), email="a@b.de", listing_id=2) is None
    assert actions.check_limits(_req(), email="a@b.de", listing_id=3) == actions.LIMIT


@override_settings(MCP_ACTION_RATE_OFFER=2)
def test_offer_limit_across_addresses():
    for n in range(2):
        assert actions.check_limits(_req(), email=f"p{n}@b.de", listing_id=9) is None
    assert actions.check_limits(_req(), email="p9@b.de", listing_id=9) == actions.LIMIT


@override_settings(MCP_ACTION_RATE_GLOBAL=1)
def test_global_mail_ceiling():
    assert actions.check_limits(_req(), email="a@b.de", listing_id=1) is None
    assert actions.check_limits(_req(), email="c@d.de", listing_id=2) == actions.LIMIT


@override_settings(MCP_ACTION_RATE_IP=1)
def test_ip_limit():
    assert actions.check_limits(_req(), email="a@b.de", listing_id=1) is None
    assert actions.check_limits(_req(), email="c@d.de", listing_id=2) == actions.LIMIT


def test_limit_keys_hold_no_address(isolated_ratelimit):
    actions.check_limits(_req(), email="geheim@example.com", listing_id=1)
    assert "geheim" not in repr(list(isolated_ratelimit._cache))


# --- ссылка --------------------------------------------------------------------------


def test_confirm_url_points_to_business_domain(tenant):
    Domain.objects.create(tenant=tenant, domain="baeckerei.siteadaptor.de", is_primary=True)
    pk = uuid.uuid4()
    token = "tok_" + "a" * 40
    url = actions.confirm_url(tenant, pk, token)
    assert url == f"https://baeckerei.siteadaptor.de/p/{pk}/ki-bestaetigen/{token}/"


def test_confirm_url_empty_without_domain(tenant):
    assert actions.confirm_url(tenant, uuid.uuid4(), "x" * 40) == ""
