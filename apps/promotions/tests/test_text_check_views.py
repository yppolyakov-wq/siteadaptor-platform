"""D2a-2 (T-8.10e): подсказки «Text-Check» владельцу — эндпоинт и провод в экраны.

План — docs/d2-ai-text-check-plan-2026-10-17.md §5, §7 (D2a-2). Подсказки только
советуют: сохранение и публикация не блокируются никогда."""

from __future__ import annotations

import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser
from django.contrib.messages.middleware import MessageMiddleware
from django.contrib.sessions.middleware import SessionMiddleware
from django.test import RequestFactory
from django.urls import reverse
from django.utils import timezone

from apps.promotions import text_check as ptc
from apps.promotions import views
from apps.promotions.models import Promotion
from apps.promotions.tests.factories import PromotionFactory
from apps.tenants.tests.factories import TenantFactory

pytestmark = [pytest.mark.django_db, pytest.mark.urls("config.urls_tenant")]

URL = "/promotions/pruefen/"


@pytest.fixture
def user(db):
    return get_user_model().objects.create_user(username="tc", password="pw12345678")


@pytest.fixture
def tenant(db):
    return TenantFactory.build(business_type="bakery")


def _req(method, path, user, data=None, tenant=None):
    rf = RequestFactory()
    request = rf.post(path, data or {}) if method == "post" else rf.get(path, data or {})
    SessionMiddleware(lambda r: None).process_request(request)
    MessageMiddleware(lambda r: None).process_request(request)
    request.user = user
    request.tenant = tenant or TenantFactory.build(business_type="bakery")
    return request


def test_url_is_routed():
    assert reverse("promotions:promotion-text-check") == URL


def test_check_endpoint_requires_login_and_post(user):
    anon = _req("post", URL, AnonymousUser(), {"title": "x"})
    assert views.promotion_text_check(anon).status_code == 302
    assert views.promotion_text_check(_req("get", URL, user)).status_code == 405


def test_quick_payload_renders_findings(user, isolated_ratelimit):
    resp = views.promotion_text_check(
        _req(
            "post",
            URL,
            user,
            {"title": "GRATIS KAFFEE NUR HEUTE!!!", "new_price": "2.50", "term": "week"},
        )
    )
    html = resp.content.decode()
    assert resp.status_code == 200
    for code in ("gratis_mit_preis", "dringlichkeit_heute", "grossbuchstaben"):
        assert f'data-tc-code="{code}"' in html, code
    assert "keine Rechtsberatung" not in html  # дисклеймер — в обёртке, не в результатах


def test_full_form_payload_reads_locale_fields(user, isolated_ratelimit):
    html = views.promotion_text_check(
        _req(
            "post",
            URL,
            user,
            {
                "title_de": "Der beste Kaffee",
                "description_de": "Statt 4,99 € nur 2,99 €",
                "price_override": "2.99",
                "ends_at": (timezone.now() + timezone.timedelta(days=3)).strftime("%Y-%m-%dT%H:%M"),
            },
        )
    ).content.decode()
    assert 'data-tc-code="alleinstellung"' in html
    assert 'data-tc-code="statt_ohne_referenz"' in html


def test_clean_text_says_no_findings(user, isolated_ratelimit):
    html = views.promotion_text_check(
        _req("post", URL, user, {"title": "Frische Brezeln", "term": "week"})
    ).content.decode()
    assert "data-tc-empty" in html


def test_check_writes_nothing_to_db(user, isolated_ratelimit, django_assert_max_num_queries):
    with django_assert_max_num_queries(0):
        views.promotion_text_check(
            _req("post", URL, user, {"title": "Gratis Kaffee", "new_price": "2"})
        )
    assert Promotion.objects.count() == 0


def test_check_endpoint_rate_limited(user, isolated_ratelimit, settings):
    settings.TEXT_CHECK_RATE_LIMIT = 2
    for _ in range(2):
        assert (
            views.promotion_text_check(_req("post", URL, user, {"title": "x"})).status_code == 200
        )
    assert views.promotion_text_check(_req("post", URL, user, {"title": "x"})).status_code == 429


@pytest.mark.parametrize(
    "data",
    [
        {"title": "x" * 50_000, "description": "1 % " * 20_000},
        {
            "title": "Brot",
            "new_price": "abc",
            "old_price": "NaN",
            "percent": "1e999",
            "quantity": "-x",
        },
        {"title": "Brot", "ends_at": "morgen", "until": "31.31.2026", "term": "date"},
        {"title": "Brot", "product": "not-a-uuid"},
        {"title": "Brot", "price_condition_kind": "x_for_y", "price_condition_n": "zz"},
    ],
)
def test_garbage_payload_never_500(user, isolated_ratelimit, data):
    assert views.promotion_text_check(_req("post", URL, user, data)).status_code == 200


def test_html_in_quote_is_escaped(user, isolated_ratelimit):
    html = views.promotion_text_check(
        _req("post", URL, user, {"title": "Mehr: https://x.de/<script>alert(1)</script>"})
    ).content.decode()
    assert "<script>alert" not in html


def test_quick_assistant_contains_text_check_block(user):
    html = views.promotion_quick(_req("get", "/promotions/schnell/", user)).content.decode()
    assert "data-text-check" in html and URL in html


def test_full_form_create_has_block_and_edit_renders_server_findings(user):
    html = views.promotion_create(_req("get", "/promotions/new/", user)).content.decode()
    assert "data-text-check" in html
    promo = PromotionFactory(title={"de": "Gratis Kaffee nur heute"}, price_override=2)
    promo.ends_at = timezone.now() + timezone.timedelta(days=5)
    promo.save()
    html = views.promotion_edit(
        _req("get", f"/promotions/{promo.pk}/", user), promo.pk
    ).content.decode()
    assert 'data-tc-code="dringlichkeit_heute"' in html


def test_done_screen_lists_high_findings_with_edit_link(user):
    promo = PromotionFactory(title={"de": "Gratis Kaffee"}, price_override=2, status="draft")
    html = views.promotion_quick_done(
        _req("get", f"/promotions/schnell/fertig/{promo.pk}/", user), promo.pk
    ).content.decode()
    assert "data-done-text-check" in html
    assert 'data-tc-code="gratis_mit_preis"' in html
    assert reverse("promotions:promotion-edit", args=[promo.pk]) in html


def test_done_screen_without_findings_has_no_block(user):
    promo = PromotionFactory(title={"de": "Frische Brezeln"}, status="draft")
    html = views.promotion_quick_done(
        _req("get", f"/promotions/schnell/fertig/{promo.pk}/", user), promo.pk
    ).content.decode()
    assert "data-done-text-check" not in html


def test_save_never_blocked_by_findings(user):
    tenant = TenantFactory(schema_name="tc_save", slug="tc-save", name="tc-save")
    resp = views.promotion_quick(
        _req(
            "post",
            "/promotions/schnell/",
            user,
            {
                "title": "GRATIS KAFFEE NUR HEUTE!!!",
                "new_price": "2.50",
                "term": "week",
                "customer_response": "reserve",
                "publish": "now",
            },
            tenant=tenant,
        )
    )
    assert resp.status_code == 302
    assert Promotion.objects.filter(title__de="GRATIS KAFFEE NUR HEUTE!!!").exists()


def test_payload_adapter_maps_quick_and_full_names(tenant):
    quick_promo = ptc.promotion_from_payload(
        {"title": "A", "new_price": "2", "old_price": "3", "percent": "", "quantity": "4"}, tenant
    )
    assert quick_promo.title == {"de": "A"}
    assert quick_promo.price_override == 2 and quick_promo.compare_at_price == 3
    assert quick_promo.available_quantity == 4
    full = ptc.promotion_from_payload(
        {"title_de": "B", "title_en": "B en", "compare_at_price": "5", "discount_percent": "20"},
        tenant,
    )
    assert full.title == {"de": "B", "en": "B en"}
    assert full.discount_percent == 20
