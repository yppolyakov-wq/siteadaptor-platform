"""KA-12 E4.4b (B6): гостевая страница «Termin verwalten» (подписанная ссылка).

Чужой/битый токен — 404; GET ничего не меняет; заголовки не пускают токен наружу;
POST отменяет/переносит по правилам снимка; лимит частоты; CSRF не снят."""

import uuid
from datetime import timedelta

import pytest
from django.core.cache.backends.locmem import LocMemCache
from django.http import Http404

from apps.booking import cancel_policy, public_views, services
from apps.booking.models import Booking
from apps.booking.tests.test_public import _req
from apps.booking.tests.test_services import _aware, _future_day, _resource, _rule, _service

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _rl(monkeypatch, settings):
    from apps.core import ratelimit

    settings.ROOT_URLCONF = "config.urls_tenant"
    monkeypatch.setattr(ratelimit, "cache", LocMemCache(f"rl-manage-{uuid.uuid4()}", {}))


def _booking():
    day = _future_day()
    r = _resource(type="staff")
    _rule(r, day, "09:00", "18:00", slot=30)
    svc = _service(duration_minutes=60)
    b = services.book(
        r,
        start=_aware(day, 10),
        end=_aware(day, 11),
        name="Gast",
        email="g@t.de",
        service=svc,
        auto_confirm=True,
    )
    return day, b


def _path(token):
    return f"/termin/verwalten/{token}/"


def test_bad_token_404():
    with pytest.raises(Http404):
        public_views.termin_manage(_req(path=_path("x")), "x")
    forged = "abc:def"
    with pytest.raises(Http404):
        public_views.termin_manage(_req(path=_path(forged)), forged)


def test_reference_code_is_not_a_token():
    _, b = _booking()
    with pytest.raises(Http404):
        public_views.termin_manage(_req(path=_path(b.reference_code)), b.reference_code)


def test_get_has_no_side_effects_and_safe_headers():
    _, b = _booking()
    token = cancel_policy.manage_token(b)
    resp = public_views.termin_manage(_req(path=_path(token)), token)
    assert resp.status_code == 200
    assert resp["Referrer-Policy"] == "no-referrer"
    assert "noindex" in resp["X-Robots-Tag"]
    assert resp["Cache-Control"] == "no-store"
    body = resp.content.decode()
    assert 'name="action" value="cancel"' in body and 'value="move"' in body
    b.refresh_from_db()
    assert b.status == "confirmed" and b.reschedule_count == 0


def test_post_cancel(monkeypatch):
    from apps.core import money_contract, refunds

    monkeypatch.setattr(refunds, "refund_payment", lambda *a, **k: refunds.RefundResult.NONE)
    monkeypatch.setattr(money_contract, "retain_on_cancel", lambda *a, **k: None)
    _, b = _booking()
    token = cancel_policy.manage_token(b)
    resp = public_views.termin_manage(_req("post", _path(token), {"action": "cancel"}), token)
    assert resp.status_code == 302
    b.refresh_from_db()
    assert b.status == "cancelled"


def test_honeypot_does_nothing():
    _, b = _booking()
    token = cancel_policy.manage_token(b)
    public_views.termin_manage(
        _req("post", _path(token), {"action": "cancel", "website": "x"}), token
    )
    b.refresh_from_db()
    assert b.status == "confirmed"


def test_post_move():
    day, b = _booking()
    token = cancel_policy.manage_token(b)
    start = _aware(day, 14)
    resp = public_views.termin_manage(
        _req("post", _path(token), {"action": "move", "start": start.isoformat()}), token
    )
    assert resp.status_code == 302
    b.refresh_from_db()
    assert b.start == start and b.reschedule_count == 1


def test_post_move_junk_start_404():
    _, b = _booking()
    token = cancel_policy.manage_token(b)
    with pytest.raises(Http404):
        public_views.termin_manage(
            _req("post", _path(token), {"action": "move", "start": "nope"}), token
        )


def test_rate_limited():
    _, b = _booking()
    token = cancel_policy.manage_token(b)
    codes = set()
    for _ in range(public_views.RL_LIMIT + 2):
        req = _req("post", _path(token), {"action": "unknown"})
        req.META["REMOTE_ADDR"] = "10.9.9.9"
        try:
            codes.add(public_views.termin_manage(req, token).status_code)
        except Http404:
            codes.add(404)
    assert 429 in codes


def test_csrf_not_exempt():
    assert not getattr(public_views.termin_manage, "csrf_exempt", False)


def test_group_token_points_to_first_member():
    _, b = _booking()
    Booking.objects.filter(pk=b.pk).update(group_code="G-T")
    b.refresh_from_db()
    later = Booking.objects.create(
        resource=b.resource,
        customer=b.customer,
        reference_code="T-GRP2",
        start=b.start + timedelta(hours=3),
        end=b.end + timedelta(hours=3),
        group_code="G-T",
    )
    assert cancel_policy.booking_from_token(cancel_policy.manage_token(later)).pk == b.pk


def test_emails_carry_manage_link_and_owner_is_told(
    monkeypatch, django_capture_on_commit_callbacks
):
    from apps.booking import notifications

    sent = []
    monkeypatch.setattr(notifications, "notify", lambda **kw: sent.append(kw))
    monkeypatch.setattr(notifications, "_base_url", lambda schema: "https://x.test")
    monkeypatch.setattr(notifications, "_owner_email", lambda t: "owner@x.test")
    _, b = _booking()
    notifications.enqueue_booking_email(b, "confirmed")
    mail = next(m for m in sent if m["type"] == "booking_confirmed")
    assert "/termin/verwalten/" in mail["body"]
    assert b.reference_code not in mail["body"].split("/termin/verwalten/")[1].split()[0]

    sent.clear()
    with django_capture_on_commit_callbacks(execute=True):
        cancel_policy.guest_cancel(b)
    assert any(m["type"] == "booking_guest_cancelled_owner" for m in sent)


def test_legacy_booking_email_has_no_manage_link(monkeypatch):
    from apps.booking import notifications

    sent = []
    monkeypatch.setattr(notifications, "notify", lambda **kw: sent.append(kw))
    monkeypatch.setattr(notifications, "_base_url", lambda schema: "https://x.test")
    _, b = _booking()
    Booking.objects.filter(pk=b.pk).update(cancel_policy={})
    b.refresh_from_db()
    sent.clear()
    notifications.enqueue_booking_email(b, "confirmed")
    assert sent and all("/termin/verwalten/" not in m["body"] for m in sent)


def test_confirmation_page_has_no_manage_token():
    _, b = _booking()
    resp = public_views.termin_confirmation(_req(path=f"/t/{b.reference_code}/"), b.reference_code)
    assert "/termin/verwalten/" not in resp.content.decode()


def test_staff_cannot_change_cancel_policy(monkeypatch):
    """Решение владельца: правила отмены — owner/admin; поля от staff игнорируются (W0)."""
    from apps.booking import views

    _, b = _booking()
    svc = b.service
    monkeypatch.setattr(views, "_can_edit_policy", lambda user: False)
    req = _req(
        "post",
        "/dashboard/booking/services/",
        {
            "action": "update",
            "service": str(svc.pk),
            "duration": "60",
            "price_eur": "10",
            "cancel_policy_present": "1",
            "cancel_window_hours": "2",
            "late_cancel": "refund",
        },
    )
    req.user = type("U", (), {"is_authenticated": True, "is_active": True})()
    views.services_view.__wrapped__(req)  # без @login_required — роль подменена выше
    svc.refresh_from_db()
    assert svc.cancel_window_hours == 24 and svc.late_cancel == "keep_deposit"
    monkeypatch.setattr(views, "_can_edit_policy", lambda user: True)
    req2 = _req("post", "/dashboard/booking/services/", dict(req.POST.items()))
    req2.user = req.user
    views.services_view.__wrapped__(req2)
    svc.refresh_from_db()
    assert svc.cancel_window_hours == 2 and svc.late_cancel == "refund"
