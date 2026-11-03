"""UX-D D6.4: Gutscheine & Treue — создание шторкой, суммы в €, страница программы."""

import json
import re
import uuid

import pytest
from django.contrib.auth import get_user_model
from django.contrib.messages.middleware import MessageMiddleware
from django.contrib.sessions.middleware import SessionMiddleware
from django.http import Http404
from django.test import RequestFactory

from apps.core.models import Membership
from apps.loyalty.models import LoyaltyProgram, Voucher
from apps.promotions import list_pages, views
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _urlconf(settings):
    settings.ROOT_URLCONF = "config.urls_tenant"


def _req(path, method="get", data=None, drawer=False):
    extra = {"HTTP_X_SF_DRAWER": "1"} if drawer else {}
    req = getattr(RequestFactory(), method)(path, data or {}, **extra)
    SessionMiddleware(lambda r: None).process_request(req)
    MessageMiddleware(lambda r: None).process_request(req)
    tag = uuid.uuid4().hex[:8]
    req.user = get_user_model().objects.create_user(username=f"u-{tag}", password="pw12345678")
    Membership.objects.get_or_create(user=req.user, defaults={"role": Membership.ROLE_OWNER})
    req.tenant = TenantFactory.build(disabled_modules=[])
    return req


def _innermost_is_drawer_aware(view):
    from apps.core import drawer

    code = drawer.drawer_aware(lambda r: r).__code__
    chain = [view]
    while hasattr(chain[-1], "__wrapped__"):
        chain.append(chain[-1].__wrapped__)
    return chain[-2].__code__ is code


# --- Gutscheine -----------------------------------------------------------------------


def test_voucher_list_has_no_inline_form_and_shows_euros():
    Voucher.objects.create(code="EURO10", label="x", discount_cents=500, min_order_cents=2000)
    html = views.voucher_list(_req("/promotions/vouchers/")).content.decode()
    assert 'name="count"' not in html  # формы генерации над списком больше нет
    assert re.search(r'<a href="/promotions/vouchers/neu/" data-drawer', html)
    assert "−5,00 €" in html or "−5.00 €" in html
    assert " ct" not in html


def test_voucher_new_fragment_and_generation():
    resp = list_pages.voucher_new(_req("/promotions/vouchers/neu/", drawer=True))
    html = resp.content.decode()
    assert resp["X-Sf-Fragment"] == "1" and "<script" not in html
    assert "data-drawer-form" in html and 'data-drawer-after="close"' in html
    resp = list_pages.voucher_new(
        _req(
            "/promotions/vouchers/neu/",
            "post",
            {
                "label": "−5 €",
                "count": "3",
                "max_uses": "1",
                "discount_eur": "5,50",
                "next": "/promotions/vouchers/",
            },
            drawer=True,
        )
    )
    assert json.loads(resp.content)["ok"] is True
    assert Voucher.objects.filter(label="−5 €", discount_cents=550).count() == 3


def test_voucher_new_errors_are_at_the_field():
    resp = list_pages.voucher_new(
        _req("/promotions/vouchers/neu/", "post", {"label": "", "count": "999"}, drawer=True)
    )
    html = resp.content.decode()
    assert resp.status_code == 200 and resp["X-Sf-Fragment"] == "1"
    assert 'id="id_count_errors"' in html and not Voucher.objects.exists()


def test_voucher_new_without_js_redirects_to_list():
    resp = list_pages.voucher_new(
        _req("/promotions/vouchers/neu/", "post", {"label": "x", "count": "1", "max_uses": "1"})
    )
    assert resp.status_code == 302 and resp.url == "/promotions/vouchers/"


# --- Treue ------------------------------------------------------------------------------


def test_loyalty_list_rows_link_to_the_page_and_creation_is_a_drawer():
    p = LoyaltyProgram.objects.create(label="Kaffee-Karte", reward_label="Gratis Kaffee")
    html = views.loyalty_list(_req("/promotions/loyalty/")).content.decode()
    assert 'name="stamps_required"' not in html
    assert f'href="/promotions/loyalty/{p.pk}/"' in html
    assert re.search(r'<a href="/promotions/loyalty/neu/" data-drawer', html)


def test_loyalty_new_creates_and_navigates_to_the_page():
    resp = list_pages.loyalty_new(
        _req(
            "/promotions/loyalty/neu/",
            "post",
            {
                "label": "Kaffee-Karte",
                "stamps_required": "8",
                "reward_label": "Gratis Kaffee",
                "is_active": "on",
                "next": "/promotions/loyalty/",
            },
            drawer=True,
        )
    )
    p = LoyaltyProgram.objects.get()
    data = json.loads(resp.content)
    assert data["navigate"] is True and data["location"] == f"/promotions/loyalty/{p.pk}/"


def test_loyalty_page_edits_program_and_keeps_collected_stamps():
    from apps.loyalty.models import LoyaltyCard
    from apps.promotions.models import Customer

    p = LoyaltyProgram.objects.create(label="Karte", reward_label="Kaffee", stamps_required=10)
    card = LoyaltyCard.objects.create(
        program=p, customer=Customer.objects.create(email="a@t.de"), stamps=7
    )
    resp = list_pages.loyalty_edit(
        _req(
            f"/promotions/loyalty/{p.pk}/",
            "post",
            {
                "program": str(p.pk),
                "label": "Kaffee-Karte",
                "stamps_required": "12",
                "reward_label": "Gratis Kaffee",
                "is_active": "on",
            },
        ),
        pk=p.pk,
    )
    p.refresh_from_db()
    card.refresh_from_db()
    assert resp.status_code == 302 and (p.label, p.stamps_required) == ("Kaffee-Karte", 12)
    assert card.stamps == 7


def test_loyalty_page_foreign_pk_is_404():
    p = LoyaltyProgram.objects.create(label="A", reward_label="B")
    with pytest.raises(Http404):
        list_pages.loyalty_edit(
            _req(f"/promotions/loyalty/{p.pk}/", "post", {"program": str(uuid.uuid4())}),
            pk=p.pk,
        )


def test_drawers_and_permissions():
    from apps.core import view_perms

    assert _innermost_is_drawer_aware(list_pages.voucher_new)
    assert _innermost_is_drawer_aware(list_pages.loyalty_new)
    r = view_perms.RULES
    assert r["promotions:voucher-new"] == r["promotions:voucher-list"]
    assert (
        r["promotions:loyalty-new"] == r["promotions:loyalty-edit"] == r["promotions:loyalty-list"]
    )


def test_loyalty_stamps_required_zero_is_rejected():
    p = LoyaltyProgram.objects.create(label="A", reward_label="B", stamps_required=10)
    data = {"program": str(p.pk), "label": "A", "stamps_required": "0", "reward_label": "B"}
    resp = list_pages.loyalty_edit(_req(f"/promotions/loyalty/{p.pk}/", "post", data), pk=p.pk)
    p.refresh_from_db()
    assert resp.status_code == 200 and p.stamps_required == 10
