"""T-8.30e: касса в лёгком кабинете / Mini App (план docs/t8-30e-counter-plan-2026-10-21.md)."""

import time
import uuid

import pytest
from django.contrib.auth import get_user_model
from django.contrib.messages.middleware import MessageMiddleware
from django.contrib.sessions.middleware import SessionMiddleware
from django.test import RequestFactory

from apps.core import tg_login
from apps.core import views as core_views
from apps.core.models import Membership
from apps.promotions import services, views
from apps.promotions.models import Reservation
from apps.promotions.tests.factories import PromotionFactory
from apps.tenants import onboarding
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _urlconf(settings):
    settings.ROOT_URLCONF = "config.urls_tenant"


@pytest.fixture
def user(db):
    u = get_user_model().objects.create_user(username="kasse", password="pw12345678")
    Membership.objects.create(user=u, role=Membership.ROLE_OWNER)
    return u


def _tenant(lite=True):
    slug = f"ks-{uuid.uuid4().hex[:6]}"
    t = TenantFactory(schema_name=slug.replace("-", "_"), slug=slug, name="Krume")
    t.site_config = {"profile": "aktionen"} if lite else {}
    t.save()
    onboarding.mark_complete(t)
    return t


def _req(method, path, user, tenant, data=None, tg=False):
    rf = RequestFactory()
    req = rf.post(path, data or {}) if method == "post" else rf.get(path)
    SessionMiddleware(lambda r: None).process_request(req)
    MessageMiddleware(lambda r: None).process_request(req)
    req.user, req.tenant = user, tenant
    if tg:
        req.COOKIES["sessionid"] = "x"
        req.session[tg_login.SESSION_KEY] = {"uid": 1, "exp": int(time.time()) + 3600}
    return req


def _reservations():
    promo = PromotionFactory(status="active", title={"de": "Brot"}, available_quantity=20)
    a = services.reserve(promo, name="Anna", email="anna@test.de")
    b = services.reserve(promo, name="Bert", email="bert@test.de")
    services.confirm(b)
    c = services.reserve(promo, name="Cleo", email="cleo@test.de")
    services.confirm(c)
    services.fulfill(c)
    d = services.reserve(promo, name="Dora", email="dora@test.de")
    services.cancel(d)
    return promo, a, b, c, d


def test_offen_filter_is_pending_and_confirmed(user):
    _promo, a, b, c, d = _reservations()
    body = views.reservation_list(
        _req("get", "/promotions/reservations/?status=offen", user, _tenant())
    ).content.decode()
    assert a.reference_code in body and b.reference_code in body
    assert c.reference_code not in body and d.reference_code not in body


def test_lite_list_is_cards_full_list_keeps_table(user):
    _reservations()
    lite = views.reservation_list(
        _req("get", "/promotions/reservations/", user, _tenant())
    ).content.decode()
    assert "data-lite-res-card" in lite and "min-w-[640px]" not in lite
    full = views.reservation_list(
        _req("get", "/promotions/reservations/", user, _tenant(lite=False))
    ).content.decode()
    assert "min-w-[640px]" in full and "data-lite-res-card" not in full


@pytest.mark.parametrize("start", ["pending", "confirmed"])
def test_fulfill_from_pending_and_confirmed(user, start):
    promo = PromotionFactory(status="active", title={"de": "Brot"}, available_quantity=5)
    res = services.reserve(promo, name="Anna", email="anna@test.de")
    if start == "confirmed":
        services.confirm(res)
    req = _req(
        "post", f"/promotions/reservations/{res.pk}/action/", user, _tenant(), {"action": "fulfill"}
    )
    views.reservation_action(req, res.pk)
    res.refresh_from_db()
    assert res.status == "fulfilled" and res.fulfilled_at is not None


def test_fulfill_pending_on_redeem_detail(user):
    promo = PromotionFactory(status="active", title={"de": "Brot"}, available_quantity=5)
    res = services.reserve(promo, name="Anna", email="anna@test.de")
    code = res.reference_code
    req = _req("post", f"/promotions/redeem/{code}/action/", user, _tenant(), {"action": "fulfill"})
    views.redeem_action(req, code)
    assert Reservation.objects.get(pk=res.pk).status == "fulfilled"


def test_lite_pending_card_offers_handout_in_one_tap(user):
    """В списке у pending не было «Ausgeben» — продавцу два нажатия (сервис умеет сразу)."""
    import re

    _promo, a, *_rest = _reservations()
    body = views.reservation_list(
        _req("get", "/promotions/reservations/?status=offen", user, _tenant())
    ).content.decode()
    cards = re.findall(r"<article[^>]*data-lite-res-card.*?</article>", body, re.S)
    card = next(c for c in cards if a.reference_code in c)
    fulfill = card.split('value="fulfill"', 1)[0]
    assert f"/promotions/reservations/{a.pk}/action/" in fulfill.rsplit("<form", 1)[1]


def test_lite_chips_keep_promotion_filter(user):
    promo, *_rest = _reservations()
    body = views.reservation_list(
        _req("get", f"/promotions/reservations/?promotion={promo.pk}", user, _tenant())
    ).content.decode()
    assert f"?status=confirmed&amp;promotion={promo.pk}" in body


def test_redeem_home_rejects_garbage_code_without_500(user):
    resp = views.redeem_home(
        _req("post", "/promotions/redeem/", user, _tenant(), {"code": "a/b/../x"})
    )
    assert resp.status_code == 200


def _auto_tenant():
    t = _tenant()
    t.auto_redeem_on_scan = True
    t.save()
    return t


def test_tg_get_link_does_not_auto_redeem(user):
    """Ревью: ссылка на код в 12-часовой Telegram-сессии не должна гасить по GET."""
    promo = PromotionFactory(status="active", title={"de": "Brot"}, available_quantity=5)
    res = services.reserve(promo, name="Anna", email="anna@test.de")
    code = res.reference_code
    views.redeem_detail(
        _req("get", f"/promotions/redeem/{code}/", user, _auto_tenant(), tg=True), code
    )
    assert Reservation.objects.get(pk=res.pk).status == "pending"


def test_tg_scanner_post_permits_auto_redeem(user):
    promo = PromotionFactory(status="active", title={"de": "Brot"}, available_quantity=5)
    res = services.reserve(promo, name="Anna", email="anna@test.de")
    code = res.reference_code
    t = _auto_tenant()
    post = _req("post", "/promotions/redeem/", user, t, {"code": code, "scan": "1"}, tg=True)
    views.redeem_home(post)
    get = _req("get", f"/promotions/redeem/{code}/", user, t, tg=True)
    get.session = post.session
    views.redeem_detail(get, code)
    assert Reservation.objects.get(pk=res.pk).status == "fulfilled"
    # разовый допуск: второй заход по ссылке уже ничего не делает
    assert "redeem_scan_auto" not in get.session


def test_browser_get_still_auto_redeems(user):
    """Прежнее поведение вне Telegram: камера телефона открывает адрес — и гасит."""
    promo = PromotionFactory(status="active", title={"de": "Brot"}, available_quantity=5)
    res = services.reserve(promo, name="Anna", email="anna@test.de")
    code = res.reference_code
    views.redeem_detail(_req("get", f"/promotions/redeem/{code}/", user, _auto_tenant()), code)
    assert Reservation.objects.get(pk=res.pk).status == "fulfilled"


def test_tg_voucher_link_does_not_auto_redeem(user):
    from apps.loyalty.models import Voucher

    v = Voucher.objects.create(code="V-TG0001", label="Kaffee", max_uses=1)
    views.voucher_redeem(
        _req("get", "/promotions/vouchers/redeem/?code=V-TG0001", user, _auto_tenant(), tg=True)
    )
    v.refresh_from_db()
    assert v.used_count == 0


def test_lite_cancel_is_behind_disclosure(user):
    _reservations()
    body = views.reservation_list(
        _req("get", "/promotions/reservations/?status=offen", user, _tenant())
    ).content.decode()
    assert body.count("data-res-cancel") == 2
    for chunk in body.split("data-res-cancel")[:-1]:
        assert chunk.rfind("<details") > chunk.rfind("</details>")


def test_redeem_tg_branch_and_browser_branch(user):
    t = _tenant()
    tg = views.redeem_home(_req("get", "/promotions/redeem/", user, t, tg=True)).content.decode()
    assert "data-tg-scan" in tg and 'name="code"' in tg
    plain = views.redeem_home(_req("get", "/promotions/redeem/", user, t)).content.decode()
    assert "data-tg-scan" not in plain and "scan-toggle" in plain


def test_scanner_never_navigates_to_raw_qr_value(user):
    """Ревью разведки: «location.href = val» уводил сессию на любой адрес из QR."""
    for tg in (False, True):
        body = views.redeem_home(
            _req("get", "/promotions/redeem/", user, _tenant(), tg=tg)
        ).content.decode()
        assert "location.href = val" not in body
        assert "data-redeem-prefix" in body and "data-scan-form" in body


def test_lite_home_counter_tiles(user):
    _reservations()
    body = core_views.dashboard(_req("get", "/dashboard/", user, _tenant())).content.decode()
    assert 'data-lite-counter="reservations"' in body
    assert "/promotions/reservations/?status=offen" in body
    assert "2 offen" in body
    assert 'data-lite-counter="scan"' in body and "/promotions/redeem/" in body


def test_promotion_list_tile_links_offen(user):
    _reservations()
    body = views.promotion_list(_req("get", "/promotions/", user, _tenant())).content.decode()
    assert "/promotions/reservations/?status=offen" in body
    assert "?status=pending" not in body
