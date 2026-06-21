"""S2b: отдельный конструктор главной /dashboard/site/home/.

Композиция блоков главной (порядок/видимость секций + тизеры архетипов) живёт
здесь; сохранение мёржит в текущий site_config, не затрагивая остальной дизайн.
`site_view` («Site») больше НЕ перестраивает секции из своей формы — переносит
как есть (регрессия: пустая форма не должна гасить блоки).
"""

from types import SimpleNamespace

import pytest
from django.contrib.messages.middleware import MessageMiddleware
from django.contrib.sessions.middleware import SessionMiddleware
from django.test import RequestFactory

from apps.core import views
from apps.tenants import siteconfig
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _tenant_urlconf(settings):
    settings.ROOT_URLCONF = "config.urls_tenant"  # reverse("site-home") в редиректе


def _request(method, path, data=None, tenant=None):
    req = getattr(RequestFactory(), method)(path, data or {})
    SessionMiddleware(lambda r: None).process_request(req)
    MessageMiddleware(lambda r: None).process_request(req)
    req.user = SimpleNamespace(is_authenticated=True)  # обойти login_required
    req.tenant = tenant
    return req


def test_home_builder_saves_blocks_and_preserves_design():
    tenant = TenantFactory(
        schema_name="public",
        slug="hb",
        name="HB",
        site_config={
            "hero_title": "Hallo",
            "nav": {"style": "centered", "sticky": False, "items": []},
        },
    )
    data = {
        "order_hero": "1",
        "enabled_hero": "on",
        "order_archetypes": "2",
        "enabled_archetypes": "on",
        "order_products": "3",  # без enabled_ → выключается
        "arch_visible_catalog": "on",
        "arch_label_catalog": "Speisekarte",
        "arch_blurb_catalog": "Frisch & vegan",
    }
    resp = views.home_builder_view(_request("post", "/dashboard/site/home/", data, tenant))
    assert resp.status_code == 302

    cfg = siteconfig.normalize(tenant.site_config)
    enabled = {s["key"] for s in cfg["sections"] if s["enabled"]}
    assert "hero" in enabled and "archetypes" in enabled
    assert "products" not in enabled  # снят
    # Композиция не затёрла остальной дизайн.
    assert cfg["hero_title"] == "Hallo"
    assert cfg["nav"]["style"] == "centered" and cfg["nav"]["sticky"] is False
    # Оверрайд тизера сохранён.
    assert cfg["archetypes"]["catalog"]["label"] == "Speisekarte"
    assert cfg["archetypes"]["catalog"]["blurb"] == "Frisch & vegan"


def test_home_builder_get_renders():
    tenant = TenantFactory(schema_name="public", slug="hb2", name="HB2")
    resp = views.home_builder_view(_request("get", "/dashboard/site/home/", tenant=tenant))
    assert resp.status_code == 200
    body = resp.content.decode()
    assert "order_hero" in body  # форма секций отрисована
    assert "arch_visible_catalog" in body  # карточки архетипов


def test_site_view_does_not_wipe_homepage_composition():
    """Регрессия S2b: форма «Site» не присылает order_/enabled_ → секции и
    оверрайды тизеров должны сохраниться (раньше site_view строил их из POST)."""
    tenant = TenantFactory(
        schema_name="public",
        slug="sv",
        name="SV",
        site_config={
            "sections": [{"key": "archetypes", "enabled": True}],
            "archetypes": {"catalog": {"label": "Speisekarte", "blurb": "", "hidden": False}},
        },
    )
    resp = views.site_view(_request("post", "/dashboard/site/", {}, tenant))
    assert resp.status_code == 302
    cfg = siteconfig.normalize(tenant.site_config)
    enabled = {s["key"] for s in cfg["sections"] if s["enabled"]}
    assert "archetypes" in enabled  # не погашено пустой формой
    assert cfg["archetypes"]["catalog"]["label"] == "Speisekarte"  # оверрайд цел
