"""DL-21.2 — шаблоны ОБЗОРНОЙ страницы акций `/aktionen/`: группы играют роль
подкатегорий, акции — товаров. Ключ `promo_page_style` (top-level, presence-minimal,
как `promo_layout`). Замки написаны ДО правок.

План — `docs/dl21-root-and-overview-templates-plan-2026-09-03.md` §3.2.
"""

from datetime import timedelta
from decimal import Decimal

import pytest
from django.test import RequestFactory
from django.utils import timezone

from apps.promotions import group_styles, public_views
from apps.promotions.models import Promotion
from apps.tenants import siteconfig
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _tenant_urlconf(settings):
    settings.ROOT_URLCONF = "config.urls_tenant"


def _promo(title, group="Wochenangebote", days=3, **kw):
    kw.setdefault("status", "active")
    kw.setdefault("promo_type", "discount")
    kw.setdefault("price_override", Decimal("2.49"))
    kw.setdefault("compare_at_price", Decimal("3.49"))
    kw.setdefault("ends_at", timezone.now() + timedelta(days=days) if days else None)
    return Promotion.objects.create(title={"de": title}, group=group, **kw)


def _seed(groups=("Wochenangebote", "Räumung"), per_group=2):
    for g in groups:
        for i in range(per_group):
            _promo(f"{g} {i}", group=g)


def _render(style="", cfg=None, **params):
    tenant = TenantFactory.build()
    config = dict(cfg or {})
    if style:
        config["promo_page_style"] = style
    tenant.site_config = config
    request = RequestFactory().get("/aktionen/", params)
    request.tenant = tenant
    request.session = {}
    return public_views.promotion_list(request).content.decode()


# ─────────────────────────── реестр и ключ ───────────────────────────


def test_overview_registry_has_the_nine_layouts():
    keys = [k for k, _l, _h in group_styles.PROMO_PAGE_STYLES]
    assert keys[0] == ""
    for k in (
        "kopfbild",
        "preisliste",
        "regale",
        "tabs",
        "schaufenster",
        "navigator",
        "magazin",
        "kompakt",
    ):
        assert k in keys, k
    assert "mosaik" not in keys  # бенто режет цену/срок на малых плитках — не обещаем
    assert "sets" not in keys  # у акций нет наборов


def test_overview_key_is_presence_minimal_and_validated():
    assert "promo_page_style" not in siteconfig.normalize({})
    assert "promo_page_style" not in siteconfig.normalize({"promo_page_style": "erfunden"})
    assert siteconfig.normalize({"promo_page_style": "tabs"})["promo_page_style"] == "tabs"


# ─────────────────────────── рендер ───────────────────────────


def test_overview_standard_is_unchanged():
    _seed()
    body = _render()
    assert "data-promo-page" not in body
    assert '<section class="mb-8">' in body  # секции групп как раньше


def test_kopfbild_adds_a_banner_with_counts():
    _seed()
    body = _render("kopfbild", cfg={"hero_image": "/static/x.jpg"})
    assert 'data-promo-page="kopfbild"' in body
    assert "data-promo-head" in body
    assert "/static/x.jpg" in body


def test_preisliste_is_the_table_by_default_but_visitor_can_switch_back():
    _seed()
    body = _render("preisliste")
    assert "<table" in body and '<section class="mb-8">' not in body
    body2 = _render("preisliste", ansicht="karten")
    assert '<section class="mb-8">' in body2


def test_regale_puts_every_group_on_a_strip_regardless_of_the_threshold():
    _seed(("Wochenangebote", "Räumung", "Solo"), per_group=1)  # порог 2 не пройден
    body = _render("regale")
    assert body.count("data-promo-strip") == 3


def test_tabs_show_all_plus_groups():
    _seed()
    body = _render("tabs")
    assert "data-promo-tabs" in body
    assert body.count("data-listing-nav") >= 3


def test_schaufenster_features_the_first_offer():
    _seed()
    body = _render("schaufenster")
    assert "data-promo-hero" in body


def test_navigator_has_a_side_column_with_groups_and_chips():
    _seed()
    body = _render("navigator")
    assert "data-promo-side" in body
    side = body[body.index("data-promo-side") :]
    assert "Wochenangebote" in side[: side.index('data-grid="promo_list"')]


def test_magazin_and_kompakt():
    _seed()
    assert 'data-group-item="magazin"' in _render("magazin")
    body = _render("kompakt")
    assert "data-promo-index" in body and 'data-group-grid="prospekt"' in body


def test_list_view_still_silences_every_overview_layout():
    _seed()
    for style in ("kopfbild", "regale", "tabs", "schaufenster", "navigator", "magazin"):
        body = _render(style, ansicht="liste")
        assert "<table" in body and "data-promo-strip" not in body, style


@pytest.mark.parametrize("style", [k for k, _l, _h in group_styles.PROMO_PAGE_STYLES if k])
def test_every_overview_layout_survives_an_empty_page(style):
    body = _render(style)
    assert f'data-promo-page="{style}"' in body


def test_cabinet_panel_saves_the_overview_template():
    from django.contrib.auth import get_user_model
    from django.contrib.messages.middleware import MessageMiddleware
    from django.contrib.sessions.middleware import SessionMiddleware

    from apps.promotions import views

    tenant = TenantFactory(schema_name="public", slug="dl21c", name="DL21C")

    def _req(method, data=None):
        r = getattr(RequestFactory(), method)("/promotions/", data or {})
        SessionMiddleware(lambda x: None).process_request(r)
        MessageMiddleware(lambda x: None).process_request(r)
        r.user = get_user_model()(is_active=True)
        r.tenant = tenant
        return r

    assert views.promotion_page_mode(_req("post", {"page_style": "regale"})).status_code == 302
    tenant.refresh_from_db()
    assert siteconfig.normalize(tenant.site_config)["promo_page_style"] == "regale"
    views.promotion_page_mode(_req("post", {"page_style": ""}))
    tenant.refresh_from_db()
    assert "promo_page_style" not in siteconfig.normalize(tenant.site_config)
