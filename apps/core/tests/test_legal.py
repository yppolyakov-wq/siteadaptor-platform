"""L5/E-2 — LegalDoc: резолвер-цепочка, /agb/, футер-тег, кабинет «Recht», демо-засев."""

import pytest
from django.contrib.auth import get_user_model
from django.contrib.messages.middleware import MessageMiddleware
from django.contrib.sessions.middleware import SessionMiddleware
from django.http import Http404
from django.test import RequestFactory

from apps.core import views as core_views
from apps.core.legal import legal_text
from apps.core.models import LegalDoc
from apps.promotions import public_views
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _tenant_urlconf(settings):
    settings.ROOT_URLCONF = "config.urls_tenant"


def _tenant(**kw):
    kw.setdefault("enabled_locales", ["de", "en"])
    kw.setdefault("default_locale", "de")
    return TenantFactory.build(name="Bäckerei X", **kw)


# --- резолвер --------------------------------------------------------------


def test_legal_text_prefers_requested_locale():
    LegalDoc.objects.create(kind="impressum", locale="de", text="DE-Impressum")
    LegalDoc.objects.create(kind="impressum", locale="en", text="EN-Imprint")
    t = _tenant()
    assert legal_text(t, "impressum", locale="en") == "EN-Imprint"
    assert legal_text(t, "impressum", locale="de") == "DE-Impressum"


def test_legal_text_falls_back_to_default_locale_then_flat_field():
    t = _tenant(impressum="Flaches Impressum")
    # нет доков вовсе → плоское Tenant-поле
    assert legal_text(t, "impressum", locale="en") == "Flaches Impressum"
    # док только в дефолтной локали → берётся для другой локали
    LegalDoc.objects.create(kind="impressum", locale="de", text="Doc-DE")
    assert legal_text(t, "impressum", locale="en") == "Doc-DE"
    # пустой док = отсутствие (не перекрывает цепочку)
    LegalDoc.objects.create(kind="impressum", locale="en", text="   ")
    assert legal_text(t, "impressum", locale="en") == "Doc-DE"


def test_legal_text_generated_fallback_and_agb_empty():
    t = _tenant()  # без плоских полей → генерённые тексты
    assert t.name in legal_text(t, "impressum", locale="de")
    assert "Datenschutz" in legal_text(t, "datenschutz", locale="de")
    assert legal_text(t, "agb", locale="de") == ""  # AGB фолбэка не имеет


# --- витрина: /agb/ + футер ---------------------------------------------------


def _req(path="/"):
    request = RequestFactory().get(path)
    SessionMiddleware(lambda r: None).process_request(request)
    MessageMiddleware(lambda r: None).process_request(request)
    request.tenant = _tenant()
    return request


def test_agb_page_404_without_text_and_renders_with():
    with pytest.raises(Http404):
        public_views.agb(_req("/agb/"))
    LegalDoc.objects.create(kind="agb", locale="de", text="Unsere AGB gelten.")
    body = public_views.agb(_req("/agb/")).content.decode()
    assert "Unsere AGB gelten." in body


def test_footer_agb_link_only_when_doc_present():
    body = public_views.impressum(_req("/impressum/")).content.decode()
    assert 'href="/agb/"' not in body
    LegalDoc.objects.create(kind="agb", locale="de", text="AGB-Text")
    body = public_views.impressum(_req("/impressum/")).content.decode()
    assert 'href="/agb/"' in body


def test_legal_pages_use_legaldoc_over_flat():
    LegalDoc.objects.create(kind="datenschutz", locale="de", text="Doc-Datenschutz-XYZ")
    body = public_views.privacy(_req("/datenschutz/")).content.decode()
    assert "Doc-Datenschutz-XYZ" in body


# --- кабинет «Recht» ------------------------------------------------------------


def _cab_req(method="get", data=None, tenant=None):
    req = getattr(RequestFactory(), method)("/dashboard/recht/", data or {})
    SessionMiddleware(lambda r: None).process_request(req)
    MessageMiddleware(lambda r: None).process_request(req)
    import uuid

    uname = f"own-{uuid.uuid4().hex[:8]}"
    req.user = get_user_model().objects.create_user(
        username=uname, email=f"{uname}@test.de", password="pw12345678"
    )
    from apps.core.models import Membership

    # KA-12: «Recht & Steuern» — только владелец (гейт и во вьюхе).
    Membership.objects.create(user=req.user, role=Membership.ROLE_OWNER)
    req.tenant = tenant or _tenant()
    return req


def test_recht_screen_links_texts_to_seiten_and_ignores_old_doc_fields():
    """M21.10: тексты правятся в «Website › Seiten»; «Recht & Steuern» — реквизиты и
    ссылки. Старый POST с doc_* (закешированная форма) ничего не пишет и не удаляет."""
    tenant = _tenant()
    body = core_views.legal_docs_view(_cab_req(tenant=tenant)).content.decode()
    for kind in ("impressum", "datenschutz", "widerruf", "agb"):
        assert f"/dashboard/site/seiten/recht/{kind}/" in body
    assert 'name="doc_' not in body
    LegalDoc.objects.create(kind="widerruf", locale="de", text="Alt")
    core_views.legal_docs_view(
        _cab_req("post", {"doc_agb_de": "Neu", "doc_widerruf_de": ""}, tenant)
    )
    assert not LegalDoc.objects.filter(kind="agb").exists()
    assert LegalDoc.objects.get(kind="widerruf").text == "Alt"


# --- демо-засев -----------------------------------------------------------------


def test_seed_legal_docs_creates_honest_texts():
    from apps.tenants import demo_kits

    kit = demo_kits.KITS["friseur"]
    tenant = _tenant(address="Hauptstr. 1", contact_email="demo@test.de")
    demo_kits._seed_legal_docs(tenant, kit)
    kinds = set(LegalDoc.objects.values_list("kind", flat=True))
    assert kinds == {"impressum", "datenschutz", "widerruf", "agb"}
    agb = LegalDoc.objects.get(kind="agb", locale="de").text
    assert "Allgemeine Geschäftsbedingungen" in agb
    assert "Termine" in agb  # booking-кит получает §Termine
    ds = LegalDoc.objects.get(kind="datenschutz", locale="de").text
    assert "Bitte passen Sie diesen Text" not in ds  # без placeholder-хинта


def test_sp4_legal_screen_keeps_tax_fields_in_dom():
    """SP-4/M21.10: реквизиты на «Recht & Steuern» — все поля в DOM (W0)."""
    body = core_views.legal_docs_view(_cab_req()).content.decode()
    for name in ("vat_id", "tax_number", "legal_form", "register_court", "legal_responsible"):
        assert f'name="{name}"' in body
    assert "max-w-5xl" in body
