"""LS-3: кабинет — композер «Angebot senden» из треда + карточки/отзыв.

Пикер позиций — FB-8 sellable_manage (названия/kind резолвятся из секций,
не из hidden-инпутов); свободные строки; итог уходит offers.send_offer.
"""

import uuid
from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from django.contrib.messages.middleware import MessageMiddleware
from django.contrib.sessions.middleware import SessionMiddleware
from django.test import RequestFactory

from apps.catalog.tests.factories import ProductFactory
from apps.inbox import services, views
from apps.orders import offers
from apps.orders.models import Offer
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _urlconf(settings):
    settings.ROOT_URLCONF = "config.urls_tenant"


def _req(method="get", data=None):
    request = getattr(RequestFactory(), method)("/dashboard/inbox/", data or {})
    SessionMiddleware(lambda r: None).process_request(request)
    MessageMiddleware(lambda r: None).process_request(request)
    o = uuid.uuid4().hex[:8]
    request.user = get_user_model().objects.create_user(
        username=f"o-{o}", email=f"o-{o}@t.de", password="pw12345678"
    )
    request.tenant = TenantFactory.build(disabled_modules=[])
    return request


def _conv():
    return services.start_conversation(subject="Frage", body="Hi", email="k@t.de", name="Kim")


def test_compose_get_renders_picker_and_free_rows():
    product = ProductFactory(name={"de": "Schokotorte"}, base_price=Decimal("24.00"))
    html = views.offer_compose(_req(), pk=_conv().pk).content.decode()
    assert "Schokotorte" in html
    assert f'value="product:{product.pk}"' in html
    assert 'name="free_title"' in html and 'name="valid_until"' in html


def test_compose_post_creates_offer_from_pick_and_free_rows():
    product = ProductFactory(name={"de": "Schokotorte"}, base_price=Decimal("24.00"))
    conv = _conv()
    data = {
        "pick": [f"product:{product.pk}"],
        f"qty:product:{product.pk}": "2",
        f"price:product:{product.pk}": "20,00",  # спеццена, немецкая запятая
        "free_title": ["Lieferung", "", ""],
        "free_price": ["5.00", "", ""],
        "free_qty": ["1", "1", "1"],
        "valid_until": "2027-01-31",
        "note": "Bis Freitag reserviert.",
    }
    resp = views.offer_compose(_req("post", data), pk=conv.pk)
    assert resp.status_code == 302
    offer = conv.offers.get()
    assert offer.lines.count() == 2
    first = offer.lines.first()
    assert first.kind == "product" and first.ref_id == str(product.pk)
    assert first.title == "Schokotorte" and first.unit_price == Decimal("20.00")
    assert offer.total == Decimal("45.00")
    assert str(offer.valid_until) == "2027-01-31"
    assert offer.customer_email == "k@t.de"


def test_compose_post_without_lines_shows_error():
    conv = _conv()
    resp = views.offer_compose(_req("post", {"free_title": ["", "", ""]}), pk=conv.pk)
    assert resp.status_code == 200  # остаёмся на форме с ошибкой
    assert not conv.offers.exists()


def test_thread_shows_offer_card_and_cancel():
    conv = _conv()
    offer = offers.send_offer(conv, lines=[{"title": "X", "unit_price": "9.00", "qty": 1}])
    html = views.thread(_req(), pk=conv.pk).content.decode()
    assert "Angebot senden" in html  # кнопка композера
    assert f"/o/{offer.token}/" in html  # ссылка на клиентскую страницу
    assert "Zurückziehen" in html
    # отзыв предложения из треда
    views.thread(_req("post", {"action": "offer-cancel", "offer_id": str(offer.pk)}), pk=conv.pk)
    offer.refresh_from_db()
    assert offer.status == Offer.STATUS_CANCELLED
