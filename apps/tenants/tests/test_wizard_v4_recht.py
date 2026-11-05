"""AIS-W W4-1 срез 2: мастер v4 — шаги company → offer → recht → done, публикация из мастера."""

import uuid

import pytest
from django.contrib.auth import get_user_model
from django.contrib.messages.middleware import MessageMiddleware
from django.contrib.sessions.middleware import SessionMiddleware
from django.test import RequestFactory

from apps.core import views as core_views
from apps.tenants import onboarding
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db

V4 = {"onboarding": {"v": 2, "flow": "v4"}}


@pytest.fixture(autouse=True)
def _tenant_urlconf(settings):
    settings.ROOT_URLCONF = "config.urls_tenant"


def _req(method="get", data=None, tenant=None):
    request = getattr(RequestFactory(), method)("/dashboard/setup/", data or {})
    SessionMiddleware(lambda r: None).process_request(request)
    MessageMiddleware(lambda r: None).process_request(request)
    request.tenant = tenant
    owner = uuid.uuid4().hex[:8]
    request.user = get_user_model().objects.create_user(
        username=f"o-{owner}", email=f"o-{owner}@test.de", password="pw12345678"
    )
    return request


def _v4(**kw):
    kw.setdefault("schema_name", "public")
    kw.setdefault("slug", "v4")
    kw.setdefault("business_type", "bakery")
    return TenantFactory(published_at=None, site_config=dict(V4), **kw)


def test_v3_tenant_never_sees_recht_and_keeps_its_steps():
    tenant = TenantFactory.build(business_type="bakery")
    keys = onboarding.visible_keys(tenant)
    assert "recht" not in keys
    assert {"start", "language", "stil", "texts", "done"} <= set(keys)


def test_v4_shows_only_base_steps():
    tenant = TenantFactory.build(business_type="bakery", site_config=dict(V4), published_at=None)
    assert onboarding.visible_keys(tenant) == ["company", "offer", "recht", "done"]


def test_v4_cannot_finish_without_publishing():
    tenant = _v4()
    onboarding.goto(tenant, "recht")
    state = onboarding.advance(tenant, skip=True)
    assert state["step"] == "recht" and not state["completed"]
    assert onboarding.goto(tenant, "done")["step"] == "recht"


def test_publish_from_wizard_refuses_then_publishes():
    from apps.core.models import LegalDoc

    tenant = _v4(address="", contact_phone="")
    onboarding.goto(tenant, "recht")
    core_views.setup_view(_req("post", {"action": "publish"}, tenant))
    tenant.refresh_from_db()
    assert tenant.published_at is None

    tenant.address, tenant.contact_phone = "Weg 1, Hilden", "0211 1"
    tenant.save(update_fields=["address", "contact_phone"])
    LegalDoc.objects.create(kind="impressum", locale="de", text="Bäckerei, Weg 1, Hilden")
    core_views.setup_view(_req("post", {"action": "publish"}, tenant))
    tenant.refresh_from_db()
    assert tenant.published_at is not None
    assert onboarding.get_state(tenant)["step"] == "done"


def test_recht_saves_only_present_fields():
    tenant = _v4(slug="rs", vat_id="DE123456789", legal_form="gmbh")
    onboarding.goto(tenant, "recht")
    core_views.setup_view(_req("post", {"legal_representative": "Anna Muster"}, tenant))
    tenant.refresh_from_db()
    assert tenant.legal_representative == "Anna Muster"
    assert tenant.vat_id == "DE123456789" and tenant.legal_form == "gmbh"  # не стёрты


def test_company_hours_grid_writes_only_with_sentinel():
    tenant = _v4(slug="oh", opening_hours_structured={"0": ["08:00", "18:00"]})
    onboarding.goto(tenant, "company")
    core_views.setup_view(_req("post", {"action": "live", "name": "X"}, tenant))
    tenant.refresh_from_db()
    assert tenant.opening_hours_structured == {"0": ["08:00", "18:00"]}  # без сетки — не трогаем
    data = {"action": "live", "oh_present": "1", "oh_1_open": "09:00", "oh_1_close": "17:00"}
    core_views.setup_view(_req("post", data, tenant))
    tenant.refresh_from_db()
    assert tenant.opening_hours_structured == {"1": ["09:00", "17:00"]}


def test_regulated_trade_names_hwo_in_impressum():
    trade = TenantFactory.build(business_type="handwerker", chamber="HWK Düsseldorf")
    assert "Handwerksordnung (HwO)" in trade.impressum_text()
    shop = TenantFactory.build(business_type="bakery", chamber="IHK")
    assert "Handwerksordnung" not in shop.impressum_text()


def test_recht_step_renders_fields_preview_and_blockers():
    tenant = _v4(slug="rr", business_type="friseur", address="")
    onboarding.goto(tenant, "recht")
    html = core_views.setup_view(_req("get", tenant=tenant)).content.decode()
    assert "data-recht-form" in html and "data-recht-preview" in html
    assert "data-recht-blockers" in html and "data-recht-publish" in html
    assert 'name="chamber"' in html and "data-recht-trade-warning" in html


def test_recht_rejects_bad_email_and_ignores_forged_legal_form():
    tenant = _v4(slug="bad", legal_form="gmbh")
    onboarding.goto(tenant, "recht")
    core_views.setup_view(_req("post", {"contact_email": "kein-email"}, tenant))
    tenant.refresh_from_db()
    assert tenant.contact_email != "kein-email"
    core_views.setup_view(_req("post", {"legal_form": "<script>"}, tenant))
    tenant.refresh_from_db()
    assert tenant.legal_form == "gmbh"


def test_unpublished_site_stays_v4_even_without_onboarding_key():
    tenant = TenantFactory.build(business_type="bakery", site_config={}, published_at=None)
    assert onboarding.is_v4(tenant)
    assert "recht" in onboarding.visible_keys(tenant)


def test_save_button_comes_before_back_for_implicit_submit():
    tenant = _v4(slug="ord")
    onboarding.goto(tenant, "recht")
    html = core_views.setup_view(_req("get", tenant=tenant)).content.decode()
    assert html.index("Speichern") < html.index('value="back"')
