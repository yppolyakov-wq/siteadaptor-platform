"""KAT-1 (бывш. DS-7): страница категории /sortiment/<slug>/ + тумблер цен в меню.
Лендинг /bereich/ слит в страницу категории; шапку решает Category.page_style.
Планы docs/ds7-category-landings-plan-2026-08-12.md → kat-catalog-structure-plan-2026-08-18.md."""

from importlib import import_module

import pytest
from django.conf import settings as dj_settings
from django.http import Http404
from django.test import RequestFactory

from apps.catalog.models import Category, Product
from apps.promotions import public_views
from apps.tenants import siteconfig
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db


def _req(path="/"):
    request = RequestFactory().get(path)
    request.session = import_module(dj_settings.SESSION_ENGINE).SessionStore()
    return request


def _seed(desc=True, photo=True):
    cat = Category.objects.create(
        name={"de": "Hochzeits-Catering"},
        description={"de": "Ihr Buffet ohne Stress."} if desc else {},
        slug="cl-hochzeit",
        images=[{"id": "i1", "url": "/media/wed.jpg", "is_primary": True}] if photo else [],
    )
    Product.objects.create(
        name={"de": "Hochzeitsbuffet Klassik"},
        description={"de": "Drei Gänge als Buffet"},
        base_price="39.00",
        category=cat,
        is_active=True,
    )
    return cat


def test_normalize_toggles_presence_minimal():
    # KAT-1: тумблер category_landings УМЕР — normalize дропает ключ (прецедент
    # classic_ui); категория всегда страница, шапку решает Category.page_style.
    assert "category_landings" not in siteconfig.normalize({})
    assert "category_landings" not in siteconfig.normalize({"category_landings": True})
    assert "menu_show_prices" not in siteconfig.normalize({})
    assert "menu_show_prices" not in siteconfig.normalize({"menu_show_prices": True})
    assert siteconfig.normalize({"menu_show_prices": False})["menu_show_prices"] is False


def test_category_page_header_by_style_and_content():
    """KAT-1: /sortiment/<slug>/ — шапка (бывший лендинг) рендерится при шаблоне
    kopfbild/sets И контенте; Standard "" — прежний вид фильтра без шапки."""
    cat = _seed()
    req = _req()
    req.tenant = TenantFactory.build()
    # Standard: страница отвечает, шапки нет, товар в сетке есть
    html = public_views.product_list(req, slug=cat.slug).content.decode()
    assert "data-category-header" not in html
    assert "Hochzeitsbuffet Klassik" in html
    assert "Ihr Buffet ohne Stress." in html  # описание — прежним плоским абзацем

    # kopfbild: hero-шапка с фото и описанием; плоский абзац не дублируется
    cat.page_style = "kopfbild"
    cat.save(update_fields=["page_style"])
    req2 = _req()
    req2.tenant = TenantFactory.build()
    html2 = public_views.product_list(req2, slug=cat.slug).content.decode()
    assert "data-category-header" in html2
    assert html2.count("Ihr Buffet ohne Stress.") == 1
    assert "/media/wed.jpg" in html2

    # kopfbild БЕЗ контента (пустая категория) → шапки нет, страница жива
    empty = Category.objects.create(name={"de": "Leer"}, slug="cl-leer", page_style="kopfbild")
    req3 = _req()
    req3.tenant = TenantFactory.build()
    html3 = public_views.product_list(req3, slug=empty.slug).content.decode()
    assert "data-category-header" not in html3

    # неизвестный slug в ПУТИ → 404 (посадочная страница, не redirect)
    req4 = _req()
    req4.tenant = TenantFactory.build()
    with pytest.raises(Http404):
        public_views.product_list(req4, slug="gibts-nicht")


def test_category_page_uuid_never_shadowed():
    """KAT-1: /sortiment/<uuid>/ обязан резолвиться в ДЕТАЛЬ товара, а не в
    категорию (uuid-роут стоит раньше slug-роута)."""
    from django.urls import Resolver404, resolve

    cat = _seed()
    p = Product.objects.get(name__de="Hochzeitsbuffet Klassik")
    try:
        match = resolve(f"/sortiment/{p.pk}/", urlconf="config.urls_tenant")
    except Resolver404:  # pragma: no cover — защита от смены urlconf в тесте
        pytest.fail("uuid-URL не резолвится")
    assert match.url_name == "storefront-product"
    match2 = resolve(f"/sortiment/{cat.slug}/", urlconf="config.urls_tenant")
    assert match2.url_name == "storefront-category"


def test_tiles_link_to_category_page():
    """KAT-1: плитки категорий ведут на /sortiment/<slug>/ — ветвление
    «лендинг vs фильтр» умерло вместе с тумблером."""
    cat = _seed()
    req = _req()
    req.tenant = TenantFactory.build(
        site_config={"sections": [{"key": "categories", "enabled": True}]}
    )
    html = public_views.storefront_home(req).content.decode()
    assert f"/sortiment/{cat.slug}/" in html
    assert "/bereich/" not in html and "?kategorie=" not in html


def test_category_page_includes_child_products():
    """KAT-1: категория-контейнер показывает товары ПРЯМЫХ детей (страница
    родителя без собственных товаров — не пустая сетка под шапкой)."""
    parent = Category.objects.create(name={"de": "Feiern"}, slug="cl-feiern")
    child = Category.objects.create(name={"de": "Geburtstag"}, slug="cl-geb", parent=parent)
    Product.objects.create(
        name={"de": "Geburtstags-Buffet"}, base_price="22.00", category=child, is_active=True
    )
    req = _req()
    req.tenant = TenantFactory.build()
    html = public_views.product_list(req, slug=parent.slug).content.decode()
    assert "Geburtstags-Buffet" in html


def test_category_page_style_preisliste():
    """KAT-1: шаблон «Preisliste» — прайс-вид как per-page дефолт ЭТОЙ категории;
    общий каталог /sortiment/ остаётся на глобальном layout (сетка), а
    ?ansicht= посетителя (MEN-24d) сильнее шаблона категории."""
    cat = _seed()
    cat.page_style = "preisliste"
    cat.save(update_fields=["page_style"])
    req = _req()
    req.tenant = TenantFactory.build()
    html = public_views.product_list(req, slug=cat.slug).content.decode()
    assert "data-price-list data-pl-style" in html
    # per-page дефолт → carry чистый: ?ansicht=preisliste встречается ТОЛЬКО
    # в ссылке самого переключателя видов (href + data-ansicht рядом), а не в
    # carry ссылок категорий/сброса фильтров
    assert html.count('?ansicht=preisliste"') == html.count('?ansicht=preisliste" data-ansicht=')
    # общий каталог не заражается стилем категории
    req2 = _req()
    req2.tenant = TenantFactory.build()
    html2 = public_views.product_list(req2).content.decode()
    assert "data-price-list data-pl-style" not in html2
    # посетитель переключает вид обратно в сетку поверх шаблона категории
    # (cols3 — грид-ссылка тулбара при прайс-владельце; мусор → дефолт страницы)
    req3 = _req(f"/sortiment/{cat.slug}/?ansicht=cols3")
    req3.tenant = TenantFactory.build()
    html3 = public_views.product_list(req3, slug=cat.slug).content.decode()
    assert "data-price-list data-pl-style" not in html3
    assert "Hochzeitsbuffet Klassik" in html3


def test_menu_prices_toggle_browse_only():
    _seed()
    base = {
        "sections": [{"key": "products", "enabled": True, "style": "preisliste"}],
        "menu_show_prices": False,
    }
    # browse-only (orders выключен) → цены скрыты
    t1 = TenantFactory.build(site_config=base, disabled_modules=["orders"])
    r1 = _req()
    r1.tenant = t1
    h1 = public_views.storefront_home(r1).content.decode()
    pl1 = h1[h1.find("data-price-list") : h1.find("data-price-list") + 3000]
    assert "39,00" not in pl1 and "Hochzeitsbuffet Klassik" in pl1
    # продажа активна → PAngV: цены показываются несмотря на ключ
    t2 = TenantFactory.build(site_config=base)
    r2 = _req()
    r2.tenant = t2
    h2 = public_views.storefront_home(r2).content.decode()
    pl2 = h2[h2.find("data-price-list") : h2.find("data-price-list") + 3000]
    assert "39,00" in pl2
