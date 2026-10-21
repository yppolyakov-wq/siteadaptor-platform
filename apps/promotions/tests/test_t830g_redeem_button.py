"""T-8.30g: погашение у прилавка меняет состояние ТОЛЬКО по POST.

GET (камера телефона, превью ссылки, перезагрузка, prefetch) показывает большую кнопку
подтверждения. Настройка «Sofort einlösen» значит: встроенный сканер гасит сразу —
в самом POST сканера. План — docs/t8-30g-redeem-button-plan-2026-10-21.md.
"""

from pathlib import Path

import pytest

from apps.loyalty.models import Voucher
from apps.promotions import services, views
from apps.promotions.models import Reservation
from apps.promotions.tests.factories import PromotionFactory
from apps.promotions.tests.test_t830e_counter import _req, _tenant

pytestmark = pytest.mark.django_db
TPL = Path(__file__).resolve().parents[3] / "templates" / "promotions"


@pytest.fixture
def user(db):
    from django.contrib.auth import get_user_model

    from apps.core.models import Membership

    u = get_user_model().objects.create_user(username="kasse-g", password="pw12345678")
    Membership.objects.create(user=u, role=Membership.ROLE_OWNER)
    return u


def _tenant_auto(auto=True):
    t = _tenant()
    t.auto_redeem_on_scan = auto
    t.save()
    return t


def _res():
    promo = PromotionFactory(status="active", title={"de": "Brot"}, available_quantity=5)
    return services.reserve(promo, name="Anna", email="anna@test.de")


def test_get_changes_nothing_for_coupon_reservation_voucher(user):
    t = _tenant_auto()
    res = _res()
    coupon = Voucher.objects.create(code="C-GET001", label="x", max_uses=1, promotion=res.promotion)
    voucher = Voucher.objects.create(code="V-GET001", label="Kaffee", max_uses=1)
    views.redeem_detail(_req("get", "/", user, t), res.reference_code)
    views.redeem_detail(_req("get", "/", user, t), coupon.code)
    views.voucher_redeem(_req("get", f"/?code={voucher.code}", user, t))
    assert Reservation.objects.get(pk=res.pk).status == "pending"
    coupon.refresh_from_db()
    voucher.refresh_from_db()
    assert coupon.used_count == 0 and voucher.used_count == 0


@pytest.mark.parametrize("auto", [True, False])
def test_scanner_post_redeems_only_with_setting(user, auto):
    t = _tenant_auto(auto)
    res = _res()
    coupon = Voucher.objects.create(code="C-SCN001", label="x", max_uses=1, promotion=res.promotion)
    voucher = Voucher.objects.create(code="V-SCN001", label="Kaffee", max_uses=1)
    for code, kind in ((res.reference_code, ""), (coupon.code, ""), (voucher.code, "voucher")):
        data = {"code": code, "scan": "1"}
        if kind:
            data["kind"] = kind
        resp = views.redeem_home(_req("post", "/promotions/redeem/", user, t, data))
        assert resp.status_code == 302
    coupon.refresh_from_db()
    voucher.refresh_from_db()
    expected = 1 if auto else 0
    assert (Reservation.objects.get(pk=res.pk).status == "fulfilled") is auto
    assert coupon.used_count == expected and voucher.used_count == expected


def test_voucher_scan_redirects_to_its_confirm_page(user):
    t = _tenant_auto(False)
    Voucher.objects.create(code="V-RDR001", label="Kaffee", max_uses=1)
    resp = views.redeem_home(
        _req("post", "/", user, t, {"code": "V-RDR001", "scan": "1", "kind": "voucher"})
    )
    assert "code=V-RDR001" in resp["Location"]


def test_double_fulfill_is_info_not_error(user):
    t = _tenant_auto(False)
    res = _res()
    code = res.reference_code
    views.redeem_action(_req("post", "/", user, t, {"action": "fulfill"}), code)
    assert Reservation.objects.get(pk=res.pk).status == "fulfilled"
    req = _req("post", "/", user, t, {"action": "fulfill"})
    views.redeem_action(req, code)
    levels = [m.level_tag for m in req._messages]
    assert "error" not in levels and "info" in levels


def test_voucher_double_post_with_same_expect_counts_once(user):
    t = _tenant_auto(False)
    v = Voucher.objects.create(code="V-DBL001", label="Kaffee", max_uses=5)
    for _ in range(2):
        views.voucher_redeem(_req("post", "/", user, t, {"code": v.code, "expect": "0"}))
    v.refresh_from_db()
    assert v.used_count == 1


def test_voucher_manual_post_without_expect_still_works(user):
    t = _tenant_auto(False)
    v = Voucher.objects.create(code="V-MAN001", label="Kaffee", max_uses=5)
    views.voucher_redeem(_req("post", "/", user, t, {"code": v.code}))
    views.voucher_redeem(_req("post", "/", user, t, {"code": v.code}))
    v.refresh_from_db()
    assert v.used_count == 2


def test_confirm_page_primary_button_is_focused_and_once(user):
    t = _tenant_auto()
    res = _res()
    body = views.redeem_detail(_req("get", "/", user, t), res.reference_code).content.decode()
    assert "data-redeem-primary" in body and "autofocus" in body and "data-once" in body
    v = Voucher.objects.create(code="V-BTN001", label="Kaffee", max_uses=1)
    body = views.voucher_redeem(_req("get", f"/?code={v.code}", user, t)).content.decode()
    assert "data-redeem-primary" in body and 'name="expect"' in body


def test_no_scanner_navigates_by_get_to_voucher_page():
    for name in ("redeem.html", "voucher_redeem.html"):
        src = (TPL / name).read_text()
        assert "location.href = voucherPrefix" not in src
        assert 'location.href = "?code="' not in src


def test_setting_help_no_longer_promises_redeem_on_open():
    from apps.tenants import forms

    src = Path(forms.__file__).read_text()
    assert "opening a redemption QR" not in src
