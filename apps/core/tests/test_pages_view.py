"""STU-5/6: экран «Pages» умер — те же гарантии держит Studio.

Экран был ВТОРЫМ писателем раскладок листингов, поэтому схлопнут (302 на Studio).
Но его тесты защищали НАСТОЯЩИЕ гарантии, и терять их вместе с экраном нельзя:
раскладки страниц, порядок и видимость секций детали события, сетка «Passt dazu»,
гейт по активным модулям и «сохранение не роняет чужие ключи». Здесь они
перенесены на форму Studio — источник тот же `site_config`, путь другой.
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
def _urlconf(settings):
    settings.ROOT_URLCONF = "config.urls_tenant"


def _builder(method, data=None, tenant=None):
    request = getattr(RequestFactory(), method)("/dashboard/site/home/", data or {})
    SessionMiddleware(lambda r: None).process_request(request)
    MessageMiddleware(lambda r: None).process_request(request)
    request.user = SimpleNamespace(is_authenticated=True)
    request.tenant = tenant
    return views.home_builder_view(request)


def test_dead_screen_redirects_to_studio():
    tenant = TenantFactory(schema_name="public", slug="pv0", name="PV0")
    request = RequestFactory().get("/dashboard/site/pages/")
    request.user = SimpleNamespace(is_authenticated=True)
    request.tenant = tenant
    resp = views.pages_view(request)
    assert resp.status_code == 302 and resp.url == "/dashboard/site/home/"


def test_studio_saves_per_page_layouts():
    tenant = TenantFactory(schema_name="public", slug="pv1", name="PV1", disabled_modules=[])
    _builder(
        "post",
        {
            "catalog_preset": "cols2",
            "stay_preset": "cols4",
            "events_preset": "cols3",
        },
        tenant,
    )
    cfg = siteconfig.normalize(tenant.site_config)
    assert cfg["catalog_layout"]["preset"] == "cols2"
    assert cfg["stay_index_layout"]["preset"] == "cols4"
    assert cfg["events_index_layout"]["preset"] == "cols3"


def test_studio_saves_event_detail_order():
    """M20U-4: порядок/видимость секций детальной события сохраняются."""
    tenant = TenantFactory(schema_name="public", slug="ped", name="PED", disabled_modules=[])
    _builder(
        "post",
        {
            # faq первым, idea скрыта; остальным — большой порядок
            "ed_order_faq": "1",
            "ed_visible_faq": "on",
            "ed_order_for_whom": "2",
            "ed_visible_for_whom": "on",
            "ed_order_idea": "3",  # ed_visible_idea не прислан → скрыта
        },
        tenant,
    )
    cfg = siteconfig.normalize(tenant.site_config)
    order = siteconfig.event_detail_order(cfg)
    assert order[0] == "faq" and "for_whom" in order and "idea" not in order
    assert order.index("faq") < order.index("for_whom")


def test_studio_renders_event_sections_when_events_active():
    tenant = TenantFactory(schema_name="public", slug="ped2", name="PED2", disabled_modules=[])
    body = _builder("get", tenant=tenant).content.decode()
    assert 'name="ed_order_faq"' in body and 'name="ed_visible_idea"' in body


def test_studio_saves_related_layout():
    """STU-5: сетка «Passt dazu» переехала с умершего экрана в уровень «эта страница»."""
    tenant = TenantFactory(schema_name="public", slug="pvr", name="PVR", disabled_modules=[])
    _builder("post", {"related_preset": "cols3"}, tenant)
    assert siteconfig.normalize(tenant.site_config)["detail_related_layout"]["preset"] == "cols3"


def test_studio_renders_active_pages_only():
    """Гейт по модулям: у тенанта без номеров и событий их раскладок в форме нет."""
    tenant = TenantFactory(
        schema_name="public", slug="pv2", name="PV2", disabled_modules=["stays", "events"]
    )
    body = _builder("get", tenant=tenant).content.decode()
    assert 'name="catalog_preset"' in body
    assert 'name="stay_preset"' not in body
    assert 'name="events_preset"' not in body


def test_studio_save_preserves_other_config():
    tenant = TenantFactory(
        schema_name="public", slug="pv3", name="PV3", site_config={"hero_title": "Hallo"}
    )
    _builder("post", {"catalog_preset": "cols2", "hero_title": "Hallo"}, tenant)
    cfg = siteconfig.normalize(tenant.site_config)
    assert cfg["hero_title"] == "Hallo" and cfg["catalog_layout"]["preset"] == "cols2"
