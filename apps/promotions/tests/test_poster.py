"""Track B4: QR-постер магазина (A4 PDF) для печати в витрину."""

import pytest
from django.test import RequestFactory

from apps.promotions import views
from apps.promotions.poster import _pretty_url, _with_channel, build_shop_poster_pdf
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db


class _User:
    is_authenticated = True
    is_active = True


def _req(tenant=None):
    request = RequestFactory().get("/promotions/poster/")
    request.user = _User()
    if tenant is not None:
        request.tenant = tenant
    return request


def test_build_poster_returns_pdf_bytes():
    pdf = build_shop_poster_pdf("Bäckerei Müller", "https://mueller.example.com/")
    assert isinstance(pdf, bytes)
    assert pdf.startswith(b"%PDF")
    assert len(pdf) > 1000  # непустой документ с QR


def test_build_poster_handles_blank_name():
    assert build_shop_poster_pdf("", "https://x.example.com/").startswith(b"%PDF")


def test_pretty_url_strips_scheme_and_slash():
    assert _pretty_url("https://mueller.example.com/") == "mueller.example.com"


def test_qr_target_carries_channel_for_attribution():
    assert _with_channel("https://x.de/", "schaufenster") == "https://x.de/?ch=schaufenster"
    assert _with_channel("https://x.de/?a=1", "schaufenster") == "https://x.de/?a=1&ch=schaufenster"


def test_poster_view_returns_pdf_attachment():
    tenant = TenantFactory.build(name="Bäckerei Müller", slug="mueller", business_type="bakery")
    resp = views.shop_poster_pdf(_req(tenant))
    assert resp.status_code == 200
    assert resp["Content-Type"] == "application/pdf"
    assert resp["Content-Disposition"].startswith("attachment;")
    assert "mueller" in resp["Content-Disposition"]
    assert resp.content.startswith(b"%PDF")


def test_poster_view_without_tenant_is_safe():
    # request без tenant (как в части unit-тестов) не должен падать
    resp = views.shop_poster_pdf(_req())
    assert resp.status_code == 200
    assert resp.content.startswith(b"%PDF")
