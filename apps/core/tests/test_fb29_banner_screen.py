"""FB-29.2 S2: экран «Website → Banner» — библиотека плитками, форма, удаление с вопросом."""

import pathlib

import pytest
from django.urls import reverse

from apps.core import banner_views as views
from apps.core import banners
from apps.core.models import Banner, Membership
from apps.core.tests.test_m21_6_content_pages import _req, _user
from apps.tenants import siteconfig
from apps.tenants.models import Tenant
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _urlconf(settings):
    settings.ROOT_URLCONF = "config.urls_tenant"


def _banner(**kwargs):
    fields = {"title": "Herbsttee", "image": {"url": "/media/banner/a.jpg", "path": "banner/a.jpg"}}
    fields.update(kwargs)
    return banners.create(fields)


def _staff(perms=()):
    from django.contrib.auth import get_user_model

    user = get_user_model().objects.create_user(username="staff-b", password="pw1234567")
    Membership.objects.create(
        user=user, role=Membership.ROLE_STAFF, permissions={"remove": ["website.edit"]}
    )
    return user


def test_list_shows_tiles_and_a_new_button():
    _banner(title="Herbsttee")
    _banner(title="Wintertee", is_active=False)
    html = views.banner_list(_req(user=_user())).content.decode()
    assert html.count("data-banner-tile=") == 2
    assert "Herbsttee" in html and "Wintertee" in html
    assert reverse("site-banner-new") in html
    assert "ui-btn-danger" not in html  # красных кнопок в списке нет


def test_empty_library_explains_what_to_do():
    html = views.banner_list(_req(user=_user())).content.decode()
    assert "data-banner-empty" in html and reverse("site-banner-new") in html


def test_search_narrows_the_list():
    _banner(title="Herbsttee")
    _banner(title="Sommerfest")
    html = views.banner_list(_req(path="/x/?q=sommer", user=_user())).content.decode()
    assert "Sommerfest" in html and "Herbsttee" not in html


def test_create_takes_only_whitelisted_fields():
    resp = views.banner_new(
        _req(
            method="post",
            user=_user(),
            data={
                "b_title": "Neu",
                "b_text": "Text",
                "b_btn_label": "Los",
                "b_btn_url": "javascript:alert(1)",
                "b_image_url": "/media/banner/x.jpg",
                "b_is_active": "on",
                "sort_order": "99",
                "legacy_key": "heroes:0",
            },
        )
    )
    assert resp.status_code == 302
    b = Banner.objects.get()
    assert b.title == "Neu" and b.button_url == "" and b.is_active is True
    assert b.sort_order == 0 and b.legacy_key == ""


def test_empty_banner_is_not_created_and_the_form_says_why():
    resp = views.banner_new(_req(method="post", user=_user(), data={"b_title": ""}))
    assert resp.status_code == 200 and not Banner.objects.exists()
    assert 'role="alert"' in resp.content.decode()


def test_broken_date_keeps_the_typed_values():
    resp = views.banner_new(
        _req(method="post", user=_user(), data={"b_title": "Neu", "b_starts": "2026-13-45"})
    )
    html = resp.content.decode()
    assert resp.status_code == 200 and not Banner.objects.exists()
    assert 'value="Neu"' in html and 'role="alert"' in html


def test_edit_changes_the_banner_and_can_switch_it_off():
    b = _banner()
    resp = views.banner_edit(
        _req(method="post", user=_user(), data={"b_title": "Wintertee", "b_present": "1"}), pk=b.pk
    )
    assert resp.status_code == 302
    b.refresh_from_db()
    assert b.title == "Wintertee" and b.is_active is False  # галочка снята
    assert b.image.get("path") == "banner/a.jpg", "фото остаётся, если новое не загружено"


def test_untouched_edit_form_changes_nothing():
    owner = _user()
    from apps.core.tests.test_fb27_design_tabs import _Form

    b = _banner(text="Frisch", link="", align="left", starts="2026-01-01")
    before = Banner.objects.filter(pk=b.pk).values().get()
    html = views.banner_edit(_req(user=owner), pk=b.pk).content.decode()
    form = _Form()
    form.feed(html.replace("data-banner-form", "data-design-form"))
    views.banner_edit(_req(method="post", user=owner, data=dict(form.fields)), pk=b.pk)
    after = Banner.objects.filter(pk=b.pk).values().get()
    before.pop("updated_at"), after.pop("updated_at")
    assert after == before


def test_delete_needs_a_confirmation_step():
    owner = _user()
    b = _banner()
    html = views.banner_delete(_req(user=owner), pk=b.pk).content.decode()
    assert Banner.objects.filter(pk=b.pk).exists(), "GET ничего не удаляет"
    assert "data-banner-confirm" in html
    resp = views.banner_delete(_req(method="post", user=owner), pk=b.pk)
    assert resp.status_code == 302 and not Banner.objects.filter(pk=b.pk).exists()


def test_delete_removes_the_banner_from_every_place_that_picked_it():
    tenant = TenantFactory(business_type="online_shop")
    keep, gone = _banner(title="Bleibt"), _banner(title="Weg")
    cfg = siteconfig.normalize(tenant.site_config)
    cfg["hero_banners"] = {"pick": [str(gone.pk), str(keep.pk)]}
    tenant.site_config = cfg
    tenant.save(update_fields=["site_config"])
    assert banners.places(Tenant.objects.get(pk=tenant.pk), gone)
    views.banner_delete(_req(method="post", user=_user(), tenant=tenant), pk=gone.pk)
    cfg = Tenant.objects.get(pk=tenant.pk).site_config
    assert cfg["hero_banners"]["pick"] == [str(keep.pk)]


def test_staff_without_edit_right_cannot_write():
    b = _banner()
    user = _staff(perms=["website.view"])
    assert (
        views.banner_new(_req(method="post", user=user, data={"b_title": "X"})).status_code == 403
    )
    assert (
        views.banner_edit(
            _req(method="post", user=user, data={"b_title": "X"}), pk=b.pk
        ).status_code
        == 403
    )
    assert views.banner_delete(_req(method="post", user=user), pk=b.pk).status_code == 403
    b.refresh_from_db()
    assert b.title == "Herbsttee" and Banner.objects.count() == 1


def test_screen_is_in_the_website_menu_and_has_route_rules():
    from apps.core import nav_registry, view_perms

    names = {"site-banners", "site-banner-new", "site-banner-edit", "site-banner-delete"}
    assert names <= set(view_perms.RULES)
    assert any(e.url_name == "site-banners" for e in nav_registry.ENTRIES)
    tpl = pathlib.Path("templates/tenant/banners.html").read_text()
    assert "nav_title" in tpl
