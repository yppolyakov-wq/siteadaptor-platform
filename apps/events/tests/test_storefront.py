"""A6c: витрина событий — список/детали, покупка билета, оплата, гейтинг."""

import uuid
from datetime import timedelta

import pytest
from django.contrib.messages.middleware import MessageMiddleware
from django.contrib.sessions.middleware import SessionMiddleware
from django.http import Http404
from django.test import RequestFactory
from django.utils import timezone

from apps.events import public_views
from apps.events.models import Event, Ticket
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _urlconf(settings):
    settings.ROOT_URLCONF = "config.urls_tenant"


def _req(method="post", data=None, tenant=None):
    request = getattr(RequestFactory(), method)("/veranstaltung/", data or {})
    request.META["REMOTE_ADDR"] = f"10.{uuid.uuid4().int % 250}.{uuid.uuid4().int % 250}.7"
    SessionMiddleware(lambda r: None).process_request(request)
    MessageMiddleware(lambda r: None).process_request(request)
    request.tenant = tenant or TenantFactory.build()
    return request


def _event(**kw):
    defaults = {
        "title": "Konzert",
        "starts_at": timezone.now() + timedelta(days=10),
        "status": Event.STATUS_PUBLISHED,
        "price_cents": 0,
        "capacity": 50,
        "questions": ["Anmerkung?"],
    }
    defaults.update(kw)
    return Event.objects.create(**defaults)


def test_detail_renders_retreat_landing_blocks():
    """Развёрнутый ретрит-лендинг: блоки из Event.details рендерятся на странице."""
    ev = _event(
        title="Retreat",
        images=[{"id": "x", "url": "https://img/1.jpg", "is_primary": True}],
        details={
            "promise": "Auftanken am See",
            "for_whom": ["du Stress spürst"],
            "includes": [{"title": "Yoga", "text": "morgens"}],
            "price_includes": ["Unterkunft"],
            "faq": [{"q": "Für Anfänger?", "a": "Ja"}],
            "hosts": [{"name": "Mara", "role": "Leitung", "photo": "https://img/h.jpg"}],
        },
    )
    body = public_views.veranstaltung_detail(_req("get"), ev.pk).content.decode()
    assert "Auftanken am See" in body  # hero-обещание
    assert "du Stress spürst" in body  # «für wen»
    assert "Yoga" in body and "Für Anfänger?" in body  # карточки + FAQ
    assert "Mara" in body and "https://img/1.jpg" in body  # ведущие + фото


def test_detail_unified_hero_gallery_and_price_card():
    """M20U-4: единый каркас детальной — галерея слева (свап) + sticky-карточка
    цены/брони справа + ссылка-инбокс (если модуль активен)."""
    ev = _event(
        title="Retreat",
        price_cents=12000,
        images=[
            {"id": "a", "url": "https://img/a.jpg", "is_primary": True},
            {"id": "b", "url": "https://img/b.jpg"},
        ],
    )
    tenant = TenantFactory.build()  # inbox активен по умолчанию
    body = public_views.veranstaltung_detail(_req("get", tenant=tenant), ev.pk).content.decode()
    # галерея M20U-G: большое фото + миниатюра со свапом
    assert "js-media-gallery" in body and 'data-src="https://img/b.jpg"' in body
    # sticky-карточка цены справа + кнопка брони (якорь на форму)
    assert "lg:sticky" in body and 'href="#buchen"' in body
    # ссылка-инбокс «задать вопрос» (M20U базовый чат)
    assert "kind=event" in body
    # форма брони на месте (не сломали)
    assert "storefront-event-book" in body or "/buchen/" in body
    # M20U-4: мобильная липкая панель покупки (цена + действие брони)
    assert "data-buybar" in body and "Jetzt buchen" in body
    # наследует единый каркас detail.html
    assert "max-w-5xl" in body and "lg:grid-cols-2" in body


def test_book_with_tier_uses_tier_price():
    """A6 ценовые тиры: бронь по выбранному тиру берёт его цену + снимок label."""
    ev = _event(
        title="Retreat",
        price_cents=29000,
        tiers=[
            {"label": "Frühbucher", "price_cents": 26000},
            {"label": "Standard", "price_cents": 29000},
        ],
    )
    req = _req(data={"name": "Mara", "email": "m@example.de", "tier": "Frühbucher", "quantity": 2})
    public_views.veranstaltung_book(req, ev.pk)
    t = Ticket.objects.get(event=ev)
    assert t.price_cents == 26000 and t.tier_label == "Frühbucher"
    assert t.total_cents == 52000  # цена тира × 2


def test_normalize_tiers_parses_and_sanitizes():
    from apps.events import details

    out = details.normalize_tiers(["Frühbucher | 79", {"label": "Kind", "price_cents": 0}, "  | 5"])
    assert out == [
        {"label": "Frühbucher", "price_cents": 7900, "capacity": 0},
        {"label": "Kind", "price_cents": 0, "capacity": 0},
    ]  # пустой label отброшен; capacity по умолчанию 0 (R11, без отдельного лимита)


def test_detail_normalizes_messy_details():
    """details.normalize терпим к мусору: строки «A | B», лишние ключи отброшены."""
    from apps.events import details

    out = details.normalize(
        {"includes": ["Yoga | sanft", "Meditation"], "junk": 1, "for_whom": "a\nb"}
    )
    assert out["includes"][0] == {"title": "Yoga", "text": "sanft"}
    assert out["includes"][1] == {"title": "Meditation", "text": ""}
    assert out["for_whom"] == ["a", "b"] and "junk" not in out


def test_index_requires_module():
    tenant = TenantFactory.build(disabled_modules=["events"])
    with pytest.raises(Http404):
        public_views.veranstaltung_index(_req("get", tenant=tenant))


def test_index_lists_published_future():
    _event(title="Sichtbar")
    _event(title="Entwurf", status=Event.STATUS_DRAFT)
    _event(title="Vergangen", starts_at=timezone.now() - timedelta(days=1))
    body = public_views.veranstaltung_index(_req("get")).content.decode()
    assert "Sichtbar" in body
    assert "Entwurf" not in body and "Vergangen" not in body


def test_free_event_books_confirmed_with_answers():
    event = _event(price_cents=0)
    resp = public_views.veranstaltung_book(
        _req("post", {"name": "Anna", "email": "a@test.de", "quantity": "2", "q0": "Vegan"}),
        pk=event.pk,
    )
    assert resp.status_code == 302
    ticket = Ticket.objects.get(event=event)
    assert ticket.quantity == 2
    assert ticket.status == Ticket.STATUS_CONFIRMED  # бесплатное → сразу
    assert ticket.answers == {"Anmerkung?": "Vegan"}


def test_honeypot_blocks():
    event = _event()
    public_views.veranstaltung_book(_req("post", {"name": "Bot", "website": "spam"}), pk=event.pk)
    assert Ticket.objects.filter(event=event).count() == 0


def test_paid_event_without_payments_stays_pending():
    event = _event(price_cents=2500)
    tenant = TenantFactory.build()  # payments_enabled False
    resp = public_views.veranstaltung_book(
        _req("post", {"name": "K", "email": "k@test.de"}, tenant=tenant), pk=event.pk
    )
    assert resp.status_code == 302
    assert Ticket.objects.get(event=event).status == Ticket.STATUS_PENDING


def test_sold_out_blocks_booking():
    event = _event(capacity=1)
    from apps.events.services import book_ticket

    book_ticket(event, name="A", email="a@test.de", quantity=1, auto_confirm=True)
    public_views.veranstaltung_book(_req("post", {"name": "B", "email": "b@test.de"}), pk=event.pk)
    assert event.tickets.count() == 1
