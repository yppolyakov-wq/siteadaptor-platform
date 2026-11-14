"""FB-29 R1: «Wo zeigen» у баннера — поиск по всем страницам (без потолка списка меню),
несколько страниц за одно сохранение, допустимость места — по базе."""

import pytest

from apps.catalog.models import Category, Product
from apps.core import banner_views as views
from apps.core import banners
from apps.core.models import Banner
from apps.core.tests.test_m21_6_content_pages import _req, _user

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _urlconf(settings):
    settings.ROOT_URLCONF = "config.urls_tenant"


def _banner():
    return banners.create({"title": "Herbsttee", "image": {"url": "/media/hero/a.jpg"}})


def _product(name, **kw):
    return Product.objects.create(name={"de": name, "en": ""}, base_price="9.90", **kw)


def test_place_exists_checks_the_database_not_the_menu_list():
    p = _product("Darjeeling")
    off = _product("Aus", is_active=False)
    Category.objects.create(slug="tee", name={"de": "Tee"})
    assert banners.place_exists(f"product:{p.pk}") is True
    assert banners.place_exists("category:tee") is True
    assert banners.place_exists(f"product:{off.pk}") is False
    assert banners.place_exists("product:not-a-uuid") is False
    assert banners.place_exists("category:nope") is False
    assert banners.place_exists("blog:1") is False


def test_search_finds_pages_beyond_the_menu_limit():
    for i in range(230):
        _product(f"Tee {i:03d}")
    needle = _product("Seltener Oolong")
    groups = banners.place_search("oolong")
    values = [o["value"] for g in groups for o in g["items"]]
    assert values == [f"product:{needle.pk}"]
    # без запроса — короткий список для начала, а не все 231
    start = [o for g in banners.place_search("") for o in g["items"]]
    assert 0 < len(start) <= banners.PLACE_SEARCH_LIMIT * len(banners.SHOW_ON_TYPES)


def test_search_skips_what_is_already_chosen():
    p = _product("Darjeeling")
    groups = banners.place_search("darj", exclude=[f"product:{p.pk}"])
    assert not [o for g in groups for o in g["items"]]


def test_labels_come_from_the_database():
    p = _product("Darjeeling")
    b = _banner()
    Banner.objects.filter(pk=b.pk).update(show_on=[f"product:{p.pk}", "category:weg"])
    b.refresh_from_db()
    rows = banners.show_on_rows(None, b)
    assert "Darjeeling" in rows[0]["label"] and rows[0]["missing"] is False
    assert rows[1]["missing"] is True


def _post(banner, data, user):
    base = {
        "b_present": "1",
        "b_title": banner.title,
        "b_is_active": "on",
        "b_image_url": "/media/hero/a.jpg",
        "b_show_present": "1",
    }
    return views.banner_edit(_req(method="post", data={**base, **data}, user=user), pk=banner.pk)


def test_several_pages_are_added_in_one_save():
    a, c = _product("Darjeeling"), _product("Assam")
    b = _banner()
    keys = [f"product:{a.pk}", f"product:{c.pk}", "product:00000000-0000-0000-0000-000000000000"]
    assert _post(b, {"b_show_add": keys}, _user()).status_code == 302
    assert Banner.objects.get(pk=b.pk).show_on == keys[:2], "несуществующая страница отброшена"


def test_form_has_a_search_that_does_not_submit_the_banner_form():
    p = _product("Seltener Oolong")
    b = _banner()
    request = _req(path="/x/?wo=oolong", user=_user())
    html = views.banner_edit(request, pk=b.pk).content.decode()
    assert 'name="wo"' in html and 'form="b-show-search"' in html
    assert '<form id="b-show-search" method="get"' in html
    assert f'value="product:{p.pk}"' in html and 'type="checkbox" name="b_show_add"' in html
    assert 'value="oolong"' in html


def test_ticked_pages_stay_ticked_after_a_form_error():
    p = _product("Darjeeling")
    b = _banner()
    data = {"b_present": "1", "b_title": "Herbsttee", "b_starts": "kein-datum", "b_show_present": "1",
            "b_show_add": [f"product:{p.pk}"]}  # fmt: skip
    resp = views.banner_edit(_req(method="post", data=data, user=_user()), pk=b.pk)
    html = resp.content.decode()
    assert resp.status_code == 200 and 'id="b-error"' in html
    assert f'value="product:{p.pk}" checked' in html


def test_radio_groups_in_the_panel_send_one_request():
    import pathlib

    js = pathlib.Path("static/js/aufbau.js").read_text()
    assert "radioTimer" in js
