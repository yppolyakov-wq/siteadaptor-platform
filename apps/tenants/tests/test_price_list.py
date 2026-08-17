"""DS-3a (Fokus): «прайс-лист» — вид вывода товаров (секция главной + страница
каталога). План docs/ds3-fokus-output-views-plan-2026-08-12.md. Замки: нормализация
extra-пресета (только каталог), рендер строк/групп, характеризация «без стиля —
прежняя сетка», гейт PDF-чипа."""

from importlib import import_module

import pytest
from django.conf import settings as dj_settings
from django.test import RequestFactory

from apps.catalog.models import Category, Product
from apps.promotions import public_views
from apps.tenants import siteconfig
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db


def _render_home(tenant):
    request = RequestFactory().get("/")
    request.session = import_module(dj_settings.SESSION_ENGINE).SessionStore()
    request.tenant = tenant
    return public_views.storefront_home(request).content.decode()


def _render_catalog(tenant, query=""):
    request = RequestFactory().get(f"/sortiment/{query}")
    request.session = import_module(dj_settings.SESSION_ENGINE).SessionStore()
    request.tenant = tenant
    return public_views.product_list(request).content.decode()


def _seed_products():
    cat = Category.objects.create(name={"de": "Buffets"}, slug="pl-buffets", sort_order=1)
    cat2 = Category.objects.create(name={"de": "Getränke"}, slug="pl-drinks", sort_order=2)
    Product.objects.create(
        name={"de": "Buffet Vegetarisch"},
        description={"de": "Drei Gänge mit Salaten"},
        base_price="24.00",
        category=cat,
        is_active=True,
    )
    Product.objects.create(
        name={"de": "Saftpaket"}, base_price="9.00", category=cat2, is_active=True
    )
    Product.objects.create(name={"de": "Ohne Kategorie"}, base_price="3.00", is_active=True)


def test_normalize_catalog_accepts_preisliste_only_there():
    cfg = siteconfig.normalize({"catalog_layout": {"preset": "preisliste"}})
    assert cfg["catalog_layout"]["preset"] == "preisliste"
    # мусор по-прежнему падает в дефолт
    assert (
        siteconfig.normalize({"catalog_layout": {"preset": "junk"}})["catalog_layout"]["preset"]
        == "cols3"
    )
    # у соседних страниц extra-вид НЕ валиден (пикеры его и не предлагают)
    assert (
        siteconfig.normalize({"stay_index_layout": {"preset": "preisliste"}})["stay_index_layout"][
            "preset"
        ]
        != "preisliste"
    )
    # LAYOUT_PRESETS не раздут — «preisliste» живёт только в PAGE_EXTRA_PRESETS
    assert "preisliste" not in siteconfig.LAYOUT_PRESETS
    # DS-5b/5c + MEN-14: семейство прайс-видов (две последние — фотосписок в колонки)
    assert siteconfig.PAGE_EXTRA_PRESETS["catalog_layout"] == (
        "preisliste",
        "preisliste_foto",
        "preisliste_kompakt",
        "preisliste_2sp",
        "preisliste_foto_2sp",
        "preisliste_foto_3sp",
        "preisliste_karte",
        "preisliste_buch",
    )


def test_products_section_style_survives_normalize():
    cfg = siteconfig.normalize(
        {"sections": [{"key": "products", "enabled": True, "style": "preisliste"}]}
    )
    row = next(s for s in cfg["sections"] if s["key"] == "products")
    assert row["style"] == "preisliste"
    junk = siteconfig.normalize(
        {"sections": [{"key": "products", "enabled": True, "style": "junk"}]}
    )
    assert next(s for s in junk["sections"] if s["key"] == "products").get("style", "") == ""


def test_home_section_price_list_renders_groups_and_rows():
    _seed_products()
    tenant = TenantFactory.build(
        site_config={"sections": [{"key": "products", "enabled": True, "style": "preisliste"}]}
    )
    html = _render_home(tenant)
    assert "data-price-list" in html
    assert "Buffets" in html and "Getränke" in html
    assert "Buffet Vegetarisch" in html and "Drei Gänge" in html
    assert "Weitere" in html  # безкатегорийные — в конце, своей группой
    assert "Ganze Speisekarte" in html
    # карточная сетка секции НЕ рендерится
    assert 'data-grid="products"' not in html


def test_home_section_default_grid_unchanged():
    # Характеризация: без стиля — прежняя карточная сетка (байт-семантика вида).
    _seed_products()
    tenant = TenantFactory.build(site_config={"sections": [{"key": "products", "enabled": True}]})
    html = _render_home(tenant)
    assert 'data-grid="products"' in html
    assert "data-price-list" not in html


def test_catalog_page_preisliste_groups_and_facets_alive():
    _seed_products()
    tenant = TenantFactory.build(site_config={"catalog_layout": {"preset": "preisliste"}})
    html = _render_catalog(tenant)
    assert "data-price-list" in html
    assert 'data-grid="catalog"' not in html
    assert "Buffet Vegetarisch" in html
    # поиск (?q=) продолжает фильтровать выдачу — провайдер UB не тронут
    filtered = _render_catalog(tenant, "?q=Saftpaket")
    assert "Saftpaket" in filtered and "Buffet Vegetarisch" not in filtered


def test_catalog_page_default_grid_unchanged():
    _seed_products()
    tenant = TenantFactory.build()
    html = _render_catalog(tenant)
    assert 'data-grid="catalog"' in html
    assert "data-price-list" not in html


# ── DS-5c: семейство прайс-видов (компакт / две колонки / классическая карта) ──


@pytest.mark.parametrize(
    "style",
    [
        "preisliste",
        "preisliste_foto",
        "preisliste_kompakt",
        "preisliste_2sp",
        "preisliste_karte",
        "preisliste_foto_2sp",
        "preisliste_foto_3sp",
        "preisliste_buch",
    ],
)
def test_all_price_styles_valid_and_render(style):
    _seed_products()
    cfg = siteconfig.normalize({"sections": [{"key": "products", "enabled": True, "style": style}]})
    assert next(s for s in cfg["sections"] if s["key"] == "products")["style"] == style
    html = _render_home(TenantFactory.build(site_config=cfg))
    assert f'data-pl-style="{style}"' in html
    # и как страничный пресет каталога
    page = siteconfig.normalize({"catalog_layout": {"preset": style}})
    assert page["catalog_layout"]["preset"] == style


def test_preisliste_foto_renders_thumbs():
    # Фикс DS-7: p.image_url не существовал у Product — фото молча пропадали.
    _seed_products()
    prod = Product.objects.get(name__de="Buffet Vegetarisch")
    prod.images = [{"id": "i1", "url": "/media/buffet.jpg", "is_primary": True}]
    prod.save(update_fields=["images"])
    html = _render_home(
        TenantFactory.build(
            site_config={
                "sections": [{"key": "products", "enabled": True, "style": "preisliste_foto"}]
            }
        )
    )
    assert 'src="/media/buffet.jpg"' in html


def test_price_style_variants_differ():
    _seed_products()

    def render(style):
        return _render_home(
            TenantFactory.build(
                site_config={"sections": [{"key": "products", "enabled": True, "style": style}]}
            )
        )

    kompakt = render("preisliste_kompakt")
    assert "Drei Gänge" not in kompakt  # компакт прячет описания
    zwei = render("preisliste_2sp")
    assert "md:columns-2" in zwei and "break-inside-avoid" in zwei
    karte = render("preisliste_karte")
    assert "Drei Gänge" in karte  # карта держит описание (курсивом под блюдом)
    assert "tracking-[0.18em]" in karte  # центр-заголовок группы


def test_photo_price_lists_in_columns():
    """MEN-14: фотосписок в 2/3 колонки — фото на месте, мобильный в одну колонку."""
    _seed_products()
    prod = Product.objects.get(name__de="Buffet Vegetarisch")
    prod.images = [{"id": "i1", "url": "/media/buffet.jpg", "is_primary": True}]
    prod.save(update_fields=["images"])

    def render(style):
        return _render_home(
            TenantFactory.build(
                site_config={"sections": [{"key": "products", "enabled": True, "style": style}]}
            )
        )

    zwei = render("preisliste_foto_2sp")
    assert 'src="/media/buffet.jpg"' in zwei  # фото не теряются в колоночном виде
    assert "grid md:grid-cols-2" in zwei
    drei = render("preisliste_foto_3sp")
    assert 'src="/media/buffet.jpg"' in drei
    assert "xl:grid-cols-3" in drei
    # мобильный — одна колонка: сетка включается только с md+ (строка «фото +
    # название + цена» в две колонки на телефоне нечитаема)
    for html in (zwei, drei):
        block = html.split("data-price-list")[0].rsplit("<div", 1)[-1]
        assert "grid-cols-2" not in block.replace("md:grid-cols-2", "")


def test_menu_book_pages_and_progressive_enhancement():
    """MEN-16: «меню-книга» — каждая группа страницей, навигация листания есть,
    но БЕЗ JS все страницы видны (атрибут hidden только на навигации)."""
    _seed_products()
    html = _render_home(
        TenantFactory.build(
            site_config={
                "sections": [{"key": "products", "enabled": True, "style": "preisliste_buch"}]
            }
        )
    )
    assert "data-price-book" in html
    assert html.count("data-book-page") >= 3  # три группы = три страницы
    assert "data-book-nav" in html and "data-book-prev" in html and "data-book-next" in html
    # содержимое доступно без скрипта: страницы не помечены hidden в разметке
    assert "data-book-page hidden" not in html
    assert "Buffet Vegetarisch" in html and "Saftpaket" in html
    # скрипт листания подключается ТОЛЬКО этим видом
    assert "__sfPriceBookBound" in html
    plain = _render_home(
        TenantFactory.build(
            site_config={"sections": [{"key": "products", "enabled": True, "style": "preisliste"}]}
        )
    )
    assert "__sfPriceBookBound" not in plain and "data-price-book" not in plain


def test_mobile_never_exceeds_two_columns():
    """MEN-14 (требование владельца): на телефоне максимум 2 колонки — у ЛЮБОЙ
    сетки, включая ручной override и плитку в 6 колонок."""
    for preset in siteconfig.LAYOUT_PRESETS:
        lay = siteconfig.normalize_layout({"preset": preset, "mobile": 4})
        assert lay["mobile"] <= 2, preset
        assert "grid-cols-3" not in siteconfig.grid_class_string(lay).split("sm:")[0]


def test_review_findings_locks():
    """DS-5c: замки на находки адверсариального ревью (2026-08-12)."""
    # (1) draft-путь билдера принимает страничные extra-пресеты — паритет с Save
    cfg = siteconfig.normalize({})
    siteconfig.apply_page_payload(cfg, {"catalog_layout": {"preset": "preisliste_karte"}})
    assert cfg["catalog_layout"]["preset"] == "preisliste_karte"
    # (2) у каждого extra-пресета есть метка — селект канвы строит опции из
    # SECTION_STYLE_LABELS (HIGH: без опции браузер слал "list" → откат вида)
    for k in siteconfig.PAGE_EXTRA_PRESETS["catalog_layout"]:
        assert k in siteconfig.SECTION_STYLE_LABELS, k


def test_pages_picker_offers_every_price_view():
    """Ревью MEN-14/16 (HIGH): список опций экрана «Pages» был захардкожен и
    отстал от реестра — сохранённый вид не совпадал ни с одной опцией, браузер
    слал первую («list»), и Save молча откатывал раскладку каталога."""
    import re
    from types import SimpleNamespace

    from django.contrib.messages.middleware import MessageMiddleware
    from django.contrib.sessions.middleware import SessionMiddleware

    from apps.core import views

    request = RequestFactory().get("/dashboard/site/pages/")
    SessionMiddleware(lambda r: None).process_request(request)
    MessageMiddleware(lambda r: None).process_request(request)
    request.user = SimpleNamespace(is_authenticated=True)
    request.tenant = TenantFactory(
        schema_name="public",
        slug="pp",
        name="PP",
        site_config={"catalog_layout": {"preset": "preisliste_buch"}},
    )
    body = views.pages_view(request).content.decode()
    for key in siteconfig.PAGE_EXTRA_PRESETS["catalog_layout"]:
        assert f'value="{key}"' in body, key
    # сохранённый вид отмечен selected — иначе браузер отправит первую опцию
    assert re.search(r'value="preisliste_buch"[^>]*selected', body)


def test_pages_screen_offers_and_saves_service_layout():
    """MEN-18 («не нашёл, где изменить вид услуг»): экран Pages настраивает и
    листинг услуг; пустой выбор «Standard» удаляет ключ (легаси-грид), чужой
    POST без селекта ключ не трогает (класс W0)."""
    from types import SimpleNamespace

    from django.contrib.messages.middleware import MessageMiddleware
    from django.contrib.sessions.middleware import SessionMiddleware

    from apps.core import views

    def _request(method="get", data=None, tenant=None):
        request = getattr(RequestFactory(), method)("/dashboard/site/pages/", data or {})
        SessionMiddleware(lambda r: None).process_request(request)
        MessageMiddleware(lambda r: None).process_request(request)
        request.user = SimpleNamespace(is_authenticated=True)
        request.tenant = tenant
        return request

    tenant = TenantFactory(
        schema_name="public",
        slug="ps",
        name="PS",
        site_config={"service_index_layout": {"preset": "preisliste_foto"}},
    )
    body = views.pages_view(_request(tenant=tenant)).content.decode()
    assert 'name="service_index_preset"' in body
    import re

    assert re.search(r'value="preisliste_foto"[^>]*selected', body)

    # Save с выбранным видом — ключ пишется
    views.pages_view(
        _request(
            "post",
            {"catalog_preset": "cols3", "service_index_preset": "preisliste_2sp"},
            tenant,
        )
    )
    cfg = siteconfig.normalize(tenant.site_config)
    assert cfg["service_index_layout"]["preset"] == "preisliste_2sp"
    # «Standard» (пустое значение) удаляет ключ
    views.pages_view(
        _request("post", {"catalog_preset": "cols3", "service_index_preset": ""}, tenant)
    )
    assert "service_index_layout" not in siteconfig.normalize(tenant.site_config)
    # POST без селекта (модуль booking выключен у другого тенанта) ключ не трогает
    tenant.site_config = {"service_index_layout": {"preset": "preisliste"}}
    views.pages_view(_request("post", {"catalog_preset": "cols3"}, tenant))
    assert siteconfig.normalize(tenant.site_config)["service_index_layout"]["preset"] == (
        "preisliste"
    )
