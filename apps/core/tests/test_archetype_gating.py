"""H0 (архетипы как сущности): гейтинг секций редактора по активному архетипу.

Пекарня (catalog) не видит в списке секций Stay/Events/Services/Handwerker; их
конфиг при сохранении НЕ теряется (carry-forward). Мультиархетип видит объединение.
"""

from types import SimpleNamespace

import pytest
from django.contrib.messages.middleware import MessageMiddleware
from django.contrib.sessions.middleware import SessionMiddleware
from django.test import RequestFactory

from apps.core import archetypes, views
from apps.tenants import siteconfig
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _urlconf(settings):
    settings.ROOT_URLCONF = "config.urls_tenant"


class _FakeTenant:
    def __init__(self, active):
        self._active = set(active)

    def is_module_active(self, key):
        return key in self._active


def test_section_visible_for_generic_always_shown():
    t = _FakeTenant({"catalog"})
    for generic in (
        "hero",
        "usp_bar",
        "promotions",
        "about",
        "faq",
        "gallery",
        "contact",
        "archetypes",
    ):
        assert archetypes.section_visible_for(t, generic), generic


def test_section_visible_for_gates_inactive_archetypes():
    t = _FakeTenant({"catalog"})  # только магазин
    assert archetypes.section_visible_for(t, "products")  # catalog активен
    assert archetypes.section_visible_for(t, "categories")
    for gated in ("stay_rooms", "stay_search", "events", "services", "before_after"):
        assert not archetypes.section_visible_for(t, gated), gated


def test_section_visible_for_multiarchetype_union():
    t = _FakeTenant({"catalog", "stays", "events", "booking", "jobs"})
    for k in ("products", "stay_rooms", "events", "services", "before_after"):
        assert archetypes.section_visible_for(t, k), k


def _get(tenant):
    req = RequestFactory().get("/dashboard/site/home/")
    SessionMiddleware(lambda r: None).process_request(req)
    MessageMiddleware(lambda r: None).process_request(req)
    req.user = SimpleNamespace(is_authenticated=True)
    req.tenant = tenant
    return views.home_builder_view(req)


def test_editor_hides_inactive_archetype_sections():
    tenant = TenantFactory(
        schema_name="public",
        slug="gate",
        name="Gate",
        business_type="bakery",
        disabled_modules=["stays", "events", "booking", "jobs", "orders", "loyalty"],
    )
    body = _get(tenant).content.decode()
    assert 'name="enabled_products"' in body  # catalog (core) — виден
    for gated in ("stay_rooms", "stay_search", "events", "services", "before_after"):
        assert f'name="enabled_{gated}"' not in body, gated


def test_editor_save_preserves_hidden_section_config():
    """Скрытая (нерелевантная) секция при сохранении формы не теряет enabled/настройки."""
    tenant = TenantFactory(
        schema_name="public",
        slug="gate2",
        name="Gate2",
        business_type="bakery",
        disabled_modules=["stays", "events", "booking", "jobs", "orders", "loyalty"],
        site_config={
            "sections": [
                {"key": "stay_rooms", "enabled": True, "layout": {"preset": "cols2"}},
                {"key": "products", "enabled": True},
            ]
        },
    )
    # POST без полей stay_rooms (скрыта) — только products
    req = RequestFactory().post(
        "/dashboard/site/home/",
        {"order_products": "1", "enabled_products": "on"},
    )
    SessionMiddleware(lambda r: None).process_request(req)
    MessageMiddleware(lambda r: None).process_request(req)
    req.user = SimpleNamespace(is_authenticated=True)
    req.tenant = tenant
    assert views.home_builder_view(req).status_code == 302
    cfg = siteconfig.normalize(tenant.site_config)
    stay = next((s for s in cfg["sections"] if s.get("key") == "stay_rooms"), None)
    assert stay is not None and stay["enabled"] is True  # carry-forward, не затёрта
    assert stay["layout"]["preset"] == "cols2"  # настройки сохранены
