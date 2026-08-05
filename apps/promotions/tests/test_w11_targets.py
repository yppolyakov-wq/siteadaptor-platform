"""W11-4: акция на услугу/номер/комбо из UI — цели ценового слоя PL в форме.

Движок PL (P1–P7, 2026-08-04) готов; здесь только UI: селекты FK-целей в
PromotionForm (гейт по модулям), префилл из «% Aktion» строки Angebote.
"""

from types import SimpleNamespace
from uuid import uuid4

import pytest
from django.contrib.auth import get_user_model
from django.contrib.messages.middleware import MessageMiddleware
from django.contrib.sessions.middleware import SessionMiddleware
from django.test import RequestFactory

from apps.promotions.forms import PromotionForm

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _urlconf(settings):
    settings.ROOT_URLCONF = "config.urls_tenant"


def _req(path):
    req = RequestFactory().get(path)
    SessionMiddleware(lambda r: None).process_request(req)
    MessageMiddleware(lambda r: None).process_request(req)
    o = uuid4().hex[:8]
    req.user = get_user_model().objects.create_user(
        username=f"o-{o}", email=f"o-{o}@t.de", password="pw12345678"
    )
    return req


def test_promotion_form_offers_pl_targets_gated_by_module():
    """Селекты целей service/stay_unit/combo — только при активном модуле;
    движок PL (P1) не трогается — форма лишь пишет FK."""
    full = SimpleNamespace(
        is_module_active=lambda key: True, default_locale="de", enabled_locales=["de"]
    )
    form = PromotionForm(tenant=full)
    for f in ("service", "stay_unit", "combo"):
        assert f in form.fields, f

    shop = SimpleNamespace(
        is_module_active=lambda key: key not in ("booking", "stays"),
        default_locale="de",
        enabled_locales=["de"],
    )
    form = PromotionForm(tenant=shop)
    assert "service" not in form.fields and "stay_unit" not in form.fields
    assert "combo" in form.fields  # catalog — core


def test_promotion_create_prefills_target_from_get():
    """Кнопка «% Aktion» из Angebote: ?service=<pk> префиллит цель формы."""
    from apps.booking.models import Service
    from apps.promotions import views as promo_views

    svc = Service.objects.create(name="Haarschnitt", duration_minutes=30, price_cents=2500)
    body = promo_views.promotion_create(_req(f"/promotions/new/?service={svc.pk}")).content.decode()
    assert f'value="{svc.pk}" selected' in body


def test_promotion_form_saves_service_target():
    from apps.booking.models import Service

    svc = Service.objects.create(name="Massage", duration_minutes=60, price_cents=5000)
    form = PromotionForm(
        data={
            "title_de": "Happy Hour",
            "promo_type": "discount",
            "discount_percent": "20",
            "service": str(svc.pk),
            "available_quantity": "10",
            "max_per_customer": "1",
            "reservation_ttl_hours": "24",
            "starts_at": "2026-09-01T10:00",
            "ends_at": "2026-09-30T18:00",
        },
    )
    assert form.is_valid(), form.errors
    promo = form.save()
    assert promo.service_id == svc.pk


def test_angebote_cards_link_to_promotion_create():
    """Строка Angebote несёт «% Aktion» с параметром цели по kind."""
    from apps.booking.models import Service
    from apps.core import sellable_manage as sm
    from apps.core import views as core_views
    from apps.tenants.tests.factories import TenantFactory

    assert sm._PROMO_PARAM["stay"] == "stay_unit"
    svc = Service.objects.create(name="Föhnen", duration_minutes=20, price_cents=1500)
    req = _req("/dashboard/angebote/")
    req.tenant = TenantFactory.build(
        business_type="hairdresser", disabled_modules=["events", "stays"]
    )
    body = core_views.sellable_manage(req).content.decode()
    assert f"?service={svc.pk}" in body
