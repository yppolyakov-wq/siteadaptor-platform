"""DL-16.2 — /aktionen/: A3 группы-слайдеры, A4 вид «Liste», A5 поиск + группа + «Sie sparen»."""

from __future__ import annotations

import re
from datetime import timedelta
from importlib import import_module

import pytest
from django.conf import settings as dj_settings
from django.test import RequestFactory
from django.utils import timezone

from apps.promotions import public_views
from apps.promotions.models import Promotion
from apps.tenants import siteconfig
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db


def _get(view, path, tenant):
    request = RequestFactory().get(path)
    request.session = import_module(dj_settings.SESSION_ENGINE).SessionStore()
    request.tenant = tenant
    return view(request).content.decode()


def _seed(n_a=3, n_b=3):
    for i in range(n_a):
        Promotion.objects.create(
            title={"de": f"A{i}"},
            status="active",
            group="Wochenangebote",
            discount_percent=20,
            compare_at_price="2.50",
        )
    for i in range(n_b):
        Promotion.objects.create(title={"de": f"B{i}"}, status="active", group="Räumung")


def test_promo_layout_presence_minimal():
    assert siteconfig.normalize_promo_layout("slider") == "slider"
    assert siteconfig.normalize_promo_layout("garbage") == ""
    assert "promo_layout" not in siteconfig.normalize({})
    assert siteconfig.normalize({"promo_layout": "slider"})["promo_layout"] == "slider"
    assert "promo_layout" not in siteconfig.normalize({"promo_layout": "x"})


def test_groups_default_grid_unchanged_and_slider_mode_strips():
    tenant = TenantFactory(schema_name="public", slug="dl162a", name="A", disabled_modules=[])
    _seed()
    html = _get(public_views.promotion_list, "/aktionen/", tenant)
    assert "data-promo-strip" not in html
    assert 'data-grid="promo_list" class="grid grid-cols-2' in html
    assert "Alle anzeigen" not in html  # в сетке ссылки «Alle» у секций нет (как было)
    tenant.site_config = {"promo_layout": "slider"}
    tenant.save()
    html = _get(public_views.promotion_list, "/aktionen/", tenant)
    strips = re.findall(r'<div data-grid="promo_list" data-promo-strip[^>]*data-sf-slider>', html)
    assert len(strips) == 2
    assert 'href="?gruppe=Wochenangebote"' in html and 'href="?gruppe=R%C3%A4umung"' in html
    # внутри секции чип группы на карточке не дублируется
    assert "data-promo-group" not in html


def test_time_mode_slider_more_links_only_for_heute_and_woche():
    tenant = TenantFactory(
        schema_name="public",
        slug="dl162b",
        name="B",
        disabled_modules=[],
        site_config={"promo_grouping": "time", "promo_layout": "slider"},
    )
    now = timezone.now()
    Promotion.objects.create(title={"de": "H"}, status="active", ends_at=now + timedelta(hours=2))
    Promotion.objects.create(title={"de": "D"}, status="active")  # dauerhaft
    html = _get(public_views.promotion_list, "/aktionen/", tenant)
    assert 'href="?endet=heute"' in html
    assert "?endet=dauerhaft" not in html and "?endet=laenger" not in html


def test_list_view_is_flat_table_and_toggle_carries_params():
    tenant = TenantFactory(schema_name="public", slug="dl162c", name="C", disabled_modules=[])
    _seed()
    html = _get(public_views.promotion_list, "/aktionen/?ansicht=liste&sort=endet", tenant)
    assert "data-promo-table" in html
    assert html.count("data-promo-row") == 6
    assert "data-promo-strip" not in html and 'data-grid="promo_list" class="grid' not in html
    assert "data-ending-soon" not in html
    # тумблер: «Karten» = тот же URL без ansicht, «Liste» активна
    assert 'href="?sort=endet" data-ansicht="karten"' in html
    assert 'data-ansicht="liste" aria-current="page"' in html
    # незнакомый вид игнорируется
    html = _get(public_views.promotion_list, "/aktionen/?ansicht=zzz", tenant)
    assert "data-promo-table" not in html and 'data-grid="promo_list" class="grid' in html


def test_search_form_and_savings_and_group_chip_on_cards():
    tenant = TenantFactory(schema_name="public", slug="dl162d", name="D", disabled_modules=[])
    _seed(n_b=0)
    Promotion.objects.create(
        title={"de": "Mys"},
        status="active",
        discount_style="mystery",
        discount_percent=50,
        compare_at_price="10.00",
    )
    html = _get(public_views.promotion_list, "/aktionen/", tenant)
    assert "data-promo-search" in html and 'name="q"' in html
    # секция Wochenangebote (3) + «More offers» (mystery без группы)
    assert html.count("data-savings") == 3  # mystery молчит
    # плоская выдача при фильтре — чип группы виден
    html = _get(public_views.promotion_list, "/aktionen/?sort=endet", tenant)
    assert html.count("data-promo-group") == 3
    assert "data-savings" in html


def test_panel_saves_layout_presence_minimal(settings):
    from types import SimpleNamespace

    from django.contrib.messages.middleware import MessageMiddleware
    from django.contrib.sessions.middleware import SessionMiddleware

    from apps.promotions import views

    settings.ROOT_URLCONF = "config.urls_tenant"
    tenant = TenantFactory(
        schema_name="public", slug="dl162e", name="E", site_config={"seo": {"x": 1}}
    )
    for layout, expect in (("slider", "slider"), ("", None), ("zzz", None)):
        req = RequestFactory().post("/promotions/page-mode/", {"mode": "", "layout": layout})
        SessionMiddleware(lambda r: None).process_request(req)
        MessageMiddleware(lambda r: None).process_request(req)
        req.user = SimpleNamespace(is_authenticated=True)
        req.tenant = tenant
        assert views.promotion_page_mode(req).status_code == 302
        tenant.refresh_from_db()
        assert tenant.site_config.get("promo_layout") == expect, (layout, tenant.site_config)
        assert tenant.site_config.get("seo") == {"x": 1}  # targeted-write
