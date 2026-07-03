"""B4/CM-9: купон-кампании по сегментам — сегменты, отправка, авто-win-back."""

from datetime import timedelta
from decimal import Decimal

import pytest
from django.test import RequestFactory
from django.utils import timezone

from apps.finance.models import RevenueEntry
from apps.loyalty.models import Voucher
from apps.notifications.models import Notification
from apps.promotions import newsletter, tasks
from apps.promotions.models import CouponCampaign, Customer

pytestmark = pytest.mark.django_db

_BASE = "http://laden.test"


def _customer(email, *, opt_in=True, tags=None, **kw):
    return Customer.objects.create(
        name=email.split("@")[0], email=email, marketing_opt_in=opt_in, tags=tags or [], **kw
    )


def _purchase(customer, *, days_ago, amount="20.00"):
    return RevenueEntry.objects.create(
        amount=Decimal(amount),
        date=timezone.localdate() - timedelta(days=days_ago),
        customer=customer,
    )


# ---------------------------------------------------------------------------
# B4.1: segment_customers
# ---------------------------------------------------------------------------


def test_segment_is_built_on_top_of_consent_gate():
    _customer("no-optin@test.de", opt_in=False, tags=["vip"])
    _customer("unsub@test.de", tags=["vip"], unsubscribed=True)
    yes = _customer("yes@test.de", tags=["vip"])
    got = list(newsletter.segment_customers(tag="vip"))
    assert got == [yes]


def test_segment_tag_is_case_insensitive_input():
    c = _customer("a@test.de", tags=["stammkunde"])
    assert list(newsletter.segment_customers(tag=" Stammkunde ")) == [c]


def test_segment_inactive_days_targets_past_buyers_only():
    old = _customer("old@test.de")
    _purchase(old, days_ago=90)
    recent = _customer("recent@test.de")
    _purchase(recent, days_ago=5)
    never = _customer("never@test.de")  # без покупок — НЕ win-back-кандидат

    got = set(newsletter.segment_customers(inactive_days=60))
    assert old in got and recent not in got and never not in got


def test_segment_top_ltv_orders_and_slices():
    small = _customer("small@test.de")
    _purchase(small, days_ago=10, amount="5.00")
    big = _customer("big@test.de")
    _purchase(big, days_ago=10, amount="100.00")
    _purchase(big, days_ago=20, amount="50.00")
    _customer("nobuy@test.de")  # LTV 0 → не входит

    got = list(newsletter.segment_customers(top_ltv=1))
    assert got == [big]


# ---------------------------------------------------------------------------
# B4.2: send_coupon_campaign
# ---------------------------------------------------------------------------


def _campaign(**kw):
    defaults = dict(
        name="Herbst −10 %",
        subject="Ihr Gutschein",
        body="Danke, dass Sie bei uns kaufen.",
        discount_percent=10,
        valid_days=14,
    )
    defaults.update(kw)
    return CouponCampaign.objects.create(**defaults)


def test_send_issues_personal_codes_and_letters():
    a = _customer("a@test.de", tags=["vip"])
    b = _customer("b@test.de", tags=["vip"])
    _customer("skip@test.de")  # вне сегмента
    camp = _campaign(tag="vip")

    n = newsletter.send_coupon_campaign(camp, base_url=_BASE)
    assert n == 2
    camp.refresh_from_db()
    assert camp.status == CouponCampaign.STATUS_SENT and camp.recipient_count == 2

    va = Voucher.objects.get(customer=a)
    assert va.campaign_id == camp.pk and va.max_uses == 1
    assert va.discount_percent == 10 and va.expires_at is not None
    assert Voucher.objects.filter(customer=b).exists()

    letter = Notification.objects.get(type="coupon_campaign", recipient="a@test.de")
    body = letter.payload["body"]
    assert va.code in body and "−10 %" in body and "Abmelden" in body
    assert "List-Unsubscribe" in letter.payload["headers"]


def test_send_is_idempotent_for_manual_campaign():
    _customer("a@test.de")
    camp = _campaign()
    newsletter.send_coupon_campaign(camp, base_url=_BASE)
    camp.refresh_from_db()
    n2 = newsletter.send_coupon_campaign(camp, base_url=_BASE)
    assert n2 == 1  # признан отправленным, вернул recipient_count
    assert Voucher.objects.count() == 1
    assert Notification.objects.filter(type="coupon_campaign").count() == 1


def test_send_never_reaches_non_opt_in():
    _customer("no@test.de", opt_in=False)
    camp = _campaign()
    n = newsletter.send_coupon_campaign(camp, base_url=_BASE)
    assert n == 0
    assert not Voucher.objects.exists()
    assert not Notification.objects.filter(type="coupon_campaign").exists()


# ---------------------------------------------------------------------------
# B4.2: кабинетная вью
# ---------------------------------------------------------------------------


def _view_req(method="get", data=None, params=""):
    import uuid

    from django.contrib.auth import get_user_model
    from django.contrib.messages.middleware import MessageMiddleware
    from django.contrib.sessions.middleware import SessionMiddleware

    req = getattr(RequestFactory(), method)(f"/promotions/kampagnen/{params}", data or {})
    SessionMiddleware(lambda r: None).process_request(req)
    MessageMiddleware(lambda r: None).process_request(req)
    uname = f"o{uuid.uuid4().hex[:10]}"
    req.user = get_user_model().objects.create_user(
        username=uname, email=f"{uname}@t.de", password="pw12345678"
    )
    req.build_absolute_uri = lambda p="/": _BASE + p
    return req


def test_view_create_and_send_flow():
    from apps.promotions.views import coupon_campaigns

    _customer("a@test.de", tags=["vip"])
    resp = coupon_campaigns(
        _view_req(
            "post",
            {
                "action": "create",
                "name": "VIP",
                "tag": "VIP",
                "discount_percent": "15",
                "valid_days": "30",
                "subject": "Gutschein",
                "body": "",
            },
        )
    )
    assert resp.status_code == 302
    camp = CouponCampaign.objects.get(name="VIP")
    assert camp.tag == "vip" and camp.discount_percent == 15

    resp = coupon_campaigns(_view_req("post", {"action": "send", "campaign": str(camp.pk)}))
    assert resp.status_code == 302
    camp.refresh_from_db()
    assert camp.status == CouponCampaign.STATUS_SENT
    assert Voucher.objects.filter(campaign=camp).count() == 1


def test_view_requires_percent_or_eur():
    from apps.promotions.views import coupon_campaigns

    coupon_campaigns(
        _view_req(
            "post",
            {"action": "create", "name": "X", "valid_days": "30", "subject": "S"},
        )
    )
    assert not CouponCampaign.objects.exists()


def test_view_winback_toggle_creates_singleton():
    from apps.promotions.views import coupon_campaigns

    coupon_campaigns(
        _view_req(
            "post",
            {
                "action": "winback",
                "enabled": "1",
                "inactive_days": "45",
                "discount_percent": "20",
                "valid_days": "21",
                "subject": "Kommen Sie wieder",
            },
        )
    )
    wb = CouponCampaign.objects.get(kind=CouponCampaign.KIND_AUTO_WINBACK)
    assert wb.status == CouponCampaign.STATUS_ACTIVE
    assert wb.inactive_days == 45 and wb.discount_percent == 20 and wb.valid_days == 21

    # повторный save без enabled → пауза, второй синглтон не создаётся
    coupon_campaigns(
        _view_req(
            "post",
            {
                "action": "winback",
                "inactive_days": "45",
                "discount_percent": "20",
                "valid_days": "21",
            },
        )
    )
    assert CouponCampaign.objects.filter(kind=CouponCampaign.KIND_AUTO_WINBACK).count() == 1
    wb.refresh_from_db()
    assert wb.status == CouponCampaign.STATUS_PAUSED


# ---------------------------------------------------------------------------
# B4.4: авто-win-back beat
# ---------------------------------------------------------------------------


def _winback(**kw):
    defaults = dict(
        kind=CouponCampaign.KIND_AUTO_WINBACK,
        status=CouponCampaign.STATUS_ACTIVE,
        name="Auto Win-back",
        subject="Wir vermissen Sie",
        inactive_days=60,
        discount_percent=10,
        valid_days=30,
    )
    defaults.update(kw)
    return CouponCampaign.objects.create(**defaults)


def test_winback_sends_once_per_window():
    lost = _customer("lost@test.de")
    _purchase(lost, days_ago=90)
    _winback()

    assert tasks.send_due_winback_coupons(base_url=_BASE) == 1
    assert Voucher.objects.filter(customer=lost).count() == 1
    # второй прогон в том же окне — тишина
    assert tasks.send_due_winback_coupons(base_url=_BASE) == 0
    assert Voucher.objects.filter(customer=lost).count() == 1
    assert Notification.objects.filter(type="coupon_campaign").count() == 1


def test_winback_paused_or_recent_buyer_is_silent():
    lost = _customer("lost@test.de")
    _purchase(lost, days_ago=90)
    _winback(status=CouponCampaign.STATUS_PAUSED)
    assert tasks.send_due_winback_coupons(base_url=_BASE) == 0

    fresh = _customer("fresh@test.de")
    _purchase(fresh, days_ago=3)
    CouponCampaign.objects.all().delete()
    _winback()
    n = tasks.send_due_winback_coupons(base_url=_BASE)
    assert n == 1  # только lost; fresh покупал недавно
    assert not Voucher.objects.filter(customer=fresh).exists()
