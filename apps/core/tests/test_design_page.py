"""DL-7b: экран «Design» — переключатель шаблонов вне Studio.

Применение POST'ом сохраняется сразу (без зависимости от Save канвы);
галерея = сборки типа бизнеса + Look'и с ленивыми iframe-превью.
"""

import uuid

import pytest
from django.contrib.auth import get_user_model
from django.contrib.messages.middleware import MessageMiddleware
from django.contrib.sessions.middleware import SessionMiddleware
from django.test import RequestFactory

from apps.core.design_page import design_view
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db


def _req(tenant, method="get", data=None):
    request = getattr(RequestFactory(), method)("/dashboard/design/", data or {})
    SessionMiddleware(lambda r: None).process_request(request)
    MessageMiddleware(lambda r: None).process_request(request)
    o = uuid.uuid4().hex[:8]
    request.user = get_user_model().objects.create_user(
        username=f"o-{o}", email=f"o-{o}@t.de", password="pw12345678"
    )
    request.tenant = tenant
    return request


def test_gallery_lists_bundles_and_looks():
    tenant = TenantFactory(business_type="grocery")
    html = design_view(_req(tenant)).content.decode()
    # Сборки типа: рекомендованная Fokus-вариация + 5 универсальных дил-шаблонов.
    for key in ("fokus_angebote", "deal_prospekt", "deal_smart"):
        assert f'name="bundle" value="{key}"' in html, key
    assert 'data-src="/?preview=1&look=prospekt&bundle=deal_prospekt"' in html
    # Look'и — все 10 семейств с превью.
    assert 'name="look" value="neon"' in html
    assert 'data-src="/?preview=1&look=blatt"' in html


def test_post_bundle_applies_and_persists():
    tenant = TenantFactory(business_type="grocery")
    resp = design_view(_req(tenant, "post", {"bundle": "deal_neon"}))
    assert resp.status_code == 302
    tenant.refresh_from_db()
    assert tenant.site_config["theme"] == "dark"  # кожа neon
    assert tenant.site_config["site_defaults"]["card_chrome"] == "line"
    row = next(s for s in tenant.site_config["sections"] if s["key"] == "promotions")
    assert row["style"] == "spotlight" and row["enabled"] is True  # композиция


def test_active_badge_and_preview_links():
    """DL-8a: активный выбор помечен «Aktiv», у карточек есть полный превью."""
    from apps.tenants import sitetemplates

    tenant = TenantFactory(business_type="grocery")
    sitetemplates.apply_bundle(tenant, "deal_blatt")
    html = design_view(_req(tenant)).content.decode()
    assert "Aktiv" in html
    # Бейдж стоит на карточке активной сборки (рамка-подсветка + ✓).
    idx = html.find('value="deal_blatt"')
    assert idx > -1 and "Aktiv" in html[idx - 2500 : idx]
    assert 'href="/?preview=1&look=blatt&bundle=deal_blatt" target="_blank"' in html


def test_post_look_applies_skin_only():
    tenant = TenantFactory(business_type="grocery")
    resp = design_view(_req(tenant, "post", {"look": "prospekt"}))
    assert resp.status_code == 302
    tenant.refresh_from_db()
    assert tenant.site_config["site_defaults"]["card_chrome"] == "hard"


def test_post_junk_is_safe():
    tenant = TenantFactory(business_type="grocery")
    before = dict(tenant.site_config or {})
    resp = design_view(_req(tenant, "post", {"bundle": "junk"}))
    assert resp.status_code == 302
    tenant.refresh_from_db()
    assert (tenant.site_config or {}) == before  # конфиг не тронут


def test_templates_for_hides_foreign_presets():
    """DL-7a: «посторонние шаблоны» чужих отраслей ушли из галерей —
    рекомендованные типу + универсальные, и минимум один есть у КАЖДОГО типа."""
    from apps.tenants import sitetemplates
    from apps.tenants.models import Tenant

    keys = [t["key"] for t in sitetemplates.templates_for("grocery")]
    assert "gastro" not in keys and "termine" not in keys  # чужие отрасли
    for bt, _label in Tenant.BUSINESS_TYPES:
        ts = sitetemplates.templates_for(bt)
        assert ts, bt
        for t in ts:
            assert (not t["recommended_for"]) or bt in t["recommended_for"], (bt, t["key"])
