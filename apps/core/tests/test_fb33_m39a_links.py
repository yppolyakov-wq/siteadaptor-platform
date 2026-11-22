"""FB-33 M3-9a: строки «Seitenaufbau» не ведут в 404 и не предлагают страниц, которых
посетитель не откроет (дефекты стенда владельца M3-9 №1–3, №5, №7, №8)."""

import pathlib
import re

import polib
import pytest
from django.urls import resolve

from apps.catalog.models import Category, Combo
from apps.core import page_settings, site_schema
from apps.tenants import siteconfig
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db

ROOT = pathlib.Path(__file__).resolve().parents[3]


@pytest.fixture(autouse=True)
def _urlconf(settings):
    settings.ROOT_URLCONF = "config.urls_tenant"


def _tenant(**kw):
    kw.setdefault("disabled_modules", [])
    return TenantFactory(slug="m39a", name="M39a", **kw)


def _rows(tenant):
    config = siteconfig.normalize(tenant.site_config)
    return {r.code: r for _label, rows in site_schema.type_groups(tenant, config) for r in rows}


# --- №1: превью «Alle Kategorien» -------------------------------------------------------


def test_all_categories_preview_opens_the_category_page():
    Category.objects.create(name="Brot", slug="brot", is_active=True)
    row = _rows(_tenant())["category"]
    assert row.preview_url == "/sortiment/brot/"
    # адрес по pk ловил маршрут ТОВАРА (`sortiment/<uuid:pk>/`) → 404
    assert resolve(row.preview_url).url_name == "storefront-category"


def test_all_categories_preview_is_empty_without_categories():
    assert _rows(_tenant())["category"].preview_url == ""


# --- №2: «Team» только у бизнеса с командой ---------------------------------------------


def test_team_page_is_offered_only_with_a_team():
    bare = _tenant()
    assert not page_settings.type_active(bare, "team")
    assert "team" not in _rows(bare)
    with pytest.raises(site_schema.SchemaError):
        site_schema.resolve(bare, "team")


def test_team_page_is_offered_with_a_team():
    tenant = _tenant(site_config={"team": [{"name": "Anna", "role": "Meisterin"}]})
    assert siteconfig.normalize(tenant.site_config).get("team")
    assert page_settings.type_active(tenant, "team")
    assert "team" in _rows(tenant)
    assert site_schema.resolve(tenant, "team")[1] == "team"


# --- №3: «Versand» только при заказах ---------------------------------------------------


def test_versand_is_offered_with_orders():
    tenant = _tenant()
    assert tenant.is_module_active("orders")
    assert "text@versand" in _rows(tenant)
    assert site_schema.resolve(tenant, "text@versand")[1] == "versand"


def test_versand_is_not_offered_without_orders():
    tenant = _tenant(disabled_modules=["orders"])
    assert not tenant.is_module_active("orders")
    rows = _rows(tenant)
    assert "text@versand" not in rows
    assert "text" in rows  # «Über uns» остаётся
    with pytest.raises(site_schema.SchemaError):
        site_schema.resolve(tenant, "text@versand")
    with pytest.raises(site_schema.SchemaError):  # и POST в обход экрана
        site_schema.apply(tenant, "text@versand", "add", block_type="text")


# --- №8: «Sets & Menüs» без наборов — не строка, каким бы ни был summaries ------------


@pytest.mark.parametrize("summaries", [True, False])
def test_sets_row_only_with_combos(summaries):
    config = siteconfig.normalize(_tenant().site_config)
    keys = [b["key"] for b in site_schema.blocks_for(config, "catalog", summaries=summaries)]
    assert siteconfig.CATALOG_SETS_KEY not in keys
    Combo.objects.create(name="Menü A", price="15.00", is_active=True)
    keys = [b["key"] for b in site_schema.blocks_for(config, "catalog", summaries=summaries)]
    assert siteconfig.CATALOG_SETS_KEY in keys


# --- №7: «Button-Lösung» переведён, цитата кнопки § 312j — нет -------------------------


@pytest.mark.parametrize("lang", ["ru", "uk", "en", "tr"])
def test_button_loesung_is_translated(lang):
    po = polib.pofile(str(ROOT / "locale" / lang / "LC_MESSAGES" / "django.po"))
    entries = [e for e in po if "(Button-Lösung)" in e.msgid and not e.obsolete]
    assert len(entries) == 4
    for entry in entries:
        assert entry.msgstr, entry.msgid[:60]
        assert "Button-Lösung" not in entry.msgstr, entry.msgstr
        assert "§ 312j" in entry.msgstr
        # подпись кнопки закреплена законом — цитируется дословно
        quote = (
            "Zahlungspflichtig buchen"
            if "buchen“" in entry.msgid
            else "Zahlungspflichtig bestellen"
        )
        assert quote in entry.msgstr, entry.msgstr


# --- №5: акция на 390 px — колонки сетки сжимаются до экрана ---------------------------


@pytest.mark.parametrize("col", ["media", "info"])
def test_promo_detail_columns_can_shrink(col):
    """Стенд (hotel, ru, 390): ссылка «Gilt für» с обрезаемым названием (`truncate` —
    одной строкой) раздвигала колонку сетки до 402 px: у элемента сетки минимальная ширина
    по умолчанию — по содержимому. `min-w-0` снимает её — обрезка начинает работать."""
    html = (ROOT / "templates" / "storefront" / "promotion_detail.html").read_text()
    tag = re.search(rf'<div class="([^"]*)" data-promo-col="{col}"', html)
    assert tag and "min-w-0" in tag.group(1).split()


# --- ревью: строка, которой у бизнеса нет, не роняет экран (адрес из закладки, старая вкладка)


def _screen(method, tenant, data=None, query=""):
    from types import SimpleNamespace

    from django.contrib.messages.middleware import MessageMiddleware
    from django.contrib.sessions.middleware import SessionMiddleware
    from django.test import RequestFactory

    from apps.core.site_schema_views import site_schema_view

    req = getattr(RequestFactory(), method)("/dashboard/site/aufbau/" + query, data or {})
    SessionMiddleware(lambda r: None).process_request(req)
    MessageMiddleware(lambda r: None).process_request(req)
    req.user = SimpleNamespace(is_authenticated=True)
    req.tenant = tenant
    return site_schema_view(req)


_GONE = [("text@versand", {"disabled_modules": ["orders"]}), ("team", {})]
_POSTS = [
    {"op": "add", "type": "text"},
    {"op": "toggle", "ref": "pagetext"},
    {"op": "save"},
    {"op": "revert", "ref": "pagetext"},
    {"op": "discard"},
    {"op": "setting", "name": "text_width", "value": "wide"},
    {"zu_tab": "wie", "ref": "pagetext"},
]


@pytest.mark.parametrize(("code", "kw"), _GONE, ids=[c for c, _ in _GONE])
def test_screen_survives_a_row_the_business_does_not_have(code, kw):
    tenant = _tenant(**kw)
    before = dict(tenant.site_config or {})
    for query in (f"?seite={code}", f"?seite={code}&block=pagetext", f"?seite={code}&block=__page"):
        assert _screen("get", tenant, query=query).status_code in (200, 302), query
    for data in _POSTS:
        resp = _screen("post", tenant, {"seite": code, **data})
        assert resp.status_code in (200, 302), data
    tenant.refresh_from_db()
    assert (tenant.site_config or {}) == before  # ничего не записано
