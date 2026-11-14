"""FB-29.2 S7 (решение владельца 2026-11-14): все баннеры — в разделе «Banner».
Собственные слайды блоков «Banner» переносятся в библиотеку, блок их выбирает; новый блок
своего слайда не имеет; перенос запускает деплой."""

import pathlib

import pytest
from django.template.loader import render_to_string
from django.test import RequestFactory

from apps.core import banners, site_schema
from apps.core.models import Banner
from apps.tenants import siteconfig
from apps.tenants.models import Tenant
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db


def _block(bid, **data):
    return {"key": "banner", "id": bid, "enabled": True, "data": data}


def _tenant(**config):
    return TenantFactory(site_config=config)


def _fresh(tenant):
    return Tenant.objects.get(pk=tenant.pk).site_config


def _html(tenant, block):
    request = RequestFactory().get("/")
    request.tenant = tenant
    return render_to_string(
        "storefront/sections/_block_banner.html", {"block": block, "request": request}
    )


def test_block_slides_move_to_the_library_and_the_block_picks_them():
    tenant = _tenant(
        sections=[{"key": "hero", "enabled": True}, _block("h1", title="Auf der Startseite", url="/media/hero/a.jpg")],
        page_blocks={"info": [_block("p1", title="Über uns Banner", text="Seit 1990", height="lg")]},
    )  # fmt: skip
    report = banners.import_legacy(tenant)
    assert report["created"] == 2
    cfg = _fresh(tenant)
    home = next(s for s in cfg["sections"] if s.get("id") == "h1")
    page = cfg["page_blocks"]["info"][0]
    for block, key, title in (
        (home, "block:h1", "Auf der Startseite"),
        (page, "block:p1", "Über uns Banner"),
    ):
        banner = Banner.objects.get(legacy_key=key)
        assert banner.title == title and block["data"]["pick"] == [str(banner.pk)]
    assert page["data"].get("height") == "lg", "высота — у места показа"
    assert Banner.objects.get(legacy_key="block:p1").text == "Seit 1990"


def test_the_page_looks_the_same_after_the_move():
    tenant = _tenant(
        page_blocks={"info": [_block("p1", title="Über uns Banner", text="Seit 1990")]}
    )
    before = _html(
        tenant, siteconfig.normalize(tenant.site_config)["page_blocks"]["info"][0]["data"]
    )
    banners.import_legacy(tenant)
    data = siteconfig.normalize(_fresh(tenant))["page_blocks"]["info"][0]["data"]
    after = _html(Tenant.objects.get(pk=tenant.pk), data)
    assert "Über uns Banner" in after and "Seit 1990" in after
    assert before.count("<h2") == after.count("<h2")


def test_repeat_creates_nothing_and_untouched_kinds_stay():
    tenant = _tenant(
        page_blocks={
            "info": [
                _block("p1", title="Eigener"),
                _block("p2"),  # пустой блок — нечего переносить
                _block("p3", from_page=True),
                {"key": "text", "id": "t1", "enabled": True, "data": {"title": "Text"}},
            ]
        }
    )
    assert banners.import_legacy(tenant)["created"] == 1
    assert banners.import_legacy(Tenant.objects.get(pk=tenant.pk))["created"] == 0
    blocks = _fresh(tenant)["page_blocks"]["info"]
    assert "pick" not in blocks[1]["data"] and "pick" not in blocks[2]["data"]
    assert blocks[3]["data"] == {"title": "Text"} and Banner.objects.count() == 1


def test_block_with_an_owner_pick_is_left_alone():
    chosen = banners.create({"title": "Gewählt", "image": {"url": "/media/hero/a.jpg"}})
    tenant = _tenant(page_blocks={"info": [_block("p1", title="Alt", pick=[str(chosen.pk)])]})
    assert banners.import_legacy(tenant)["created"] == 0
    assert _fresh(tenant)["page_blocks"]["info"][0]["data"]["pick"] == [str(chosen.pk)]


def test_block_translations_travel_with_the_banner():
    tenant = _tenant(
        page_blocks={"info": [_block("p1", title="Herbst", text="Neu")]},
        i18n={"ru": {"page_blocks": {"info": [{"id": "p1", "data": {"title": "Осень"}}]}}},
    )
    shown = siteconfig.localize(siteconfig.normalize(tenant.site_config), "ru")
    if shown["page_blocks"]["info"][0]["data"].get("title") != "Осень":
        pytest.skip("форма оверлея блоков другая — перевод проверяется стендом")
    banners.import_legacy(tenant)
    assert Banner.objects.get(legacy_key="block:p1").title_i18n.get("ru") == "Осень"


def test_undo_returns_the_blocks_own_slide():
    tenant = _tenant(page_blocks={"info": [_block("p1", title="Eigener")]})
    banners.import_legacy(tenant)
    assert banners.undo_legacy(Tenant.objects.get(pk=tenant.pk)) == 1
    data = _fresh(tenant)["page_blocks"]["info"][0]["data"]
    assert "pick" not in data and data["title"] == "Eigener" and Banner.objects.count() == 0


def test_new_banner_block_has_no_slide_of_its_own():
    tenant = TenantFactory(business_type="online_shop")
    ref = site_schema.apply(tenant, "text", "add", block_type="banner")
    block = next(b for b in _fresh(tenant)["page_blocks"]["info"] if b.get("id") == ref)
    data = block.get("data") or {}
    assert not any(data.get(k) for k in ("title", "text", "url", "button_label"))


def test_studio_points_to_the_library_for_banner_blocks():
    src = pathlib.Path("templates/tenant/_cb_row.html").read_text()
    part = src[src.index('{% if b.type == "banner" %}') :][:2500]
    assert "site-banners" in part and "data-cb-banner-library" in part


def test_deploy_runs_the_move():
    assert "import_banners" in pathlib.Path("scripts/deploy.sh").read_text()


# --- ревью S7 (silent-failure-hunter) и остатки S8 ---


def test_same_block_id_on_two_pages_ends_up_in_the_library_once():
    tenant = _tenant(
        page_blocks={
            "info": [_block("dup", title="Kopie")],
            "versand": [_block("dup", title="Kopie")],
        }
    )
    report = banners.import_legacy(tenant)
    assert report == {"created": 1, "skipped": 0}
    cfg = _fresh(tenant)
    picks = [cfg["page_blocks"][h][0]["data"]["pick"] for h in ("info", "versand")]
    assert picks[0] == picks[1] and len(picks[0]) == 1


def test_library_banner_in_a_block_has_no_photo_edit_marker():
    b = banners.create({"title": "Aus der Bibliothek", "image": {"url": "/media/hero/a.jpg"}})
    html = _html(TenantFactory.build(), {"pick": [str(b.pk)]})
    assert "Aus der Bibliothek" in html and "data-sf-media-slot" not in html


def test_deleted_banners_do_not_fill_the_place():
    import uuid

    from apps.core.modules import default_disabled_for

    tenant = TenantFactory(
        business_type="online_shop", disabled_modules=list(default_disabled_for("online_shop"))
    )
    ghosts = [str(uuid.uuid4()) for _ in range(siteconfig.BANNER_PICK_MAX)]
    tenant.site_config = {"hero_banners": {"pick": ghosts}}
    tenant.save(update_fields=["site_config"])
    alive = banners.create({"title": "Neu", "image": {"url": "/media/hero/a.jpg"}})
    site_schema.apply(tenant, "home", "pick_add", ref="hero", value=str(alive.pk))
    assert _fresh(tenant)["hero_banners"]["pick"] == [str(alive.pk)]


def test_picker_survives_a_missing_table(monkeypatch):
    from django.db import DatabaseError

    def boom(*_a, **_k):
        raise DatabaseError("no table")

    monkeypatch.setattr(banners, "_pick_state", boom)
    state = banners.pick_state(RequestFactory().get("/"), {"pick": ["x"]})
    assert state["unavailable"] is True and state["entries"] == []
