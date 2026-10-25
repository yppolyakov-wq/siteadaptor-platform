"""KA-12 A-3 (G6): кейтеринг стартует с формой «дата · гости · повод», а
наборы/услуги «pro Person» считаются в смете по числу гостей заявки."""

import uuid
from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from django.contrib.messages import get_messages
from django.contrib.messages.middleware import MessageMiddleware
from django.contrib.sessions.middleware import SessionMiddleware
from django.test import RequestFactory

from apps.catalog.models import Combo
from apps.core import setup_steps
from apps.jobs import anfrage_presets, services, views
from apps.tenants.services import _new_tenant
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _urlconf(settings):
    settings.ROOT_URLCONF = "config.urls_tenant"


def _req(method="get", data=None, tenant=None, path="/dashboard/auftraege/"):
    request = getattr(RequestFactory(), method)(path, data or {})
    SessionMiddleware(lambda r: None).process_request(request)
    MessageMiddleware(lambda r: None).process_request(request)
    owner = uuid.uuid4().hex[:8]
    request.user = get_user_model().objects.create_user(username=f"o-{owner}", password="pw1234567")
    request.tenant = tenant if tenant is not None else TenantFactory.build()
    return request


def test_new_catering_tenant_gets_event_form_others_do_not():
    cat = _new_tenant(
        business_name="Tafel", slug="tafel", business_type="catering", city="Köln", email="a@b.de"
    )
    assert cat.site_config["anfrage"]["fields"] == ["date", "guests", "event_type"]
    assert "Hochzeit" in cat.site_config["anfrage"]["event_types"]
    handw = _new_tenant(
        business_name="Bau", slug="bau", business_type="handwerker", city="Köln", email="a@b.de"
    )
    assert "anfrage" not in handw.site_config


def test_switching_to_catering_adds_preset_but_never_overwrites_owner_choice():
    tenant = TenantFactory(business_type="handwerker", site_config={"notify": {"x": 1}})
    setup_steps.apply_business_type(tenant, "catering")
    tenant.refresh_from_db()
    assert tenant.site_config["anfrage"] == anfrage_presets.preset_for("catering")
    assert tenant.site_config["notify"] == {"x": 1}  # W6: чужие ключи целы

    own = {"fields": ["date"], "event_types": ["Grillfest"]}
    tenant2 = TenantFactory(business_type="bakery", site_config={"anfrage": own})
    setup_steps.apply_business_type(tenant2, "catering")
    tenant2.refresh_from_db()
    assert tenant2.site_config["anfrage"] == own

    # повтор шага тем же типом не возвращает пресет, если владелец снял все поля
    tenant3 = TenantFactory(business_type="catering", site_config={})
    setup_steps.apply_business_type(tenant3, "catering")
    tenant3.refresh_from_db()
    assert "anfrage" not in tenant3.site_config


def test_load_preset_button_overwrites_and_is_shown_only_for_typed_tenant():
    from apps.core import views as core_views

    tenant = TenantFactory(
        business_type="catering",
        disabled_modules=[],
        site_config={"anfrage": {"fields": ["date"]}},
    )
    views.anfrage_form_settings(_req("post", data={"load_preset": "1"}, tenant=tenant))
    tenant.refresh_from_db()
    assert tenant.site_config["anfrage"] == anfrage_presets.preset_for("catering")
    assert 'name="load_preset"' in core_views.ablaeufe_view(_req(tenant=tenant)).content.decode()

    other = TenantFactory.build(business_type="handwerker", disabled_modules=[])
    assert 'name="load_preset"' not in core_views.ablaeufe_view(_req(tenant=other)).content.decode()


def _job(guests):
    return services.create_job(name="Frau Meyer", title="Hochzeit", guest_count=guests)


def test_picker_marks_per_person_and_detail_carries_guests():
    combo = Combo.objects.create(name="Buffet", price=Decimal("25.00"), price_per_person=True)
    job = _job(40)
    tenant = TenantFactory.build(disabled_modules=[])
    body = views.job_detail(_req(tenant=tenant), pk=job.pk).content.decode()
    assert 'data-qt-guests="40"' in body
    assert f'value="k:{combo.pk}"' in body and 'data-per-person="1"' in body


def test_guest_change_with_lines_warns_to_check_quantities():
    tenant = TenantFactory.build(
        site_config={"anfrage": {"fields": ["guests"]}}, disabled_modules=[]
    )
    job = _job(40)
    services.set_lines(job, [{"text": "Buffet", "qty": 40, "unit_price": "25"}])
    req = _req(
        "post", data={"action": "request", "event_present": "1", "guest_count": "60"}, tenant=tenant
    )
    views.job_detail(req, pk=job.pk)
    texts = [str(m) for m in get_messages(req)]
    assert any("Gästezahl geändert" in t for t in texts)
    job.refresh_from_db()
    assert job.guest_count == 60 and job.lines.get().qty == Decimal("40")  # без автопересчёта
