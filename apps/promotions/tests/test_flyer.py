"""T-8.9 «Aushang»: флаер на одну акцию с QR. План — docs/t8-9-flyer-plan-2026-10-10.md."""

import io
from datetime import timedelta

import pytest
from django.contrib.auth import get_user_model
from django.contrib.messages.middleware import MessageMiddleware
from django.contrib.sessions.middleware import SessionMiddleware
from django.test import RequestFactory
from django.utils import timezone, translation
from PIL import Image

from apps.core import documents
from apps.core.tests.test_documents_i18n import pdf_text
from apps.promotions import flyer, views
from apps.promotions.tests.factories import PromotionFactory
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db

URL = "https://klingenbrot.siteadaptor.de/p/1/"


@pytest.fixture(autouse=True)
def _helvetica(monkeypatch):
    # Helvetica-режим: строки в потоке PDF читаемы (у subset-TTF они закодированы).
    monkeypatch.setattr(documents, "unicode_fonts_available", lambda: False)


@pytest.fixture
def user(db):
    return get_user_model().objects.create_user(
        username="flyer", email="flyer@test.de", password="pw12345678"
    )


def _tenant(slug="t89", **kw):
    return TenantFactory(
        schema_name=slug.replace("-", "_"),
        slug=slug,
        name="Backhaus Klinge",
        address="Klostergasse 3",
        city="Solingen",
        disabled_modules=kw.pop("disabled", ["orders"]),
        **kw,
    )


def _promo(**kw):
    kw.setdefault("status", "active")
    kw.setdefault("title", {"de": "Feierabendtüte"})
    kw.setdefault("price_override", "5.00")
    kw.setdefault("compare_at_price", "10.00")
    kw.setdefault("ends_at", timezone.now() + timedelta(days=3))
    return PromotionFactory(**kw)


def _text(promo, tenant, fmt="a6", lang="de"):
    with translation.override(lang):
        return pdf_text(flyer.build_promo_flyer_pdf(promo, URL, fmt=fmt, tenant=tenant))


@pytest.mark.parametrize("fmt", flyer.FORMATS)
def test_every_format_builds_one_page_pdf(fmt):
    pdf = flyer.build_promo_flyer_pdf(_promo(), URL, fmt=fmt, tenant=_tenant())
    assert pdf.startswith(b"%PDF")
    assert pdf.count(b"/Type /Page\n") + pdf.count(b"/Type /Page ") <= 1 or b"/Count 1" in pdf


def test_flyer_prints_title_price_cta_and_address():
    text = _text(_promo(), _tenant())
    assert "Feierabendt" in text
    assert "5,00" in text and "10,00" in text and "50 %" in text
    assert "zur" in text and "cklegen lassen" in text  # «Scannen & zurücklegen lassen»
    assert "Klostergasse 3, Solingen" in text
    assert "klingenbrot.siteadaptor.de" in text and "/p/1" not in text  # путь не печатаем
    assert "gültig bis" in text.replace("\\374", "ü") or "g\\374ltig bis" in text


def test_mystery_style_never_prints_the_price():
    text = _text(_promo(discount_style="mystery"), _tenant())
    assert "5,00" not in text and "10,00" not in text
    assert "berraschungspreis" in text


def test_validity_today_and_future_start():
    now = timezone.localtime()
    today = _promo(ends_at=now.replace(hour=23, minute=0, second=0, microsecond=0))
    assert "Nur heute bis 23:00" in flyer.validity_line(today, now=now.replace(hour=9))
    later = _promo(status="scheduled", starts_at=now + timedelta(days=2), ends_at=None)
    assert flyer.validity_line(later, now=now).startswith("ab ")


def test_qr_carries_flyer_channel():
    assert flyer.flyer_url(URL) == URL + "?ch=flyer"


def test_cta_follows_customer_response():
    tenant = _tenant("t89-cta", disabled=["orders"])
    assert "Details" in flyer.call_to_action(_promo(metadata={"response": "show"}), tenant)
    shop = _tenant("t89-shop", disabled=[])
    assert "bestellen" in flyer.call_to_action(_promo(), shop)


def test_english_flyer_is_translated():
    text = _text(_promo(), _tenant(), lang="en")
    assert "Scannen" not in text


def test_broken_photo_still_builds():
    promo = _promo(images=[{"id": "x", "path": "promotions/missing.png", "is_primary": True}])
    assert flyer.build_promo_flyer_pdf(promo, URL, tenant=_tenant()).startswith(b"%PDF")


def test_photo_is_embedded(tmp_path, settings):
    from django.core.files.base import ContentFile

    from apps.catalog.images import delete_stored_image, save_product_image

    buf = io.BytesIO()
    Image.new("RGB", (40, 30), "orange").save(buf, "PNG")
    ref = save_product_image(ContentFile(buf.getvalue(), name="p.png"), is_primary=True)
    try:
        with_photo = flyer.build_promo_flyer_pdf(_promo(images=[ref]), URL, tenant=_tenant())
        without = flyer.build_promo_flyer_pdf(_promo(), URL, tenant=_tenant("t89-b"))
        assert with_photo.count(b"/Subtype /Image") > without.count(b"/Subtype /Image")
    finally:
        delete_stored_image(ref)


def _get(path, user, tenant):
    req = RequestFactory().get(path)
    SessionMiddleware(lambda r: None).process_request(req)
    MessageMiddleware(lambda r: None).process_request(req)
    req.user = user
    req.tenant = tenant
    return req


def test_view_returns_attachment_for_active_promo(user):
    tenant = _tenant()
    promo = _promo()
    resp = views.promotion_flyer(
        _get(f"/promotions/{promo.pk}/aushang.pdf?format=a6x4", user, tenant), pk=promo.pk
    )
    assert resp.status_code == 200 and resp["Content-Type"] == "application/pdf"
    assert 'filename="aushang-t89-a6x4.pdf"' in resp["Content-Disposition"]


def test_view_refuses_draft(user):
    tenant = _tenant()
    promo = _promo(status="draft")
    resp = views.promotion_flyer(
        _get(f"/promotions/{promo.pk}/aushang.pdf", user, tenant), pk=promo.pk
    )
    assert resp.status_code == 302 and resp.url == f"/promotions/{promo.pk}/edit/"


def test_flyer_links_on_done_screen_and_edit_page(user):
    tenant = _tenant()
    promo = _promo()
    done = views.promotion_quick_done(
        _get(f"/promotions/{promo.pk}/fertig/", user, tenant), pk=promo.pk
    ).content.decode()
    assert "data-flyer-links" in done and "format=a6x4" in done
    edit = views.promotion_edit(
        _get(f"/promotions/{promo.pk}/edit/", user, tenant), pk=promo.pk
    ).content.decode()
    assert "data-flyer-links" in edit
    draft = _promo(status="draft")
    edit = views.promotion_edit(
        _get(f"/promotions/{draft.pk}/edit/", user, tenant), pk=draft.pk
    ).content.decode()
    assert "data-flyer-links" not in edit
