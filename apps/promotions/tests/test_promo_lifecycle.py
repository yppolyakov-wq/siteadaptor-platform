"""SF-3: конец жизни акции + мобильный CTA + PAngV на карточках + 404/500.

До SF-3: деталь закончившейся акции = get_object_or_404(status="active") →
голый джанговский 404 (класс «QR на флаере ведёт в никуда»); кастомных
404/500-шаблонов у платформы не было вовсе; sticky-buybar был на 5 деталях,
кроме акции; строка §11 PAngV жила только на детали акции.
"""

from datetime import timedelta
from decimal import Decimal

import pytest
from django.contrib.messages.middleware import MessageMiddleware
from django.contrib.sessions.middleware import SessionMiddleware
from django.http import Http404
from django.test import RequestFactory
from django.utils import timezone
from django.views import defaults as django_defaults

from apps.promotions import public_views
from apps.promotions.models import Promotion
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _urlconf(settings):
    settings.ROOT_URLCONF = "config.urls_tenant"


def _tenant(slug, **kw):
    return TenantFactory(schema_name="public", slug=slug, name="PL", **kw)


def _req(path="/aktionen/", tenant=None):
    req = RequestFactory().get(path)
    SessionMiddleware(lambda r: None).process_request(req)
    MessageMiddleware(lambda r: None).process_request(req)
    req.tenant = tenant
    return req


def _detail(promo, tenant):
    return public_views.promotion_detail(_req(f"/p/{promo.pk}/", tenant), pk=promo.pk)


def test_ended_promotion_renders_friendly_page_with_410():
    t = _tenant("lc1")
    ended = Promotion.objects.create(title={"de": "VorbeiDeal"}, status="ended")
    Promotion.objects.create(title={"de": "NochDaDeal"}, status="active")

    resp = _detail(ended, t)
    body = resp.content.decode()
    assert resp.status_code == 410  # Gone — краулерам честно
    assert "VorbeiDeal" in body  # посетитель видит, ЧТО это была за акция
    assert "Dieses Angebot ist leider beendet." in body
    # CTA + альтернативы из актуальных акций
    assert "Aktuelle Angebote ansehen" in body
    assert 'data-grid="promo_ended_alt"' in body and "NochDaDeal" in body
    # формы резерва на странице нет
    assert "promo-reserve-modal" not in body


def test_paused_promotion_is_200_and_archived_410():
    t = _tenant("lc2")
    paused = Promotion.objects.create(title={"de": "PauseDeal"}, status="paused")
    resp = _detail(paused, t)
    assert resp.status_code == 200
    assert "Dieses Angebot ist derzeit pausiert." in resp.content.decode()

    archived = Promotion.objects.create(title={"de": "ArchivDeal"}, status="archived")
    assert _detail(archived, t).status_code == 410


def test_draft_and_scheduled_stay_404():
    # черновик/запланированная наружу не светились — не раскрываем их страницей
    t = _tenant("lc3")
    for st in ("draft", "scheduled"):
        promo = Promotion.objects.create(title={"de": f"X{st}"}, status=st)
        with pytest.raises(Http404):
            _detail(promo, t)


def test_ended_without_module_has_no_alternatives_block():
    t = _tenant("lc4", disabled_modules=["promotions"])
    ended = Promotion.objects.create(title={"de": "EndeDeal"}, status="ended")
    body = _detail(ended, t).content.decode()
    assert 'data-grid="promo_ended_alt"' not in body
    assert "Aktuelle Angebote ansehen" not in body  # CTA вёл бы в 404 модуля


def test_active_detail_has_sticky_buybar_but_mystery_not():
    t = _tenant("lc5")
    promo = Promotion.objects.create(
        title={"de": "BarDeal"},
        status="active",
        price_override=Decimal("1.99"),
        compare_at_price=Decimal("2.49"),
    )
    body = _detail(promo, t).content.decode()
    assert "data-buybar" in body
    assert "#angebot" in body and 'id="angebot"' in body

    mystery = Promotion.objects.create(
        title={"de": "GeheimDeal"},
        status="active",
        price_override=Decimal("1.00"),
        compare_at_price=Decimal("2.00"),
        discount_style="mystery",
    )
    assert "data-buybar" not in _detail(mystery, t).content.decode()


def test_card_shows_pangv_lowest_line_on_listing():
    from apps.catalog.models import PriceLog
    from apps.catalog.tests.factories import ProductFactory

    t = _tenant("lc6")
    product = ProductFactory(name={"de": "Saft"}, base_price=Decimal("2.49"))
    PriceLog.objects.all().delete()
    PriceLog.objects.create(product=product, price=Decimal("2.19"))
    PriceLog.objects.update(created_at=timezone.now() - timedelta(days=5))
    Promotion.objects.create(
        title={"de": "SaftDeal"},
        status="active",
        product=product,
        price_override=Decimal("1.99"),
        compare_at_price=Decimal("2.49"),
    )
    body = public_views.promotion_list(_req(tenant=t)).content.decode()
    assert "Niedrigster Preis der letzten 30 Tage" in body
    assert "2,19" in body


def test_custom_404_and_500_pages():
    req = RequestFactory().get("/gibts-nicht/")
    req.tenant = _tenant("lc7")
    resp = django_defaults.page_not_found(req, Http404())
    assert resp.status_code == 404
    assert "Seite nicht gefunden." in resp.content.decode()

    resp = django_defaults.server_error(req)
    assert resp.status_code == 500
    assert "Etwas ist schiefgelaufen" in resp.content.decode()
