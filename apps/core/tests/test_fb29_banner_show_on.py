"""FB-29.2c: «Wo zeigen» у баннера — один баннер сразу на многих страницах (категория,
товар, услуга, акция), без блока на каждой."""

import datetime
import pathlib

import pytest
from django.template import Context, Template
from django.test import RequestFactory
from django.urls import reverse

from apps.catalog.models import Category, Product
from apps.core import banner_views as views
from apps.core import banners
from apps.core.models import Banner
from apps.core.tests.test_m21_6_content_pages import _req, _user
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _urlconf(settings):
    settings.ROOT_URLCONF = "config.urls_tenant"


def _banner(title="Herbsttee", **kwargs):
    fields = {"title": title, "image": {"url": "/media/hero/a.jpg"}}
    fields.update(kwargs)
    return banners.create(fields)


def _product(name="Darjeeling"):
    return Product.objects.create(name={"de": name, "en": ""}, base_price="9.90")


def _site(kind, obj):
    request = RequestFactory().get("/")
    request.tenant = TenantFactory.build()
    tpl = Template("{% load siteui %}{% place_banners kind obj %}")
    return tpl.render(Context({"request": request, "kind": kind, "obj": obj}))


# ───────────── данные ─────────────


def test_place_key_per_kind():
    p = _product()
    cat = Category.objects.create(slug="tee", name={"de": "Tee"})
    assert banners.place_key("product", p) == f"product:{p.pk}"
    assert banners.place_key("category", cat) == "category:tee"
    assert banners.place_key("blog", p) == "" and banners.place_key("product", None) == ""


def test_only_offered_places_are_stored_and_kept_ones_survive():
    p = _product()
    b = _banner()
    offered = {f"product:{p.pk}", "category:tee"}
    banners.set_show_on(
        b, keep=[], add=[f"product:{p.pk}", "product:not-offered", "x"], allowed=offered
    )
    assert b.show_on == [f"product:{p.pk}"]
    # место, которого сейчас нет в списке (товар выключен), остаётся, пока владелец его не снял
    banners.set_show_on(b, keep=[f"product:{p.pk}"], add=["category:tee"], allowed={"category:tee"})
    assert b.show_on == [f"product:{p.pk}", "category:tee"]
    banners.set_show_on(b, keep=["category:tee", "category:injected"], add=[], allowed=offered)
    assert b.show_on == ["category:tee"], "«оставить» можно только то, что уже было"
    assert Banner.objects.get(pk=b.pk).show_on == ["category:tee"]


def test_places_are_capped():
    b = _banner()
    many = [f"product:{i}" for i in range(80)]
    banners.set_show_on(b, keep=[], add=many, allowed=set(many))
    assert len(b.show_on) == banners.SHOW_ON_MAX


def test_category_address_change_keeps_the_place():
    b = _banner()
    banners.set_show_on(b, keep=[], add=["category:tee"], allowed={"category:tee"})
    assert banners.rename_place("category:tee", "category:tees") == 1
    assert Banner.objects.get(pk=b.pk).show_on == ["category:tees"]
    assert banners.rename_place("category:tees", "") == 1
    assert Banner.objects.get(pk=b.pk).show_on == []


# ───────────── витрина ─────────────


def test_banner_shows_on_its_places_only():
    a, other = _product("Darjeeling"), _product("Assam")
    b = _banner("Nur bei Darjeeling")
    banners.set_show_on(b, keep=[], add=[f"product:{a.pk}"], allowed={f"product:{a.pk}"})
    assert "Nur bei Darjeeling" in _site("product", a)
    assert _site("product", other).strip() == ""
    assert _site("product", None).strip() == ""


def test_several_banners_on_one_place_become_a_slider_in_library_order():
    p = _product()
    key = f"product:{p.pk}"
    for i, title in enumerate(("Erster", "Zweiter")):
        b = banners.create({"title": title, "image": {"url": "/media/hero/a.jpg"}}, sort_order=i)
        banners.set_show_on(b, keep=[], add=[key], allowed={key})
    html = _site("product", p)
    assert html.count("data-hero-slide") >= 2 and html.index("Erster") < html.index("Zweiter")


def test_inactive_or_out_of_date_banner_is_not_shown():
    p = _product()
    key = f"product:{p.pk}"
    off = _banner("Aus")
    banners.set_show_on(off, keep=[], add=[key], allowed={key})
    Banner.objects.filter(pk=off.pk).update(is_active=False)
    past = _banner("Vorbei")
    banners.set_show_on(past, keep=[], add=[key], allowed={key})
    Banner.objects.filter(pk=past.pk).update(ends=datetime.date(2020, 1, 1))
    assert _site("product", p).strip() == ""


def test_templates_place_the_banners():
    for name, call in (
        ("product_detail.html", '{% place_banners "product" product %}'),
        ("service_detail.html", '{% place_banners "service" service %}'),
        ("promotion_detail.html", '{% place_banners "promotion" promotion %}'),
        ("products.html", '{% place_banners "category" current_category %}'),
    ):
        assert call in pathlib.Path("templates/storefront", name).read_text(), name


# ───────────── форма баннера ─────────────


def _post(banner, data, user):
    base = {
        "b_present": "1",
        "b_title": banner.title,
        "b_is_active": "on",
        "b_image_url": "/media/hero/a.jpg",
    }
    request = _req(method="post", data={**base, **data}, user=user)
    return views.banner_edit(request, pk=banner.pk)


def test_form_adds_and_removes_places():
    p = _product()
    b = _banner()
    key = f"product:{p.pk}"
    owner = _user()
    assert _post(b, {"b_show_present": "1", "b_show_add": key}, owner).status_code == 302
    assert Banner.objects.get(pk=b.pk).show_on == [key]
    _post(b, {"b_show_present": "1", "b_show_keep": [key]}, owner)
    assert Banner.objects.get(pk=b.pk).show_on == [key], "отмеченное место остаётся"
    _post(b, {"b_show_present": "1"}, owner)
    assert Banner.objects.get(pk=b.pk).show_on == [], "снятый флажок убирает место"


def test_form_without_the_sentinel_keeps_the_places():
    b = _banner()
    Banner.objects.filter(pk=b.pk).update(show_on=["category:tee"])
    _post(b, {"b_show_add": "category:kaffee"}, _user())
    assert Banner.objects.get(pk=b.pk).show_on == ["category:tee"]


def test_form_shows_the_places_with_their_names():
    p = _product("Darjeeling")
    b = _banner()
    Banner.objects.filter(pk=b.pk).update(show_on=[f"product:{p.pk}"])
    html = views.banner_edit(_req(user=_user()), pk=b.pk).content.decode()
    assert 'name="b_show_present"' in html and 'name="wo"' in html  # R1: поиск страниц
    assert 'name="b_show_keep"' in html and "Darjeeling" in html
    assert reverse("site-banners") in html


def test_auto_placed_banner_has_no_studio_edit_marker():
    p = _product()
    key = f"product:{p.pk}"
    b = _banner("Allein")
    banners.set_show_on(b, keep=[], add=[key], allowed={key})
    html = _site("product", p)
    assert "Allein" in html and "data-sf-media-slot" not in html


def test_cascade_delete_of_categories_frees_their_places():
    src = pathlib.Path("apps/catalog/views.py").read_text()
    cascade = src[src.index("# bulk soft-delete") :][:600]
    assert "move_category_blocks(gone.slug, None)" in cascade
