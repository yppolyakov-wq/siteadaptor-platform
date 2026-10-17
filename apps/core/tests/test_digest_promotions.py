"""Г4-2: недельный блок «Ihre Aktionen letzte Woche» в утреннем дайджесте владельцу.

План — docs/g3-g4-freshness-digest-plan-2026-10-17.md §4.3. Только агрегаты, без
персональных данных; блок только по понедельникам; пустая неделя — без блока.
"""

from datetime import timedelta
from unittest import mock

import pytest
from django.utils import timezone

from apps.core import digest, tasks
from apps.loyalty.models import Voucher
from apps.notifications.models import Notification
from apps.promotions.models import Customer, PromotionDailyView, Reservation
from apps.promotions.tests.factories import PromotionFactory
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db

SECRET_EMAIL = "geheim-kunde-4711@test.de"
SECRET_NAME = "Wilhelmina Zuckerbrot"


def _tenant(**kw):
    kw.setdefault("owner_email", "chef@test.de")
    return TenantFactory(**kw)


def _days_ago(n):
    return timezone.now() - timedelta(days=n)


def _promo(title="Brötchen-Woche", **kw):
    kw.setdefault("status", "active")
    kw.setdefault("ends_at", timezone.now() + timedelta(days=3))
    return PromotionFactory(title={"de": title}, **kw)


def _views(promo, days_ago, n):
    PromotionDailyView.objects.create(
        promotion=promo, day=timezone.localdate() - timedelta(days=days_ago), views=n
    )


def _reservation(promo, *, status="pending", created_days_ago=2, fulfilled_days_ago=None):
    customer, _ = Customer.objects.get_or_create(
        email=SECRET_EMAIL, defaults={"name": SECRET_NAME, "phone": "+49 151 99999999"}
    )
    import uuid

    r = Reservation.objects.create(
        promotion=promo,
        customer=customer,
        status=status,
        reference_code="R-" + uuid.uuid4().hex[:8].upper(),
    )
    Reservation.objects.filter(pk=r.pk).update(
        created_at=_days_ago(created_days_ago),
        fulfilled_at=_days_ago(fulfilled_days_ago) if fulfilled_days_ago is not None else None,
    )
    return r


def _week(tenant):
    data = digest.collect_digest(tenant, weekly=True)
    return (data or {}).get("promo_week")


def test_views_count_only_inside_the_week():
    tenant = _tenant()
    promo = _promo()
    _views(promo, 1, 2)
    _views(promo, 6, 1)
    _views(promo, 9, 50)  # вне окна
    _views(promo, 0, 40)  # сегодня — ещё не «прошлая неделя»
    assert _week(tenant)["views"] == 3


def test_held_and_handed_follow_status_and_dates():
    tenant = _tenant()
    promo = _promo()
    _reservation(promo, status="pending")
    _reservation(promo, status="cancelled")  # не считается
    _reservation(promo, status="expired")  # не считается
    _reservation(promo, status="fulfilled", created_days_ago=20, fulfilled_days_ago=1)
    week = _week(tenant)
    assert week["held"] == 1  # созданный до окна и выданный в окне — не «отложено»
    assert week["handed"] == 1


def test_coupons_issued_and_redeemed_in_window():
    from apps.promotions import services

    tenant = _tenant()
    promo = _promo()
    Voucher.objects.create(code="C-WEEK1", promotion=promo, max_uses=1)
    Voucher.objects.create(code="C-WEEK2", promotion=promo, max_uses=1)
    old = Voucher.objects.create(code="C-OLD1", promotion=promo, max_uses=1)
    Voucher.objects.filter(pk=old.pk).update(created_at=_days_ago(30))
    Voucher.objects.create(code="PROMO10", max_uses=0)  # промокод без акции — не купон акции
    # Окно — прошлая неделя без сегодняшнего дня: «вчера» — выдача и погашение.
    Voucher.objects.filter(code__in=["C-WEEK1", "C-WEEK2"]).update(created_at=_days_ago(1))
    services.redeem_voucher("C-WEEK1")
    Voucher.objects.filter(code="C-WEEK1").update(updated_at=_days_ago(1))
    week = _week(tenant)
    assert week["coupons"] == 2 and week["coupons_redeemed"] == 1


def test_empty_week_has_no_block():
    tenant = _tenant()
    _promo()
    _views(_promo(title="Alt"), 20, 99)
    assert _week(tenant) is None


def test_not_monday_no_block():
    tenant = _tenant()
    promo = _promo()
    _views(promo, 1, 5)
    data = digest.collect_digest(tenant)  # weekly=False — обычный день
    assert data is None or "promo_week" not in data


def test_module_off_or_error_no_block():
    promo = _promo()
    _views(promo, 1, 5)
    off = _tenant(disabled_modules=["promotions"])
    assert _week(off) is None
    tenant = _tenant()
    with mock.patch.object(digest, "_promo_week", side_effect=RuntimeError("boom")):
        data = digest.collect_digest(tenant, weekly=True)
    assert data is None or "promo_week" not in data


def test_monday_mail_goes_out_on_otherwise_empty_day():
    tenant = _tenant()
    promo = _promo()
    _views(promo, 2, 4)
    with mock.patch.object(tasks, "_is_digest_monday", return_value=True):
        assert tasks.send_digest_for_tenant(tenant, force_hour=True) is True
    body = Notification.objects.get(type="owner_digest").payload["body"]
    assert "Ihre Aktionen letzte Woche" in body


def test_mail_has_no_personal_data_and_no_prices():
    tenant = _tenant()
    promo = _promo(title="Mystery-Tüte")
    r = _reservation(promo, status="pending")
    _views(promo, 1, 3)
    with mock.patch.object(tasks, "_is_digest_monday", return_value=True):
        tasks.send_digest_for_tenant(tenant, force_hour=True)
    body = Notification.objects.get(type="owner_digest").payload["body"]
    assert "Mystery-Tüte" in body
    for secret in (SECRET_EMAIL, SECRET_NAME, "99999999", r.reference_code):
        assert secret not in body
    block = body.split("Ihre Aktionen letzte Woche", 1)[1]
    assert "€" not in block


def test_top3_ordered_by_week_views_without_n_plus_one(django_assert_max_num_queries):
    _tenant()
    for i, n in enumerate((5, 50, 1, 20, 9)):
        _views(_promo(title=f"Aktion {i}"), 1, n)
    with django_assert_max_num_queries(7):  # 5 агрегатов + топ + заголовки, без N+1
        week = digest._promo_week(timezone.localdate())
    assert [t["title"] for t in week["top"]] == ["Aktion 1", "Aktion 3", "Aktion 4"]


def test_digest_renders_in_business_language():

    from django.utils import translation

    tenant = _tenant(default_locale="ru", enabled_locales=["de", "ru"])
    promo = _promo()
    _views(promo, 1, 3)
    seen = []
    real = translation.override

    def spy(lang, *a, **kw):
        seen.append(lang)
        return real(lang, *a, **kw)

    with (
        mock.patch.object(tasks, "_is_digest_monday", return_value=True),
        mock.patch.object(translation, "override", side_effect=spy),
    ):
        tasks.send_digest_for_tenant(tenant, force_hour=True)
    assert "ru" in seen
