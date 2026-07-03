"""CM-6.1/6.3 — кабинет «Bewertungen»: список+фильтры, скрыть/показать
(пропадает с витрины), сводка owner_overview, подписи сущностей."""

import uuid

import pytest
from django.contrib.auth import get_user_model
from django.contrib.messages.middleware import MessageMiddleware
from django.contrib.sessions.middleware import SessionMiddleware
from django.test import RequestFactory

from apps.reviews import services, views
from apps.reviews.models import Review

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _tenant_urlconf(settings):
    settings.ROOT_URLCONF = "config.urls_tenant"


def _req(method="get", data=None):
    request = getattr(RequestFactory(), method)("/dashboard/reviews/", data or {})
    SessionMiddleware(lambda r: None).process_request(request)
    MessageMiddleware(lambda r: None).process_request(request)
    uname = f"o{uuid.uuid4().hex[:10]}"
    request.user = get_user_model().objects.create_user(
        username=uname, email=f"{uname}@t.de", password="pw12345678"
    )
    return request


def _review(**kw):
    kw.setdefault("entity_kind", "product")
    kw.setdefault("entity_id", uuid.uuid4())
    kw.setdefault("rating", 5)
    kw.setdefault("author_name", "Kim")
    kw.setdefault("email", f"{uuid.uuid4().hex[:8]}@t.de")
    return Review.objects.create(**kw)


def test_list_shows_reviews_with_entity_label():
    from apps.catalog.tests.factories import ProductFactory

    p = ProductFactory(name={"de": "Roggenbrot"})
    _review(entity_id=p.pk, comment="Lecker!")
    _review(entity_kind="service", comment="Toll!")  # сущности нет → «—», не падаем
    body = views.review_list(_req()).content.decode()
    assert "Lecker!" in body and "Roggenbrot" in body
    assert "Toll!" in body


def test_toggle_hides_from_storefront():
    r = _review(comment="Naja")
    resp = views.review_toggle(_req("post"), pk=r.pk)
    assert resp.status_code == 302
    r.refresh_from_db()
    assert r.is_published is False
    # витринный ридер больше не видит отзыв
    assert services.published_for(r.entity_kind, r.entity_id).count() == 0
    views.review_toggle(_req("post"), pk=r.pk)  # обратно
    r.refresh_from_db()
    assert r.is_published is True


def test_overview_and_hidden_filter():
    _review(rating=5)
    _review(rating=3)
    _review(rating=1, is_published=False)
    ov = services.owner_overview()
    assert ov["count"] == 2 and ov["avg"] == 4.0 and ov["hidden"] == 1
    body = views.review_list(_req(data={"status": "hidden"})).content.decode()
    assert body.count("★") >= 1  # скрытый показан в фильтре hidden


def test_reply_saved_and_rendered_on_storefront():
    """CM-6.2: ответ владельца сохраняется и виден под отзывом на витрине товара."""
    from django.contrib.messages.middleware import MessageMiddleware as MM
    from django.contrib.sessions.middleware import SessionMiddleware as SM

    from apps.catalog.tests.factories import ProductFactory
    from apps.promotions import public_views as promo_public
    from apps.tenants.tests.factories import TenantFactory

    p = ProductFactory(name={"de": "Brot"})
    r = _review(entity_id=p.pk, comment="Gut")
    resp = views.review_reply(_req("post", {"reply_text": "Danke, Kim!"}), pk=r.pk)
    assert resp.status_code == 302
    r.refresh_from_db()
    assert r.reply_text == "Danke, Kim!" and r.replied_at is not None

    sreq = RequestFactory().get(f"/sortiment/{p.pk}/")
    SM(lambda x: None).process_request(sreq)
    MM(lambda x: None).process_request(sreq)
    sreq.tenant = TenantFactory.build(name="B")
    body = promo_public.product_detail(sreq, pk=p.pk).content.decode()
    assert "Danke, Kim!" in body and "Reply from the business" in body

    # пустой текст убирает ответ
    views.review_reply(_req("post", {"reply_text": "  "}), pk=r.pk)
    r.refresh_from_db()
    assert r.reply_text == "" and r.replied_at is None
