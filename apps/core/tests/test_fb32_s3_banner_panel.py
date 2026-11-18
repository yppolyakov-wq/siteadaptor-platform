"""FB-32 S3: баннер в панели «Seitenaufbau» — «Ein Banner / Slider» и «＋ Neuer Banner»
без ухода со страницы (решение владельца 2026-11-17, макет S3)."""

import pytest

from apps.core import banner_views
from apps.core.tests.test_fb27_r2_draft import Browser
from apps.core.tests.test_fb29_banner_pick import _banner, _cfg, _tenant
from apps.tenants import siteconfig

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _urlconf(settings):
    settings.ROOT_URLCONF = "config.urls_tenant"


def _two(b):
    a, c = _banner("Herbst"), _banner("Winter")
    b.post(seite="home", ref="hero", pick_op=f"add:{a.pk}")
    b.post(seite="home", ref="hero", pick_op=f"add:{c.pk}")
    return a, c


def test_single_mode_shows_the_first_banner_without_slider_settings():
    b = Browser(_tenant())
    _two(b)
    html = b.get("?seite=home&block=hero")
    assert "data-schema-banner-show" in html and "data-schema-slider" in html
    b.post(seite="home", op="update", ref="hero", panel_present="1", f_single="1")
    html = b.get("?seite=home&block=hero")
    assert "data-schema-slider" not in html, "у одного баннера настроек слайдера нет"
    b.post(seite="home", op="save")
    choice = _cfg(b.tenant)["hero_banners"]
    assert choice["single"] is True and len(choice["pick"]) == 2, "остальные остаются выбранными"
    b.post(seite="home", op="update", ref="hero", panel_present="1", f_single="0")
    b.post(seite="home", op="save")
    assert "single" not in _cfg(b.tenant)["hero_banners"]


def test_switching_the_mode_keeps_the_arrows_setting():
    b = Browser(_tenant())
    _two(b)
    b.post(
        seite="home",
        op="update",
        ref="hero",
        panel_present="1",
        f_auto="1",
        f_interval="6",
        f_arrows="1",
    )
    b.post(seite="home", op="update", ref="hero", panel_present="1", f_single="1")
    b.post(seite="home", op="save")
    assert _cfg(b.tenant)["hero_banners"].get("arrows") is True


def test_hero_slides_in_single_mode_is_just_the_first():
    from types import SimpleNamespace

    from apps.tenants.templatetags.siteui import hero_slides

    a, c = _banner("Herbst"), _banner("Winter")
    ctx = {"request": SimpleNamespace(tenant=None)}
    pick = [str(a.pk), str(c.pk)]
    assert len(hero_slides(ctx, [], {"pick": pick})) == 2
    one = hero_slides(ctx, [], {"pick": pick, "single": True})
    assert [s["title"] for s in one] == ["Herbst"]
    assert siteconfig.clean_banner_choice({"pick": pick, "single": "0"}).get("single") is None


def test_new_banner_from_the_panel_lands_in_the_library_and_in_the_draft_pick():
    from apps.core.models import Banner

    b = Browser(_tenant())
    # владелец 2026-11-18: в панели баннер не создаётся — только выбор из библиотеки;
    # путь «из редактора баннера обратно в схему» (`schema_seite`) остаётся
    html = b.get("?seite=home&block=hero")
    assert "data-schema-banner-new" not in html and 'action="/dashboard/site/banner' not in html
    req = b._request(
        "post",
        {
            "schema_seite": "home",
            "schema_ref": "hero",
            "b_title": "Neu im Herbst",
            "b_is_active": "1",
        },
    )
    resp = banner_views._save(req, None)
    assert resp.status_code == 302 and "/dashboard/site/aufbau/" in resp["Location"]
    assert "block=hero" in resp["Location"]
    new = Banner.objects.get(title="Neu im Herbst")
    assert "hero_banners" not in _cfg(b.tenant), "в черновик, не сразу на сайт"
    b.post(seite="home", op="save")
    assert _cfg(b.tenant)["hero_banners"]["pick"] == [str(new.pk)]


def test_empty_new_banner_goes_back_to_the_panel_with_an_error():
    from apps.core.models import Banner

    b = Browser(_tenant())
    req = b._request("post", {"schema_seite": "home", "schema_ref": "hero"})
    resp = banner_views._save(req, None)
    assert resp.status_code == 302 and "block=hero" in resp["Location"]
    assert not Banner.objects.exists()


def test_add_button_opens_the_library_list():
    _banner("Herbst"), _banner("Winter")
    b = Browser(_tenant())
    html = b.get("?seite=home&block=hero")
    add = html[html.index("data-schema-banner-add") :]
    add = add[: add.index("</details>")]
    assert "Banner hinzufügen" in add and add.count('name="pick_op" value="add:') == 2
