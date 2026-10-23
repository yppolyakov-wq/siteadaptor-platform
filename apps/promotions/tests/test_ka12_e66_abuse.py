"""KA-12 E6.6: злоупотребление купонами/резервами и гонка лимита 5 акций.

План — docs/ka-12-e6-6-abuse-plan-2026-10-23.md.
"""

import ast
import pathlib
import threading
import uuid
from datetime import timedelta
from importlib import import_module

import pytest
from django.conf import settings as dj_settings
from django.contrib.messages import get_messages
from django.contrib.messages.middleware import MessageMiddleware
from django.db import connection
from django.test import RequestFactory
from django.utils import timezone

from apps.core.contacts import phone_key
from apps.loyalty.models import Voucher
from apps.promotions import limits, public_views, services, tasks
from apps.promotions.models import Promotion, Reservation
from apps.promotions.state_machine import ReservationSM
from apps.promotions.tests.factories import PromotionFactory
from apps.tenants.tests.factories import TenantFactory

ROOT = pathlib.Path(__file__).resolve().parents[3]


def _promo(**kw):
    kw.setdefault("status", "active")
    kw.setdefault("available_quantity", 10)
    kw.setdefault("promo_type", Promotion.DISCOUNT)
    return PromotionFactory(**kw)


def _tenant(slug):
    return TenantFactory(schema_name=slug.replace("-", "_"), slug=slug, name=slug)


def _request(path, tenant, data, ip="10.66.0.1"):
    request = RequestFactory().post(path, data)
    request.session = import_module(dj_settings.SESSION_ENGINE).SessionStore()
    MessageMiddleware(lambda r: None).process_request(request)
    request.tenant = tenant
    request.META["REMOTE_ADDR"] = ip
    return request


def _reserve_post(promo, tenant, ip="10.66.0.1", **data):
    data.setdefault("name", "Anna")
    data.setdefault("quantity", "1")
    data.setdefault("form_token", uuid.uuid4().hex)
    request = _request(f"/p/{promo.pk}/reserve/", tenant, data, ip=ip)
    resp = public_views.reservation_create(request, pk=promo.pk)
    resp.messages = [str(m) for m in get_messages(request)]
    return resp


# --- L10: лимит активных акций -------------------------------------------------------


@pytest.mark.django_db(transaction=True)
def test_parallel_activation_never_exceeds_limit(monkeypatch):
    monkeypatch.setattr(limits, "active_limit", lambda tenant: 2)
    _promo(available_quantity=None)
    candidates = [_promo(status="scheduled", available_quantity=None) for _ in range(4)]
    barrier = threading.Barrier(len(candidates))
    results = []

    def worker(promo):
        connection.close()
        barrier.wait()
        try:
            limits.activate(Promotion.objects.get(pk=promo.pk), None)
            results.append(True)
        except limits.ActivationLimit:
            results.append(False)
        finally:
            connection.close()

    threads = [threading.Thread(target=worker, args=(p,)) for p in candidates]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert Promotion.objects.filter(status="active").count() == 2
    assert results.count(True) == 1


@pytest.mark.django_db
def test_try_activate_returns_false_on_full_limit(monkeypatch):
    monkeypatch.setattr(limits, "active_limit", lambda tenant: 1)
    _promo(available_quantity=None)
    waiting = _promo(status="scheduled", available_quantity=None)
    assert limits.try_activate(waiting, None) is False
    waiting.refresh_from_db()
    assert waiting.status == "scheduled"


@pytest.mark.django_db
def test_beat_respects_limit_through_locked_path(monkeypatch):
    monkeypatch.setattr(limits, "active_limit", lambda tenant: 1)
    _promo(available_quantity=None)
    due = _promo(
        status="scheduled",
        available_quantity=None,
        starts_at=timezone.now() - timedelta(minutes=1),
    )
    called = []
    real = limits.try_activate
    monkeypatch.setattr(limits, "try_activate", lambda *a, **k: called.append(1) or real(*a, **k))
    tasks.roll_due_promotions()
    due.refresh_from_db()
    assert due.status == "scheduled" and called


@pytest.mark.django_db
def test_unlimited_tenant_takes_no_lock(monkeypatch):
    monkeypatch.setattr(limits, "active_limit", lambda tenant: None)

    def boom():
        raise AssertionError("lock taken without a limit")

    monkeypatch.setattr(limits, "_limit_lock", boom)
    promo = _promo(status="scheduled", available_quantity=None)
    limits.activate(promo, None)
    assert Promotion.objects.get(pk=promo.pk).status == "active"


def test_no_direct_activation_outside_limits():
    """Скан: переход акции в "active" — только через limits (кроме тестов/демо)."""
    offenders = []
    for path in (ROOT / "apps").rglob("*.py"):
        rel = path.relative_to(ROOT).as_posix()
        if "/tests/" in rel or "demo" in rel or rel.endswith("promotions/limits.py"):
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and node.func.attr == "apply"
                and len(node.args) >= 2
                and isinstance(node.args[1], ast.Constant)
                and node.args[1].value == "active"
                and "Promotion" in ast.unparse(node.func.value) + rel
                and "promotions" in rel
            ):
                offenders.append(f"{rel}:{node.lineno}")
    assert offenders == []


# --- телефон --------------------------------------------------------------------------


def test_phone_key_normalizes_dach_formats():
    assert phone_key("+49 171 1234567") == phone_key("0171/1234567") == "491711234567"
    assert phone_key("0049 171 1234567") == "491711234567"
    assert phone_key("") == ""
    assert phone_key("+49 (0)171 1234567") == "491711234567"
    assert phone_key("0") == phone_key("12") == ""  # не номер — не сравниваем


@pytest.mark.django_db
def test_short_stored_phone_is_found_by_other_format():
    from apps.core.contacts import find_by_phone
    from apps.promotions.models import Customer

    stored = Customer.objects.create(name="K", phone="0171 123456")
    Customer.objects.create(name="Fremd", phone="0160 123456")  # тот же хвост
    assert find_by_phone(Customer.objects.all(), "+49 171123456") == [stored]
    assert find_by_phone(Customer.objects.all(), "0") == []


@pytest.mark.django_db
def test_same_phone_in_other_format_hits_limit_per_customer():
    promo = _promo(max_per_customer=1)
    services.reserve(promo, name="A", phone="+49 171 1234567")
    with pytest.raises(services.ReservationLimitReached):
        services.reserve(promo, name="A", phone="0171 1234567")


# --- купон без гонки ------------------------------------------------------------------


@pytest.mark.django_db(transaction=True)
def test_parallel_coupon_same_email_issues_one():
    promo = _promo(available_quantity=5, metadata={"response": "coupon"})
    barrier = threading.Barrier(4)

    def worker():
        connection.close()
        barrier.wait()
        try:
            services.issue_coupon(promo, email="anna@example.com")
        except services.CouponExists:
            pass
        finally:
            connection.close()

    threads = [threading.Thread(target=worker) for _ in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert Voucher.objects.filter(promotion=promo).count() == 1
    promo.refresh_from_db()
    assert promo.available_quantity == 4


# --- резерв: короткий срок неподтверждённого ------------------------------------------


@pytest.mark.django_db
def test_pending_hold_is_short_and_confirm_extends(settings):
    settings.PROMO_PENDING_HOLD_HOURS = 4
    promo = _promo(reservation_ttl_hours=24, auto_confirm=False, ends_at=None)
    res = services.reserve(promo, name="A", email="a@example.com")
    assert res.status == "pending"
    assert res.expires_at <= timezone.now() + timedelta(hours=4, minutes=1)
    ReservationSM().apply(res, "confirmed")
    res.refresh_from_db()
    assert res.expires_at >= res.created_at + timedelta(hours=23, minutes=59)


@pytest.mark.django_db
def test_confirm_extension_never_beyond_promotion_end(settings):
    settings.PROMO_PENDING_HOLD_HOURS = 1
    ends = timezone.now() + timedelta(hours=6)
    promo = _promo(reservation_ttl_hours=24, auto_confirm=False, ends_at=ends)
    res = services.reserve(promo, name="A", email="b@example.com")
    ReservationSM().apply(res, "confirmed")
    res.refresh_from_db()
    assert res.expires_at == ends


@pytest.mark.django_db
def test_auto_confirm_gets_full_ttl_right_away(settings):
    settings.PROMO_PENDING_HOLD_HOURS = 1
    promo = _promo(reservation_ttl_hours=24, auto_confirm=True, ends_at=None)
    res = services.reserve(promo, name="A", email="c@example.com")
    assert res.expires_at > timezone.now() + timedelta(hours=23)


# --- потолки на витрине ---------------------------------------------------------------


@pytest.mark.django_db
def test_unconfirmed_reservations_per_contact_cap(settings, isolated_ratelimit):
    isolated_ratelimit.clear()  # LocMem с тем же именем общий между тестами
    settings.PROMO_OPEN_RESERVATIONS_PER_CONTACT = 2
    tenant = _tenant("e66-open")
    promos = [_promo(auto_confirm=False) for _ in range(3)]
    for p in promos[:2]:
        assert _reserve_post(p, tenant, email="d@example.com").status_code == 302
    resp = _reserve_post(promos[2], tenant, email="D@example.com")
    assert resp.status_code == 200 and Reservation.objects.count() == 2
    assert resp.messages == ["Zu viele Versuche. Bitte später erneut."]  # без оракула
    services.confirm(Reservation.objects.first())  # подтверждённое не держит потолок
    assert _reserve_post(promos[2], tenant, email="d@example.com").status_code == 302


@pytest.mark.django_db(transaction=True)
def test_contact_cap_holds_under_parallel_posts():
    promos = [_promo(auto_confirm=False) for _ in range(5)]
    barrier = threading.Barrier(len(promos))

    def worker(promo):
        connection.close()
        barrier.wait()
        try:
            services.reserve(promo, name="A", email="p@example.com", open_cap=2)
        except services.ContactHoldLimit:
            pass
        finally:
            connection.close()

    threads = [threading.Thread(target=worker, args=(p,)) for p in promos]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert Reservation.objects.count() == 2


@pytest.mark.django_db(transaction=True)
def test_activate_outside_transaction_releases_lock(monkeypatch):
    """Вне транзакции — сессионная блокировка: статус коммитится до задач on_transition,
    и блокировка отпускается."""
    monkeypatch.setattr(limits, "active_limit", lambda tenant: 3)
    promo = _promo(status="scheduled", available_quantity=None)
    limits.activate(promo, None)
    with connection.cursor() as cur:
        cur.execute(
            "SELECT count(*) FROM pg_locks WHERE locktype = 'advisory' AND pid = pg_backend_pid()"
        )
        assert cur.fetchone()[0] == 0
    assert Promotion.objects.get(pk=promo.pk).status == "active"


@pytest.mark.django_db
def test_reservations_per_ip_per_day_cap(settings, isolated_ratelimit):
    isolated_ratelimit.clear()  # LocMem с тем же именем общий между тестами
    settings.PROMO_RESERVATIONS_PER_IP_DAY = 2
    tenant = _tenant("e66-day")
    for i in range(2):
        assert _reserve_post(_promo(), tenant, email=f"x{i}@example.com").status_code == 302
    resp = _reserve_post(_promo(), tenant, email="x9@example.com")
    assert resp.status_code == 200 and Reservation.objects.count() == 2
    assert any("Zu viele" in m for m in resp.messages)


@pytest.mark.django_db
def test_sold_out_does_not_consume_daily_cap(settings, isolated_ratelimit):
    isolated_ratelimit.clear()  # LocMem с тем же именем общий между тестами
    settings.PROMO_RESERVATIONS_PER_IP_DAY = 1
    tenant = _tenant("e66-refund")
    sold = _promo(available_quantity=0)
    first = _reserve_post(sold, tenant, email="y@example.com")
    assert first.status_code == 200, first.messages
    assert first.messages == ["Leider ausverkauft."], first.messages
    resp = _reserve_post(_promo(), tenant, email="y@example.com")
    assert resp.status_code == 302, resp.messages


def _coupon_post(promo, tenant, ip="10.66.1.1", **data):
    return public_views.coupon_create(
        _request(f"/p/{promo.pk}/coupon/", tenant, data, ip=ip), pk=promo.pk
    )


@pytest.mark.django_db
def test_limited_coupon_daily_cap_per_ip(settings, isolated_ratelimit):
    isolated_ratelimit.clear()  # LocMem с тем же именем общий между тестами
    settings.PROMO_COUPONS_PER_IP_DAY = 2
    tenant = _tenant("e66-coupon")
    promo = _promo(available_quantity=10, metadata={"response": "coupon"})
    for i in range(2):
        _coupon_post(promo, tenant, email=f"c{i}@example.com")
    _coupon_post(promo, tenant, email="c9@example.com")
    assert Voucher.objects.filter(promotion=promo).count() == 2


@pytest.mark.django_db
def test_unlimited_coupon_has_no_daily_cap(settings, isolated_ratelimit):
    isolated_ratelimit.clear()  # LocMem с тем же именем общий между тестами
    settings.PROMO_COUPONS_PER_IP_DAY = 1
    tenant = _tenant("e66-coupon-free")
    promo = _promo(available_quantity=None, metadata={"response": "coupon"})
    for i in range(3):
        _coupon_post(promo, tenant, email=f"u{i}@example.com")
    assert Voucher.objects.filter(promotion=promo).count() == 3


@pytest.mark.django_db
def test_coupon_by_email_never_reveals_code(isolated_ratelimit, monkeypatch):
    isolated_ratelimit.clear()  # LocMem с тем же именем общий между тестами
    tenant = _tenant("e66-mail")
    promo = _promo(metadata={"response": "coupon", "coupon_delivery": "email"})
    sent = []
    monkeypatch.setattr(
        "apps.promotions.notifications.send_coupon_email",
        lambda voucher, promo, email, **kw: sent.append((voucher.code, email)),
    )
    no_mail = _coupon_post(promo, tenant)
    assert no_mail.status_code == 302 and not Voucher.objects.exists()
    resp = _coupon_post(promo, tenant, email="m@example.com")
    voucher = Voucher.objects.get(promotion=promo)
    assert resp.url == f"/p/{promo.pk}/"
    assert voucher.code not in resp.url
    assert public_views.COUPON_COOKIE not in resp.cookies
    assert sent == [(voucher.code, "m@example.com")]
    again = public_views.coupon_create(
        _request(f"/p/{promo.pk}/coupon/", tenant, {"email": "m@example.com"}, ip="10.66.2.2"),
        pk=promo.pk,
    )
    assert again.url == f"/p/{promo.pk}/"  # тот же ответ: наличие купона не раскрываем


@pytest.mark.django_db
def test_promotion_form_toggles_coupon_by_email():
    from apps.promotions.forms import PromotionForm

    promo = _promo(metadata={"response": "coupon"})
    form = PromotionForm(instance=promo)
    assert "coupon_by_email" in form.fields
    assert form.fields["coupon_by_email"].initial is False
