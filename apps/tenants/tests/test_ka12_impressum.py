"""KA-12 E7.1/E7.2: структурные данные Impressum (§ 5 DDG) и проверка полноты."""

import uuid

import pytest
from django.contrib.auth import get_user_model
from django.contrib.messages.middleware import MessageMiddleware
from django.contrib.sessions.middleware import SessionMiddleware
from django.test import RequestFactory

from apps.core.models import Membership
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _urlconf(settings):
    settings.ROOT_URLCONF = "config.urls_tenant"


def _t(**kw):
    slug = f"imp-{uuid.uuid4().hex[:6]}"
    base = dict(
        schema_name=slug.replace("-", "_"), slug=slug, name="Krume", owner_email="login@k.de"
    )
    base.update(kw)
    return TenantFactory.build(**base)


def test_gmbh_impressum_prints_form_representative_register():
    t = _t(
        address="Markt 1, 42651 Solingen",
        contact_email="info@krume.example.com",
        legal_form="gmbh",
        legal_representative="Anna Krume",
        register_court="Amtsgericht Wuppertal",
        register_number="HRB 12345",
        vat_id="DE123456789",
        legal_responsible="Ben Krume",
    )
    text = t.impressum_text()
    assert "Krume (GmbH)" in text
    assert "Vertreten durch: Anna Krume" in text
    assert "Registereintrag: Amtsgericht Wuppertal, HRB 12345" in text
    # V.i.S.d.P. остаётся своей строкой (§ 18 MStV) — не путать с представителем
    assert "§ 18 Abs. 2 MStV: Ben Krume" in text
    assert "login@k.de" not in text  # почта входа не уходит в Impressum
    assert t.impressum_missing() == []


def test_missing_matrix_by_legal_form():
    t = _t(address="", contact_email="", legal_form="gmbh")
    assert t.impressum_missing() == [
        "address",
        "contact_email",
        "representative",
        "register",
        "tax",
    ]
    single = _t(address="A 1", contact_email="a@b.de", legal_form="einzel", small_business=True)
    assert single.impressum_missing() == []  # Einzelunternehmen: ни представителя, ни реестра
    legacy = _t(address="A 1", contact_email="a@b.de", legal_form="ek", register_entry="HRA 1")
    assert "register" not in legacy.impressum_missing()  # старая запись засчитывается
    own = _t(impressum="Eigener Text")
    assert own.impressum_missing() == []


def _owner_post(tenant, data, role=Membership.ROLE_OWNER):
    from apps.core import lite_cabinet

    user = get_user_model().objects.create_user(username=f"o-{uuid.uuid4().hex[:6]}", password="x")
    Membership.objects.create(user=user, role=role)
    req = RequestFactory().post("/dashboard/geschaeft/", data)
    SessionMiddleware(lambda r: None).process_request(req)
    MessageMiddleware(lambda r: None).process_request(req)
    req.user, req.tenant = user, tenant
    return lite_cabinet.lite_business(req)


def test_lite_business_saves_legal_fields_and_requires_contact_email():
    tenant = _t()
    tenant.save()
    base = {
        "name": "Krume",
        "address": "Markt 1",
        "city": "Solingen",
        "contact_phone": "0212 1",
        "legal_form": "ug",
        "legal_representative": "Anna",
        "register_court": "AG Wuppertal",
        "register_number": "HRB 9",
        "tax_number": "123/456",
    }
    resp = _owner_post(tenant, base)  # без contact_email — форма не сохраняется
    assert resp.status_code == 200
    tenant.refresh_from_db()
    assert tenant.legal_form == ""
    resp = _owner_post(tenant, {**base, "contact_email": "info@krume.example.com"})
    assert resp.status_code == 302
    tenant.refresh_from_db()
    assert (tenant.legal_form, tenant.register_number, tenant.contact_email) == (
        "ug",
        "HRB 9",
        "info@krume.example.com",
    )
    assert tenant.impressum_missing() == []
