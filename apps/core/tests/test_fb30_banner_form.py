"""FB-30.7 (макет 1): форма баннера в две колонки; «Wo zeigen» — «＋ Ort hinzufügen»:
сначала вид страницы, потом список этого вида; «Startseite» — место показа, выбор пишется
сразу (решение владельца 2026-11-15, вопрос 2)."""

import pytest

from apps.catalog.models import Category, Product
from apps.core import banner_views as views
from apps.core import banners
from apps.core.tests.test_m21_6_content_pages import _req, _user
from apps.tenants.models import Tenant
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _urlconf(settings):
    settings.ROOT_URLCONF = "config.urls_tenant"


def _banner(title="Herbsttee"):
    return banners.create({"title": title, "image": {"url": "/media/hero/a.jpg"}})


def _tenant(**config):
    return TenantFactory(auto_create_schema=False, site_config=config)


_USER = {}


def _owner():
    if "u" not in _USER or not type(_USER["u"]).objects.filter(pk=_USER["u"].pk).exists():
        _USER["u"] = _user()
    return _USER["u"]


def _edit(banner, tenant, path="/x/", data=None):
    method = "post" if data is not None else "get"
    req = _req(path, method=method, data=data, user=_owner(), tenant=tenant)
    return views.banner_edit(req, pk=banner.pk)


def _pick(tenant):
    return (Tenant.objects.get(pk=tenant.pk).site_config.get("hero_banners") or {}).get("pick")


def test_form_has_two_columns_with_content_left_and_places_right():
    html = _edit(_banner(), _tenant()).content.decode()
    left = html.index("data-banner-content")
    right = html.index("data-banner-side")
    assert left < html.index('name="b_title"') < right
    assert right < html.index("data-banner-show-on")
    assert "lg:grid-cols-2" in html


def test_add_place_asks_for_the_kind_first_then_lists_that_kind():
    Category.objects.create(slug="tee", name={"de": "Grüner Tee"})
    Product.objects.create(name={"de": "Sencha"}, base_price="5")
    b = _banner()

    def places(html):
        return html[html.index("data-banner-show-add") : html.index('name="b_is_active"')]

    html = _edit(b, _tenant()).content.decode()
    assert "data-banner-kind=" in html and "Grüner Tee" not in places(html), "без вида — без списка"
    html = _edit(b, _tenant(), "/x/?art=category").content.decode()
    assert "Grüner Tee" in places(html) and "Sencha" not in places(html)
    assert 'aria-current="true"' in html[html.index('data-banner-kind="category"') - 300 :][:600]


def test_home_is_a_place_written_at_once():
    tenant = _tenant(hero_banners={"pick": []})
    b = _banner()
    data = {"b_present": "1", "b_title": "Herbsttee", "b_is_active": "on", "b_home_present": "1",
            "b_home": "1"}  # fmt: skip
    assert _edit(b, tenant, data=data).status_code == 302
    assert _pick(tenant) == [str(b.pk)]
    html = _edit(b, Tenant.objects.get(pk=tenant.pk)).content.decode()
    assert 'name="b_home" value="1" checked' in html
    _edit(b, tenant, data={**data, "b_home": ""})
    assert _pick(tenant) == []


def test_home_choice_is_not_touched_without_its_sentinel():
    b = _banner()
    tenant = _tenant(hero_banners={"pick": [str(b.pk)]})
    _edit(b, tenant, data={"b_present": "1", "b_title": "Herbsttee", "b_is_active": "on"})
    assert _pick(tenant) == [str(b.pk)]


def test_home_keeps_other_picked_banners_and_their_order():
    a, b = _banner("A"), _banner("B")
    tenant = _tenant(hero_banners={"pick": [str(a.pk)], "auto": False})
    assert banners.set_home(tenant, b, True) is True
    assert _pick(tenant) == [str(a.pk), str(b.pk)]
    assert banners.set_home(tenant, b, True) is False
    assert Tenant.objects.get(pk=tenant.pk).site_config["hero_banners"]["auto"] is False
    banners.set_home(tenant, a, False)
    assert _pick(tenant) == [str(b.pk)]


def test_status_line_says_where_and_whether_the_banner_shows():
    b = _banner()
    tenant = _tenant(hero_banners={"pick": [str(b.pk)]})
    html = _edit(b, tenant).content.decode()
    assert "data-banner-status" in html and "Startseite" in html
    b.is_active = False
    b.save(update_fields=["is_active"])
    html = _edit(b, tenant).content.decode()
    assert "ausgeschaltet" in html.split("data-banner-status", 1)[1][:400]
