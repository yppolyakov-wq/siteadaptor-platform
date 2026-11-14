"""FB-29.2 S4: баннеры ВЫБИРАЮТСЯ в панели «Seitenaufbau» — у баннера главной и у блока
«Banner»; несколько — слайдер со своими настройками. Правки идут в черновик."""

import pathlib

import pytest

from apps.core import banners, site_schema
from apps.core.modules import default_disabled_for
from apps.core.tests.test_fb27_r2_draft import Browser
from apps.tenants import siteconfig
from apps.tenants.models import Tenant
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _urlconf(settings):
    settings.ROOT_URLCONF = "config.urls_tenant"


def _tenant():
    return TenantFactory(
        business_type="online_shop", disabled_modules=list(default_disabled_for("online_shop"))
    )


def _cfg(tenant):
    return siteconfig.normalize(Tenant.objects.get(pk=tenant.pk).site_config)


def _banner(title="Herbst"):
    return banners.create({"title": title, "image": {"url": f"/media/hero/{title}.jpg"}})


def test_hero_panel_offers_library_banners_as_tiles():
    a = _banner("Herbst")
    b = Browser(_tenant())
    html = b.get("?seite=home&block=hero")
    assert "data-schema-banner-pick" in html
    assert f'value="add:{a.pk}"' in html and "Herbst" in html
    assert "/dashboard/site/banner/" in html  # ссылка «Banner verwalten»


def test_pick_goes_through_the_draft_and_keeps_the_owners_order():
    a, c = _banner("Herbst"), _banner("Winter")
    b = Browser(_tenant())
    b.post(seite="home", ref="hero", pick_op=f"add:{a.pk}")
    b.post(seite="home", ref="hero", pick_op=f"add:{c.pk}")
    assert "hero_banners" not in _cfg(b.tenant), "пока черновик"
    b.post(seite="home", ref="hero", pick_op=f"up:{c.pk}")
    b.post(seite="home", op="save")
    cfg = _cfg(b.tenant)
    assert cfg["hero_banners"]["pick"] == [str(c.pk), str(a.pk)]
    hero = next(s for s in cfg["sections"] if s["key"] == "hero")
    assert "data" not in hero, "выбор хранится в одном месте — `hero_banners`"


def test_remove_and_clear_return_to_the_old_slides():
    a = _banner()
    tenant = _tenant()
    site_schema.apply(tenant, "home", "pick_add", ref="hero", value=str(a.pk))
    assert _cfg(tenant)["hero_banners"]["pick"] == [str(a.pk)]
    site_schema.apply(tenant, "home", "pick_remove", ref="hero", value=str(a.pk))
    assert "hero_banners" not in _cfg(tenant)


def test_only_existing_banners_can_be_picked_and_not_more_than_the_cap():
    tenant = _tenant()
    with pytest.raises(site_schema.SchemaError):
        site_schema.apply(
            tenant, "home", "pick_add", ref="hero", value="3f2b8c1e-5d44-4c0e-9a57-0d2f6a1b7c33"
        )
    for i in range(siteconfig.BANNER_PICK_MAX):
        site_schema.apply(tenant, "home", "pick_add", ref="hero", value=str(_banner(f"B{i}").pk))
    with pytest.raises(site_schema.SchemaError):
        site_schema.apply(tenant, "home", "pick_add", ref="hero", value=str(_banner("Zuviel").pk))


def test_slider_settings_are_saved_and_untouched_panel_changes_nothing():
    a, c = _banner("Herbst"), _banner("Winter")
    b = Browser(_tenant())
    for banner in (a, c):
        b.post(seite="home", ref="hero", pick_op=f"add:{banner.pk}")
    b.post(seite="home", op="save")
    before = _cfg(b.tenant)
    html = b.get("?seite=home&block=hero")
    assert 'name="f_interval"' in html and 'name="f_arrows"' in html and 'name="f_auto"' in html
    b.post(seite="home", op="update", ref="hero", panel_present="1", f_auto="1", f_interval="6")
    assert "data-schema-draft-note" not in b.get("?seite=home"), "без правок черновика нет"
    b.post(
        seite="home", op="update", ref="hero", panel_present="1",
        f_auto="0", f_interval="8", f_arrows="1",
    )  # fmt: skip
    b.post(seite="home", op="save")
    cfg = _cfg(b.tenant)
    assert cfg["hero_banners"] == {
        "pick": before["hero_banners"]["pick"], "auto": False, "interval": 8, "arrows": True,
    }  # fmt: skip


def test_banner_block_picks_from_the_library_too():
    a = _banner()
    tenant = _tenant()
    ref = site_schema.apply(tenant, "text", "add", block_type="banner")
    b = Browser(tenant)
    assert "data-schema-banner-pick" in b.get(f"?seite=text&block={ref}")
    b.post(seite="text", ref=ref, pick_op=f"add:{a.pk}")
    b.post(seite="text", op="save")
    block = next(x for x in _cfg(tenant)["page_blocks"]["info"] if x.get("id") == ref)
    assert block["data"]["pick"] == [str(a.pk)]


def test_row_summary_counts_picked_banners():
    a, c = _banner("Herbst"), _banner("Winter")
    tenant = _tenant()
    for banner in (a, c):
        site_schema.apply(tenant, "home", "pick_add", ref="hero", value=str(banner.pk))
    html = Browser(tenant).get("?seite=home")
    row = html[html.index('data-schema-block="hero"') :]
    assert "2 Folien" in row[: row.index("</a>")]


def test_storefront_slider_reads_the_settings():
    tpl = pathlib.Path("templates/storefront/sections/_hero_slider.html").read_text()
    assert "data-hero-interval" in tpl and "data-hero-auto" in tpl and "data-hero-prev" in tpl
    js = pathlib.Path("templates/storefront/sections/_banner_slider_script.html").read_text()
    assert "dataset.heroInterval" in js and "6000" not in js.replace("|| 6", "")


def test_studio_points_to_the_library_instead_of_its_own_slide_manager():
    tpl = pathlib.Path("templates/tenant/site_home.html").read_text()
    assert "site-banners" in tpl


def test_banner_block_with_several_banners_becomes_a_slider():
    from django.template.loader import render_to_string
    from django.test import RequestFactory

    a, c = _banner("Herbst"), _banner("Winter")
    request = RequestFactory().get("/")
    request.tenant = _tenant()
    block = {"pick": [str(a.pk), str(c.pk)], "interval": 8, "arrows": True}
    html = render_to_string(
        "storefront/sections/_block_banner.html", {"block": block, "request": request}
    )
    assert html.count("data-hero-slide") >= 2 and 'data-hero-interval="8"' in html
    assert "data-hero-prev" in html and "Herbst" in html and "Winter" in html
    one = render_to_string(
        "storefront/sections/_block_banner.html",
        {"block": {"pick": [str(a.pk)]}, "request": request},
    )
    assert "data-hero-slider" not in one and "Herbst" in one


def test_pick_is_visible_in_the_panel_before_saving():
    """Браузерная проверка поймала: выбор уходил в черновик, но панель его не показывала."""
    a = _banner()
    b = Browser(_tenant())
    b.post(seite="home", ref="hero", pick_op=f"add:{a.pk}")
    html = b.get("?seite=home&block=hero")
    assert f'data-schema-banner-item="{a.pk}"' in html
    assert f'value="add:{a.pk}"' not in html, "выбранный баннер не предлагается второй раз"


@pytest.mark.parametrize("style", ["plain", "split", "fullscreen", "bento"])
def test_picked_banners_show_as_a_slider_with_any_hero_style(style):
    """Браузерная проверка поймала: при виде «Split» выбранные баннеры не показывались."""
    from django.template.loader import render_to_string
    from django.test import RequestFactory

    a, c = _banner("Herbst"), _banner("Winter")
    tenant = _tenant()
    cfg = siteconfig.normalize(
        {**(tenant.site_config or {}), "hero_style": style,
         "hero_banners": {"pick": [str(a.pk), str(c.pk)]}}
    )  # fmt: skip
    request = RequestFactory().get("/")
    request.tenant = tenant
    html = render_to_string("storefront/sections/_hero.html", {"site": cfg, "request": request})
    assert html.count("data-hero-slide") >= 2 and "Herbst" in html and "Winter" in html
