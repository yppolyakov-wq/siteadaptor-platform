"""P2.3c: история броней клиента по всем бизнесам (email-связка).

Тенант в тестах — public (физических tenant-схем нет, как в test_reconcile);
прод-обход исключает public, поэтому tenants инжектится параметром. Email —
uuid: кэш истории (TTL 60с) живёт в общем Redis.
"""

import uuid

import pytest
from django.contrib.sessions.middleware import SessionMiddleware
from django.test import RequestFactory

from apps.aggregator import account_views, auth
from apps.aggregator.account_services import reservations_for_email
from apps.aggregator.models import AggregatorPortal, PortalUser
from apps.promotions.models import Reservation
from apps.promotions.services import reserve
from apps.promotions.tests.factories import PromotionFactory
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _portal_urlconf(settings):
    settings.ROOT_URLCONF = "config.urls_portal"


def _email():
    return f"{uuid.uuid4().hex}@kunde.test"


def _tenant():
    return TenantFactory(schema_name="public", slug="baeckerei", name="Bäckerei X")


def _reserve(email, title="Brot -20%", quantity=1):
    promo = PromotionFactory(
        status="active", available_quantity=20, max_per_customer=10, title={"de": title}
    )
    return reserve(promo, name="Kunde", email=email, quantity=quantity)


def test_collects_reservations_by_email():
    tenant, email = _tenant(), _email()
    res = _reserve(email, title="MeinBrot", quantity=2)
    _reserve(_email(), title="FremdesBrot")  # чужая бронь — мимо

    rows = reservations_for_email(email, tenants=[tenant])
    assert len(rows) == 1
    assert rows[0]["business"] == "Bäckerei X"
    assert rows[0]["title"] == "MeinBrot"
    assert rows[0]["code"] == res.reference_code
    assert rows[0]["quantity"] == 2
    assert rows[0]["url"].endswith(f"/r/{res.reference_code}/")
    assert "baeckerei." in rows[0]["url"]


def test_newest_first_and_limit():
    tenant, email = _tenant(), _email()
    first = _reserve(email, title="Alt")
    second = _reserve(email, title="Neu")
    rows = reservations_for_email(email, tenants=[tenant], limit=1)
    assert len(rows) == 1
    assert rows[0]["code"] == second.reference_code
    assert rows[0]["code"] != first.reference_code


def test_email_match_is_case_insensitive():
    tenant = _tenant()
    email = _email()
    _reserve(email.upper())
    assert len(reservations_for_email(email, tenants=[tenant])) == 1


def test_result_is_cached():
    tenant, email = _tenant(), _email()
    _reserve(email)
    assert len(reservations_for_email(email, tenants=[tenant])) == 1
    Reservation.objects.all().delete()
    # минуту отдаём из кэша — БД уже пуста
    assert len(reservations_for_email(email, tenants=[tenant])) == 1


def test_account_page_shows_reservations(monkeypatch):
    """Вьюха рендерит брони из сервиса (сам сбор покрыт юнитами выше)."""
    from django.utils import timezone

    from apps.aggregator import account_services

    monkeypatch.setattr(
        account_services,
        "reservations_for_email",
        lambda email, **kw: [
            {
                "business": "Bäckerei X",
                "title": "KontoBrot",
                "code": "R-ABC123",
                "quantity": 2,
                "status": "confirmed",
                "created_at": timezone.now(),
                "url": "https://baeckerei.siteadaptor.de/r/R-ABC123/",
            }
        ],
    )
    portal, _ = AggregatorPortal.objects.get_or_create(
        host="muenchen.siteadaptor.de",
        defaults={"kind": "city", "city": "München", "title": {"de": "Angebote München"}},
    )
    user = PortalUser.objects.create(email=_email())
    request = RequestFactory().get("/konto/")
    SessionMiddleware(lambda r: None).process_request(request)
    request.portal = portal
    request.session[auth.SESSION_KEY] = user.pk

    body = account_views.account(request).content.decode()
    assert "KontoBrot" in body
    assert "R-ABC123" in body
    assert "https://baeckerei.siteadaptor.de/r/R-ABC123/" in body
