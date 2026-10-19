"""T-8.10f F-4b: подтверждение «Zurücklegen»/«Coupon», начатых в ассистенте.

План — docs/t8-10f-f4-plan-2026-10-19.md (Д-2…Д-8). GET ничего не создаёт; POST создаёт
ровно одну запись с каналом `mcp`; повтор показывает тот же итог."""

import uuid
from datetime import timedelta
from importlib import import_module

import pytest
from django.conf import settings as dj_settings
from django.contrib.messages.middleware import MessageMiddleware
from django.core.cache.backends.locmem import LocMemCache
from django.http import Http404
from django.test import RequestFactory
from django.utils import timezone

from apps.aggregator.mcp import actions
from apps.loyalty.models import Voucher
from apps.notifications.models import Notification
from apps.promotions import assistant_views, response
from apps.promotions.models import Customer, Promotion, Reservation
from apps.promotions.tests.factories import PromotionFactory
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _rl(monkeypatch):
    """Лимит частоты — в приватном кэше теста (xdist делит один Redis)."""
    from apps.core import ratelimit

    monkeypatch.setattr(ratelimit, "cache", LocMemCache(f"rl-confirm-{uuid.uuid4()}", {}))


@pytest.fixture(autouse=True)
def store(monkeypatch):
    cache = LocMemCache(f"mcp-confirm-{uuid.uuid4()}", {})
    monkeypatch.setattr(actions, "cache", cache)
    return cache


@pytest.fixture
def tenant():
    return TenantFactory(schema_name="t1", slug="baeckerei", enabled_locales=["de", "ru"])


def _promo(op=response.RESERVE, **kw):
    kw.setdefault("available_quantity", 5)
    kw.setdefault("max_per_customer", 3)
    kw.setdefault("ends_at", timezone.now() + timedelta(days=2))
    return PromotionFactory(metadata={"response": op}, **kw)


def _token(promo, op=actions.OP_RESERVE, schema="t1", **kw):
    token, _ttl = actions.create_pending(
        op=op,
        schema=schema,
        promo_id=promo.pk,
        listing_id=kw.pop("listing_id", 42),
        portal_id=1,
        email=kw.pop("email", "anna@example.com"),
        name="Anna",
        qty=kw.pop("qty", 2),
        lang=kw.pop("lang", "de"),
    )
    return token


def _req(method, tenant):
    rf = RequestFactory()
    ua = {"HTTP_USER_AGENT": "Mozilla/5.0 (X11; Linux x86_64) Firefox/120.0"}
    request = rf.post("/", **ua) if method == "post" else rf.get("/", **ua)
    request.session = import_module(dj_settings.SESSION_ENGINE).SessionStore()
    MessageMiddleware(lambda r: None).process_request(request)
    request.tenant = tenant
    return request


def _get(tenant, promo, token):
    return assistant_views.assistant_confirm(_req("get", tenant), pk=promo.pk, token=token)


def _post(tenant, promo, token):
    return assistant_views.assistant_confirm(_req("post", tenant), pk=promo.pk, token=token)


def _nothing_created():
    assert not Reservation.objects.exists()
    assert not Voucher.objects.exists()
    assert not Customer.objects.exists()
    assert not Notification.objects.exists()


# --- GET -----------------------------------------------------------------------------


def test_get_shows_question_and_creates_nothing(tenant):
    promo = _promo()
    resp = _get(tenant, promo, _token(promo))
    body = resp.content.decode()
    assert resp.status_code == 200
    assert 'data-state="ask"' in body and 'method="post"' in body
    assert "a***@example.com" in body and "anna@example.com" not in body
    assert resp["Referrer-Policy"] == "no-referrer"
    assert "no-cache" in resp["Cache-Control"]
    _nothing_created()


def test_unknown_or_expired_token_is_honest(tenant):
    promo = _promo()
    resp = _get(tenant, promo, "x" * 43)
    assert resp.status_code == 410 and 'data-state="invalid"' in resp.content.decode()


def test_foreign_tenant_or_promotion_is_404(tenant):
    promo = _promo()
    token = _token(promo, schema="anderer")
    with pytest.raises(Http404):
        _get(tenant, promo, token)
    other = _promo()
    with pytest.raises(Http404):
        _get(tenant, other, _token(promo))
    _nothing_created()


# --- POST: Zurücklegen ---------------------------------------------------------------


def test_post_reserves_once_with_mcp_channel(tenant, mailoutbox):
    promo = _promo()
    token = _token(promo)
    resp = _post(tenant, promo, token)
    res = Reservation.objects.get()
    assert resp.status_code == 302 and res.reference_code in resp["Location"]
    assert res.source_channel == "mcp" and res.quantity == 2
    assert res.customer.email == "anna@example.com"
    assert res.customer.marketing_opt_in_at is None  # подтверждение ≠ согласие на рассылку
    # повторный клик — тот же итог, без второй записи
    again = _post(tenant, promo, token)
    assert again.status_code == 302 and res.reference_code in again["Location"]
    again_get = _get(tenant, promo, token)
    assert again_get.status_code == 302
    assert Reservation.objects.count() == 1
    promo.refresh_from_db()
    assert promo.available_quantity == 3


def test_sold_out_is_reported_and_stock_never_negative(tenant):
    promo = _promo(available_quantity=1)
    resp = _post(tenant, promo, _token(promo, qty=2))
    assert 'data-state="sold_out"' in resp.content.decode()
    promo.refresh_from_db()
    assert promo.available_quantity == 1 and not Reservation.objects.exists()


def test_owner_changed_response_meanwhile(tenant):
    promo = _promo()
    token = _token(promo)
    promo.metadata = {"response": response.SHOW}
    promo.save(update_fields=["metadata"])
    resp = _post(tenant, promo, token)
    assert 'data-state="unavailable"' in resp.content.decode()
    _nothing_created()


def test_ended_promotion_meanwhile(tenant):
    promo = _promo()
    token = _token(promo)
    promo.status = "ended"
    promo.save(update_fields=["status"])
    assert 'data-state="unavailable"' in _post(tenant, promo, token).content.decode()
    assert not Reservation.objects.exists()


def test_busy_claim_does_not_double(tenant):
    promo = _promo()
    token = _token(promo)
    assert actions.claim(token)  # другой клик уже исполняется
    resp = _post(tenant, promo, token)
    assert resp.status_code == 409
    assert not Reservation.objects.exists()


@pytest.fixture
def owner_tenant(tenant, monkeypatch):
    """Письма резерва ищут тенанта по схеме соединения (в тестах — public) → подставляем."""
    from apps.promotions import notifications

    monkeypatch.setattr(notifications, "_tenant", lambda schema: tenant)
    return tenant


def test_demo_owner_gets_no_mail_but_customer_does(owner_tenant):
    tenant = owner_tenant
    tenant.is_demo = True
    tenant.owner_email = "demo@example.de"
    tenant.save(update_fields=["is_demo", "owner_email"])
    promo = _promo()
    _post(tenant, promo, _token(promo))
    recipients = set(Notification.objects.values_list("recipient", flat=True))
    assert "demo@example.de" not in recipients
    assert "anna@example.com" in recipients


def test_real_owner_still_gets_mail(owner_tenant):
    tenant = owner_tenant
    tenant.owner_email = "inhaber@baeckerei.de"
    tenant.save(update_fields=["owner_email"])
    promo = _promo()
    _post(tenant, promo, _token(promo))
    recipients = set(Notification.objects.values_list("recipient", flat=True))
    assert "inhaber@baeckerei.de" in recipients


def test_deal_counted_for_listing_from_pending(tenant, monkeypatch):
    from apps.aggregator import conversions

    seen = []
    monkeypatch.setattr(
        conversions,
        "count",
        lambda request, action, kind, obj, *, attribution=None, once_key="": seen.append(
            (action, kind, attribution.channel, attribution.listing)
        ),
    )
    promo = _promo()
    _post(tenant, promo, _token(promo, listing_id=77))
    assert seen == [("deal", "reservation", "mcp", 77)]


# --- POST: Coupon --------------------------------------------------------------------


def test_coupon_issued_once_mailed_and_remembered(tenant):
    promo = _promo(response.COUPON)
    token = _token(promo, op=actions.OP_COUPON)
    resp = _post(tenant, promo, token)
    voucher = Voucher.objects.get()
    assert voucher.source_channel == "mcp" and voucher.promotion_id == promo.pk
    assert resp.status_code == 302 and voucher.code in resp["Location"]
    assert "sa_coupons" in resp.cookies
    mails = Notification.objects.filter(recipient="anna@example.com", type="coupon_issued")
    assert mails.count() == 1 and voucher.code in str(mails.get().payload)
    _post(tenant, promo, token)
    assert Voucher.objects.count() == 1
    assert Notification.objects.filter(type="coupon_issued").count() == 1


def test_same_address_gets_same_coupon_without_new_deal(tenant, monkeypatch):
    from apps.aggregator import conversions

    counted = []
    monkeypatch.setattr(conversions, "count", lambda *a, **k: counted.append(a[2]))
    promo = _promo(response.COUPON)
    _post(tenant, promo, _token(promo, op=actions.OP_COUPON))
    _post(tenant, promo, _token(promo, op=actions.OP_COUPON))
    assert Voucher.objects.count() == 1 and counted == ["coupon"]


def test_coupon_sold_out(tenant):
    promo = _promo(response.COUPON, available_quantity=0)
    resp = _post(tenant, promo, _token(promo, op=actions.OP_COUPON))
    assert 'data-state="sold_out"' in resp.content.decode()
    assert not Voucher.objects.exists()


def test_language_from_assistant_when_enabled(tenant):
    promo = _promo()
    body = _get(tenant, promo, _token(promo, lang="ru")).content.decode()
    assert "Подтвердить резерв" in body


def test_language_not_enabled_falls_back(tenant):
    promo = _promo()
    body = _get(tenant, promo, _token(promo, lang="tr")).content.decode()
    assert "Reservierung bestätigen" in body


def test_failure_before_outcome_releases_claim(tenant, monkeypatch):
    from apps.promotions import services

    def boom(*a, **k):
        raise RuntimeError("db down")

    monkeypatch.setattr(services, "reserve", boom)
    promo = _promo()
    token = _token(promo)
    with pytest.raises(RuntimeError):
        _post(tenant, promo, token)
    assert actions.claim(token)  # можно нажать ещё раз


def test_outcome_from_other_tenant_is_404(tenant):
    promo = _promo()
    token = _token(promo)
    _post(tenant, promo, token)
    other = TenantFactory(schema_name="t2", slug="anders")
    with pytest.raises(Http404):
        _get(other, promo, token)


def test_foreign_host_cannot_burn_pending_token(tenant):
    promo = _promo()
    token = _token(promo)
    other = TenantFactory(schema_name="t2", slug="anders")
    with pytest.raises(Http404):
        _post(other, promo, token)
    assert actions.load_pending(token) is not None
    assert actions.claim(token)  # не занят чужим хостом


def test_get_for_unusable_promo_does_not_spend_link(tenant):
    promo = _promo()
    token = _token(promo)
    promo.metadata = {"response": response.SHOW}
    promo.save(update_fields=["metadata"])
    assert 'data-state="unavailable"' in _get(tenant, promo, token).content.decode()
    promo.metadata = {"response": response.RESERVE}
    promo.save(update_fields=["metadata"])
    assert 'data-state="ask"' in _get(tenant, promo, token).content.decode()


def test_promo_past_end_is_not_usable_even_before_beat(tenant):
    promo = _promo()
    token = _token(promo)
    Promotion.objects.filter(pk=promo.pk).update(ends_at=timezone.now() - timedelta(minutes=5))
    assert 'data-state="unavailable"' in _post(tenant, promo, token).content.decode()
    assert not Reservation.objects.exists()


def test_lost_outcome_is_recovered_from_db(tenant, monkeypatch):
    """Кэш не принял итог: второй клик находит запись в БД, а не создаёт вторую."""
    promo = _promo()
    token = _token(promo)
    real = actions.finish
    monkeypatch.setattr(actions, "finish", lambda *a, **k: None)
    _post(tenant, promo, token)
    res = Reservation.objects.get()
    monkeypatch.setattr(actions, "finish", real)
    resp = _post(tenant, promo, token)
    assert resp.status_code == 302 and res.reference_code in resp["Location"]
    assert Reservation.objects.count() == 1


def test_failure_inside_reserve_rolls_back_and_allows_retry(tenant, monkeypatch):
    from apps.promotions import services

    promo = _promo()
    token = _token(promo)
    real = services.enqueue_reservation_email

    def boom(*a, **k):
        raise RuntimeError("mail down")

    monkeypatch.setattr(services, "enqueue_reservation_email", boom)
    with pytest.raises(RuntimeError):
        _post(tenant, promo, token)
    assert not Reservation.objects.exists()
    promo.refresh_from_db()
    assert promo.available_quantity == 5
    monkeypatch.setattr(services, "enqueue_reservation_email", real)
    assert _post(tenant, promo, token).status_code == 302
    assert Reservation.objects.count() == 1


def test_coupon_mail_failure_does_not_break_redirect(tenant, monkeypatch):
    def boom(*a, **k):
        raise RuntimeError("smtp down")

    monkeypatch.setattr(assistant_views, "_send_coupon_email", boom)
    promo = _promo(response.COUPON)
    resp = _post(tenant, promo, _token(promo, op=actions.OP_COUPON))
    assert resp.status_code == 302 and Voucher.objects.get().code in resp["Location"]


def test_mute_is_restored_and_demo_owner_gets_no_telegram(owner_tenant, monkeypatch):
    from apps.notifications import prefs
    from apps.telegram import notify as tg

    sent = []
    monkeypatch.setattr(tg, "send_to_owner", lambda *a, **k: sent.append(k.get("type")))
    owner_tenant.is_demo = True
    owner_tenant.save(update_fields=["is_demo"])
    promo = _promo()
    _post(owner_tenant, promo, _token(promo))
    assert sent == []
    assert getattr(prefs._mute, "owner", False) is False


def test_real_deal_row_for_mcp_channel(tenant, django_capture_on_commit_callbacks):
    from apps.aggregator.models import PortalStat
    from apps.aggregator.tests.test_machine_readable import _listing

    promo = _promo()
    listing = _listing(source_ref=str(promo.pk), tenant_schema="t1")
    with django_capture_on_commit_callbacks(execute=True):
        _post(tenant, promo, _token(promo, listing_id=listing.pk))
    row = PortalStat.objects.get(action="deal")
    assert row.channel == "mcp" and row.listing_id == listing.pk


def test_headers_forbid_indexing(tenant):
    promo = _promo()
    resp = _get(tenant, promo, _token(promo))
    assert "noindex" in resp["X-Robots-Tag"]


# --- «Das war ich nicht» ---------------------------------------------------------------


def _decline(method, tenant, promo, token):
    return assistant_views.assistant_decline(_req(method, tenant), pk=promo.pk, token=token)


def test_decline_get_asks_and_changes_nothing(tenant):
    promo = _promo()
    token = _token(promo)
    body = _decline("get", tenant, promo, token).content.decode()
    assert 'data-state="decline_ask"' in body
    assert actions.load_pending(token) is not None
    assert not actions.is_suppressed("anna@example.com")


def test_decline_post_kills_link_and_silences_address(tenant):
    promo = _promo()
    token = _token(promo)
    body = _decline("post", tenant, promo, token).content.decode()
    assert 'data-state="declined"' in body
    assert actions.is_suppressed("anna@example.com")
    assert actions.load_pending(token) is None
    # ссылка подтверждения больше ничего не создаёт
    _post(tenant, promo, token)
    assert not Reservation.objects.exists()


def test_decline_from_foreign_host_is_404(tenant):
    promo = _promo()
    token = _token(promo)
    other = TenantFactory(schema_name="t2", slug="anders")
    with pytest.raises(Http404):
        _decline("post", other, promo, token)
    assert not actions.is_suppressed("anna@example.com")
