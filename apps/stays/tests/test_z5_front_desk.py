"""KA-12 Zimmer Z-5c: стойка — авто-скидки, комната, оплата, блок, правила продаж, next.

План docs/ka-12-w4-z5-front-desk-heute-plan-2026-10-25.md Р-1…Р-4 + §9. Замки:
без сентинела форма ведёт себя как до Z-5; выключенные авто-скидки не трогают ваучер
и не списывают лимит акции; комната — строго своей категории, занятая — откат всей
брони; способ оплаты — белый список стойки; блок — только через сервис."""

import uuid
from datetime import timedelta

import pytest
from django.contrib.auth import get_user_model
from django.contrib.messages import get_messages
from django.contrib.messages.middleware import MessageMiddleware
from django.contrib.sessions.middleware import SessionMiddleware
from django.test import RequestFactory
from django.utils import timezone

from apps.core.models import Membership
from apps.promotions.models import Customer, Promotion
from apps.promotions.tests.factories import PromotionFactory
from apps.stays import views
from apps.stays.models import NightRate, Room, StayBooking, StaySettings, StayUnit, UnitBlock
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db

D0 = timezone.localdate() + timedelta(days=20)


@pytest.fixture(autouse=True)
def _urlconf(settings):
    settings.ROOT_URLCONF = "config.urls_tenant"


def _unit(quantity=2, **kw):
    kw.setdefault("price_cents", 10000)
    return StayUnit.objects.create(name=f"DZ {uuid.uuid4().hex[:6]}", quantity=quantity, **kw)


def _user():
    tag = uuid.uuid4().hex[:8]
    user = get_user_model().objects.create_user(
        username=f"u-{tag}", email=f"u-{tag}@test.de", password="pw12345678"
    )
    Membership.objects.get_or_create(user=user, defaults={"role": Membership.ROLE_OWNER})
    return user


def _desk(unit, extra=None, *, nights=2, tenant=None):
    data = {
        "unit": str(unit.pk),
        "arrival": D0.isoformat(),
        "departure": (D0 + timedelta(days=nights)).isoformat(),
        "name": "Walk-in Gast",
        "erw": "2",
        **(extra or {}),
    }
    request = RequestFactory().post("/dashboard/stays/new/", data)
    SessionMiddleware(lambda r: None).process_request(request)
    MessageMiddleware(lambda r: None).process_request(request)
    request.user = _user()
    request.tenant = tenant or TenantFactory.build(disabled_modules=[])
    response = views.stay_create(request)
    return [str(m) for m in get_messages(request)], response


def _los(percent=10):
    s = StaySettings.load()
    s.auto_discount_rules = [{"kind": "los", "threshold": 2, "percent": percent}]
    s.save()


def _stay_promo(unit, percent=50, quantity=5):
    promo = PromotionFactory(product=None, available_quantity=quantity)
    Promotion.objects.filter(pk=promo.pk).update(
        status="active", stay_unit=unit, discount_percent=percent, target_rules={}
    )
    promo.refresh_from_db()
    return promo


# --- Р-1 авто-скидки ----------------------------------------------------------------


def test_without_sentinel_auto_discount_applies_as_before():
    unit = _unit()
    _los(10)
    _desk(unit)
    b = StayBooking.objects.get()
    assert b.auto_discount_cents == 2000 and b.total_cents == 18000


def test_unchecked_toggle_skips_auto_discount_and_promo_limit():
    unit = _unit()
    _los(10)
    promo = _stay_promo(unit, percent=50, quantity=5)
    _desk(unit, {"auto_rabatt_present": "1"})
    b = StayBooking.objects.get()
    assert (b.auto_discount_cents, b.auto_discount_label) == (0, "")
    assert b.total_cents == 20000 and b.promotion_id is None
    promo.refresh_from_db()
    assert promo.available_quantity == 5


def test_checked_toggle_applies_auto_discount():
    unit = _unit()
    _los(10)
    _desk(unit, {"auto_rabatt_present": "1", "auto_rabatt": "1"})
    assert StayBooking.objects.get().auto_discount_cents == 2000


def test_voucher_still_applies_when_toggle_off():
    from apps.loyalty.models import Voucher

    unit = _unit()
    Voucher.objects.create(code="DESK10", label="-10%", discount_percent=10, max_uses=0)
    _desk(unit, {"auto_rabatt_present": "1", "voucher_code": "DESK10"})
    b = StayBooking.objects.get()
    assert b.voucher_code == "DESK10" and b.discount_cents == 2000


# --- Р-2 комната ----------------------------------------------------------------------


def test_free_room_is_assigned():
    unit = _unit()
    room = Room.objects.create(unit=unit, number="101")
    _desk(unit, {"room": str(room.pk)})
    assert StayBooking.objects.get().room_id == room.pk


def test_occupied_room_rolls_back_whole_booking():
    unit = _unit(quantity=2)
    r101 = Room.objects.create(unit=unit, number="101")
    Room.objects.create(unit=unit, number="102")
    _desk(unit, {"room": str(r101.pk)})
    customers = Customer.objects.count()
    promo = _stay_promo(unit, quantity=5)
    msgs, _resp = _desk(unit, {"room": str(r101.pk), "email": "neu@t.de", "name": "Neu"})
    assert StayBooking.objects.count() == 1
    assert Customer.objects.count() == customers
    promo.refresh_from_db()
    assert promo.available_quantity == 5
    assert any("belegt" in m for m in msgs)


@pytest.mark.parametrize("raw", ["foreign", "garbage", "1 OR 1", "x" * 80])
def test_room_of_other_category_or_garbage_refused(raw):
    unit, other = _unit(), _unit()
    foreign = Room.objects.create(unit=other, number="201")
    value = str(foreign.pk) if raw == "foreign" else raw
    msgs, response = _desk(unit, {"room": value})
    assert response.status_code == 302
    assert not StayBooking.objects.exists()
    assert any("Kategorie" in m for m in msgs)


def test_room_with_several_rooms_refused():
    unit = _unit(quantity=3)
    room = Room.objects.create(unit=unit, number="101")
    msgs, _resp = _desk(unit, {"room": str(room.pk), "rooms": "2"})
    assert not StayBooking.objects.exists()
    assert any("Mehrere Zimmer" in m for m in msgs)


def test_garbage_unit_is_404_not_500():
    from django.http import Http404

    request = RequestFactory().post("/dashboard/stays/new/", {"unit": "1 OR 1"})
    request.user = _user()
    with pytest.raises(Http404):
        views.stay_create(request)


# --- Р-3 оплата -----------------------------------------------------------------------


def test_vorkasse_with_iban_kept_without_hold_deadline():
    unit = _unit()
    tenant = TenantFactory.build(disabled_modules=[], bank_iban="DE89370400440532013000")
    _desk(unit, {"payment_method": "vorkasse"}, tenant=tenant)
    b = StayBooking.objects.get()
    assert b.payment_method == "vorkasse" and b.payment_due_at is None


@pytest.mark.parametrize("raw", ["vorkasse", "stripe", "invoice", "xx"])
def test_other_methods_fall_back_to_on_site_without_invoice(raw):
    from apps.finance.models import Invoice

    unit = _unit()
    _desk(unit, {"payment_method": raw})  # тенант без IBAN → Vorkasse тоже нет
    b = StayBooking.objects.get()
    assert b.payment_method == "on_site"
    assert not Invoice.objects.exists()


# --- Р-4 блок -------------------------------------------------------------------------


def test_block_on_sold_out_nights_refused():
    unit = _unit(quantity=1)
    _desk(unit)
    msgs, _resp = _desk(unit, {"mode": "block", "name": "Wartung"})
    assert not UnitBlock.objects.exists()
    assert any("Überbuchung" in m for m in msgs)


def test_block_with_room_and_conflict():
    unit = _unit(quantity=2)
    r101 = Room.objects.create(unit=unit, number="101")
    r102 = Room.objects.create(unit=unit, number="102")
    _desk(unit, {"mode": "block", "room": str(r102.pk)})
    assert UnitBlock.objects.get().room_id == r102.pk
    _desk(unit, {"room": str(r101.pk)}, nights=2)
    UnitBlock.objects.all().delete()
    msgs, _resp = _desk(unit, {"mode": "block", "room": str(r101.pk)})
    assert not UnitBlock.objects.exists()
    assert any("Gast" in m for m in msgs)


def test_block_with_reversed_dates_refused():
    unit = _unit()
    request = RequestFactory().post(
        "/dashboard/stays/new/",
        {
            "unit": str(unit.pk),
            "arrival": D0.isoformat(),
            "departure": D0.isoformat(),
            "mode": "block",
        },
    )
    SessionMiddleware(lambda r: None).process_request(request)
    MessageMiddleware(lambda r: None).process_request(request)
    request.user = _user()
    views.stay_create(request)
    assert not UnitBlock.objects.exists()
    assert len(list(get_messages(request))) == 1  # «Invalid dates.» (на языке кабинета)


# --- О-2 правила продаж ---------------------------------------------------------------


def test_stop_sell_night_books_with_warning():
    unit = _unit()
    NightRate.objects.create(unit=unit, day=D0, stop_sell=True)
    msgs, _resp = _desk(unit)
    assert StayBooking.objects.count() == 1
    assert any("Verkaufsregel" in m for m in msgs)


def test_no_warning_without_rule_violation():
    msgs, _resp = _desk(_unit())
    assert not any("Verkaufsregel" in m for m in msgs)


# --- next -----------------------------------------------------------------------------


@pytest.mark.parametrize(
    "nxt", ["//evil.com", "/\\evil.com", "/\t/evil.com", "https://evil.com", "///evil.com"]
)
def test_unsafe_next_falls_back_to_calendar(nxt):
    unit = _unit()
    _msgs, response = _desk(unit, {"next": nxt})
    assert "evil" not in response["Location"]


def test_local_next_kept():
    _msgs, response = _desk(_unit(), {"next": "/dashboard/verkaeufe/?tab=stay"})
    assert response["Location"] == "/dashboard/verkaeufe/?tab=stay"


def test_stay_action_unsafe_next():
    unit = _unit()
    _desk(unit)
    b = StayBooking.objects.get()
    request = RequestFactory().post(
        f"/dashboard/stays/{b.pk}/action/", {"action": "nope", "next": "/\\evil.com"}
    )
    SessionMiddleware(lambda r: None).process_request(request)
    MessageMiddleware(lambda r: None).process_request(request)
    request.user = _user()
    request.tenant = TenantFactory.build(disabled_modules=[])
    response = views.stay_action(request, b.pk)
    assert "evil" not in response["Location"]


def test_walkin_form_shows_rooms_with_category_and_toggle():
    unit = _unit()
    room = Room.objects.create(unit=unit, number="101")
    request = RequestFactory().get("/dashboard/stays/new/")
    request.user = _user()
    request.tenant = TenantFactory.build(disabled_modules=[])
    body = views.stay_new(request).content.decode()
    assert f'value="{room.pk}" data-unit="{unit.pk}"' in body
    assert 'name="auto_rabatt_present"' in body and 'name="auto_rabatt" value="1" checked' in body
    assert 'value="vorkasse"' not in body  # без IBAN
