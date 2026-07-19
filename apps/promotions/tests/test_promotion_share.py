"""ST-6b: экран «Teilen» акции — публикации по каналам + «überall veröffentlichen».

Замки: идемпотентность повторного веера (дублей Publication нет), гейты
(не-active/без publishing — отказ), рендер статусов и входов email/★,
кнопка «Teilen» в списке акций.
"""

from uuid import uuid4

import pytest
from django.contrib.auth import get_user_model
from django.contrib.messages.middleware import MessageMiddleware
from django.contrib.sessions.middleware import SessionMiddleware
from django.test import RequestFactory

from apps.promotions import views
from apps.promotions.tests.factories import PromotionFactory
from apps.publishing.models import Channel, Publication
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _urlconf(settings):
    settings.ROOT_URLCONF = "config.urls_tenant"


def _req(method="get", data=None, tenant=None):
    req = getattr(RequestFactory(), method)("/promotions/x/teilen/", data or {})
    SessionMiddleware(lambda r: None).process_request(req)
    MessageMiddleware(lambda r: None).process_request(req)
    o = uuid4().hex[:8]
    req.user = get_user_model().objects.create_user(
        username=f"o-{o}", email=f"o-{o}@t.de", password="pw12345678"
    )
    req.tenant = tenant
    return req


def test_share_page_lists_channels_and_button():
    t = TenantFactory(slug="sh1", name="Sh1")
    promo = PromotionFactory()
    Channel.objects.create(type=Channel.LOG, name="Log", is_enabled=True)
    body = views.promotion_share(_req(tenant=t), promo.pk).content.decode()
    assert "Aktion überall teilen" in body
    assert "Noch nicht veröffentlicht" in body  # включённый канал без публикации
    assert "Jetzt überall veröffentlichen" in body
    assert "Per E-Mail an Kunden" in body  # вход в кампании (UWG: только переход)


def test_share_post_is_idempotent(monkeypatch):
    # Celery в тестах не гоняем — веер ставит Publication + .delay (замокан).
    from apps.publishing import tasks as pub_tasks

    monkeypatch.setattr(pub_tasks.publish_to_channel, "delay", lambda **kw: None)
    t = TenantFactory(slug="sh2", name="Sh2")
    promo = PromotionFactory()
    ch = Channel.objects.create(type=Channel.LOG, name="Log", is_enabled=True)

    resp = views.promotion_share(_req("post", tenant=t), promo.pk)
    assert resp.status_code == 302
    assert Publication.objects.filter(promotion=promo, channel=ch).count() == 1
    # повторный клик — дубля нет (get_or_create по (promotion, channel))
    views.promotion_share(_req("post", tenant=t), promo.pk)
    assert Publication.objects.filter(promotion=promo, channel=ch).count() == 1


def test_share_post_rejects_non_active():
    t = TenantFactory(slug="sh3", name="Sh3")
    promo = PromotionFactory(status="draft")
    Channel.objects.create(type=Channel.LOG, name="Log", is_enabled=True)
    views.promotion_share(_req("post", tenant=t), promo.pk)
    assert Publication.objects.filter(promotion=promo).count() == 0


def test_promotion_list_has_share_link():
    t = TenantFactory(slug="sh4", name="Sh4")
    promo = PromotionFactory()
    body = views.promotion_list(_req(tenant=t)).content.decode()
    assert f"/promotions/{promo.pk}/teilen/" in body and "Teilen" in body
