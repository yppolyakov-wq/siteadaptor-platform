"""FB-31 P4 R8: характеризация страниц «Team» и «Galerie» ДО ★ (вид как «nur hier»).

Обновить (осознанно): FB31P4_GOLDEN=update uv run pytest <этот файл>
"""

import os
from pathlib import Path

import pytest
from django.contrib.messages.middleware import MessageMiddleware
from django.contrib.sessions.middleware import SessionMiddleware
from django.test import RequestFactory

from apps.promotions import public_views
from apps.promotions.tests.test_fb31p3_promo_golden import _normalize
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db
GOLDEN = Path(__file__).parent / "golden_fb31p4"
UPDATE = os.environ.get("FB31P4_GOLDEN") == "update"
TEAM = [{"name": "Anna", "role": "Meisterin", "photo": ""}, {"name": "Ben", "role": "Azubi"}]
GALLERY = [{"url": f"/media/g{i}.jpg"} for i in (1, 2, 3)]
TEXT = {"key": "text", "id": "t-tg", "data": {"title": "Über uns", "body": "Seit 1999"}}


@pytest.fixture(autouse=True)
def _urlconf(settings):
    settings.ROOT_URLCONF = "config.urls_tenant"


def _check(name, html):
    path = GOLDEN / f"{name}.html"
    got = _normalize(html)
    if UPDATE or not path.exists():
        if not UPDATE:
            pytest.fail(f"нет снимка {path.name}: FB31P4_GOLDEN=update")
        GOLDEN.mkdir(exist_ok=True)
        path.write_text(got)
        return
    assert got == path.read_text(), f"страница изменилась: {path.name}"


def _render(view, cfg):
    tenant = TenantFactory.build(name="Salon X", site_config=cfg)
    req = RequestFactory().get("/")
    SessionMiddleware(lambda r: None).process_request(req)
    MessageMiddleware(lambda r: None).process_request(req)
    req.tenant = tenant
    return view(req).content.decode()


def _cfg(key, style, blocks):
    cfg = {"team": TEAM} if key == "team" else {"gallery": GALLERY}
    cfg["sections"] = [{"key": key, "enabled": True, **({"style": style} if style else {})}]
    if blocks:
        cfg["page_blocks"] = {key: [TEXT]}
    return cfg


@pytest.mark.parametrize("blocks", [False, True], ids=["plain", "blocks"])
@pytest.mark.parametrize("style", ["", "circles", "list", "compact", "duo"])
def test_team_page_looks_as_before(style, blocks):
    html = _render(public_views.team_page, _cfg("team", style, blocks))
    _check(f"team-{style or 'standard'}-{'blocks' if blocks else 'plain'}", html)


@pytest.mark.parametrize("blocks", [False, True], ids=["plain", "blocks"])
@pytest.mark.parametrize("style", ["", "strip", "large", "polaroid", "soft"])
def test_gallery_page_looks_as_before(style, blocks):
    html = _render(public_views.gallery_page, _cfg("gallery", style, blocks))
    _check(f"gallery-{style or 'standard'}-{'blocks' if blocks else 'plain'}", html)


# ── R8: ★ своей страницы ──


def test_page_view_beats_the_home_section_view_and_home_is_untouched():
    cfg = _cfg("team", "circles", False)
    cfg["page_blocks"] = {"team": [{"key": "main", "style": "duo"}]}
    html = _render(public_views.team_page, cfg)
    want = _render(public_views.team_page, _cfg("team", "duo", False))
    assert _normalize(html) == _normalize(want), "вид страницы = вид «duo»"
    from apps.tenants import siteconfig

    sections = siteconfig.normalize(cfg)["sections"]
    assert next(s for s in sections if s["key"] == "team")["style"] == "circles"


def test_explicit_like_home_keeps_the_home_view():
    cfg = _cfg("gallery", "strip", False)
    cfg["page_blocks"] = {"gallery": [{"key": "main", "style": "raster"}]}
    html = _render(public_views.gallery_page, cfg)
    # ревью R8: «Wie auf der Startseite» явно = вид секции главной («strip»), не обычная сетка
    _check("gallery-strip-plain", html)


def test_panel_offers_the_section_views_and_saves_them():
    from apps.core import site_schema
    from apps.core.tests.test_fb27_r2_draft import Browser
    from apps.tenants import siteconfig

    tenant = TenantFactory(site_config={"team": TEAM})
    rows = site_schema.blocks_for(siteconfig.normalize(tenant.site_config), "team")
    main = next(r for r in rows if r["main"])
    assert [c[0] for c in main["mainview"]["choices"]] == [
        "raster",
        "circles",
        "list",
        "compact",
        "duo",
    ]
    b = Browser(tenant)
    b.post(seite="team", op="mainview", ref="main", value="list")
    b.post(seite="team", op="save")
    tenant.refresh_from_db()
    blocks = siteconfig.normalize(tenant.site_config)["page_blocks"]["team"]
    assert {"key": "main", "style": "list"} in blocks
