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
    # MEN-22: матчим МАРКАП-форму маркера — голый "data-price-list" теперь есть
    # на каждой странице как строка селектора в _grid_view_script.html.
    _seed_products()
    tenant = TenantFactory.build(site_config={"sections": [{"key": "products", "enabled": True}]})
    html = _render_home(tenant)
    assert 'data-grid="products"' in html
    assert "data-price-list data-pl-style" not in html


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
    # MEN-22: маркап-форма маркера (см. test_home_section_default_grid_unchanged).
    _seed_products()
    tenant = TenantFactory.build()
    html = _render_catalog(tenant)
    assert 'data-grid="catalog"' in html
    assert "data-price-list data-pl-style" not in html


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


# ── MEN-22: посетительский переключатель вида (список / с фото / 2 колонки) ──


def test_visitor_toggle_on_base_views_with_photos_always_in_dom():
    """У базовых видов (plain/foto/2sp/3sp) рендерится переключатель и data-plv;
    фото ВСЕГДА в DOM (класс plv-img) — в «plain» скрыты классом hidden."""
    _seed_products()
    p = Product.objects.get(name__de="Buffet Vegetarisch")
    p.images = [{"id": "x1", "url": "/media/demo/buffet.webp", "alt": {}}]
    p.save(update_fields=["images"])
    tenant = TenantFactory.build(
        site_config={"sections": [{"key": "products", "enabled": True, "style": "preisliste"}]}
    )
    html = _render_home(tenant)
    assert 'data-plv="plain"' in html and 'data-plv-key="products"' in html
    assert "data-plv-btn" in html  # кнопки переключателя
    assert 'class="plv-img w-10 h-10 rounded-lg object-cover shrink-0 hidden"' in html
    # классы целевых видов лежат в data-cls-* (JIT/purge-safe)
    assert 'data-cls-cols="grid md:grid-cols-2 gap-x-10 gap-y-6"' in html

    # фото-вид стартует с видимыми фото (без hidden)
    tenant2 = TenantFactory.build(
        site_config={
            "sections": [{"key": "products", "enabled": True, "style": "preisliste_foto_2sp"}]
        }
    )
    html2 = _render_home(tenant2)
    assert 'data-plv="cols"' in html2
    assert 'class="plv-img w-10 h-10 rounded-lg object-cover shrink-0"' in html2


def test_visitor_toggle_absent_for_authored_views():
    """kompakt/karte/buch/2sp — авторские виды: переключателя нет. Ревью MEN-22:
    2sp (колонки без фото) не совпадает ни с одним состоянием переключателя —
    стартовое «plain» врало, клик по активной кнопке рушил md:columns-2."""
    _seed_products()
    for style in ("preisliste_kompakt", "preisliste_karte", "preisliste_buch", "preisliste_2sp"):
        tenant = TenantFactory.build(
            site_config={"sections": [{"key": "products", "enabled": True, "style": style}]}
        )
        html = _render_home(tenant)
        # маркап-форма атрибутов: голые имена есть в JS _grid_view_script.html
        assert 'data-plv-btn="' not in html, style
        assert 'data-plv="' not in html, style


def test_catalog_page_uses_server_side_view_links():
    """MEN-24d (переписан осознанно с MEN-22): на СТРАНИЦЕ каталога вид
    посетителя — серверные ссылки ?ansicht= (работают при любом стиле владельца,
    вкл. karte/buch), class-swap-механика главной там выключена (pl_page):
    ни data-plv-атрибутов, ни узкого max-w-2xl у прайс-контейнера."""
    _seed_products()
    tenant = TenantFactory.build(site_config={"catalog_layout": {"preset": "preisliste"}})
    html = _render_catalog(tenant)
    # маркап-форма (грабля MEN-22: голые имена атрибутов есть в JS-селекторах)
    assert 'data-plv-key="catalog"' not in html and 'data-plv="plain"' not in html
    assert 'data-ansicht="preisliste_foto"' in html  # ссылки видов у сортировки
    assert 'data-ansicht="cols3"' in html  # «Kacheln» — карточная сетка
    assert 'aria-current="page"' in html  # активный вид подсвечен
    # полная ширина: узкий кап снят у прайс-контейнера
    container = html.split("data-price-list")[0].rsplit("<div", 1)[-1]
    assert "max-w-2xl" not in container and "max-w-none" in container


def test_catalog_ansicht_overrides_owner_preset_and_carries():
    """MEN-24d: ?ansicht= подменяет пресет владельца (мусор → вид владельца);
    выбранный вид переживает ссылки чипов/пагинации (carry)."""
    _seed_products()
    tenant = TenantFactory.build(site_config={"catalog_layout": {"preset": "preisliste_karte"}})
    html = _render_catalog(tenant, "?ansicht=preisliste_foto")
    assert 'data-pl-style="preisliste_foto"' in html
    assert "ansicht=preisliste_foto" in html  # carry в ссылках
    junk = _render_catalog(tenant, "?ansicht=junk")
    assert 'data-pl-style="preisliste_karte"' in junk  # мусор → вид владельца
    grid = _render_catalog(tenant, "?ansicht=cols3")
    assert 'data-grid="catalog"' in grid  # карточная сетка — штатная ветка


def test_cols_target_classes_follow_owner_style():
    """Ревью MEN-22: data-cls-cols обязан вернуть ИМЕННО стартовые классы вида —
    у foto_3sp клик по активной «2 колонки» не должен ронять xl:grid-cols-3."""
    _seed_products()
    tenant = TenantFactory.build(
        site_config={
            "sections": [{"key": "products", "enabled": True, "style": "preisliste_foto_3sp"}]
        }
    )
    html = _render_home(tenant)
    assert 'data-cls-cols="grid md:grid-cols-2 xl:grid-cols-3 gap-x-8 gap-y-6"' in html


# ── MEN-24: маркировка / вид «Kacheln» / кап строк ───────────────────────────


def test_menu_labels_render_with_key_and_food_type_only():
    """MEN-24a: пиктограммы диет + буквенные сноски аллергенов (схема PDF) —
    только при включённом menu_labels И гастро-типе; легенда — по встреченным."""
    _seed_products()
    p = Product.objects.get(name__de="Buffet Vegetarisch")
    p.diets = ["vegan"]
    p.allergens = ["gluten", "eier"]
    p.save(update_fields=["diets", "allergens"])
    cfg = {
        "sections": [{"key": "products", "enabled": True, "style": "preisliste"}],
        "menu_labels": True,
    }
    html = _render_home(TenantFactory.build(business_type="catering", site_config=cfg))
    assert "🌱" in html  # эмодзи диеты (title = метка)
    assert "<sup" in html and ">ac</sup>" in html  # буквы gluten=a, eier=c
    assert "a</b> = " in html  # легенда «a = Glutenhaltiges Getreide …»

    # без ключа — чисто (дефолт ВЫКЛ)
    off = dict(cfg)
    off.pop("menu_labels")
    html_off = _render_home(TenantFactory.build(business_type="catering", site_config=off))
    assert "<sup" not in html_off and "🌱" not in html_off
    # не-гастро тип — чисто даже с ключом
    html_tech = _render_home(TenantFactory.build(business_type="services", site_config=cfg))
    assert "<sup" not in html_tech


def test_menu_labels_normalize_presence_minimal():
    cfg = siteconfig.normalize({"menu_labels": True})
    assert cfg["menu_labels"] is True
    assert "menu_labels" not in siteconfig.normalize({})
    assert "menu_labels" not in siteconfig.normalize({"menu_labels": False})


def test_visitor_toggle_has_grid_state():
    """MEN-24b: 4-я кнопка «Kacheln» (сетка 2–4) + классы контейнера в data-cls-grid;
    вёрстку карточек даёт CSS-каскад [data-plv="grid"] в app.css."""
    _seed_products()
    tenant = TenantFactory.build(
        site_config={"sections": [{"key": "products", "enabled": True, "style": "preisliste"}]}
    )
    html = _render_home(tenant)
    assert 'data-plv-btn="grid"' in html
    assert 'data-cls-grid="max-w-none"' in html and 'data-gcls-grid=""' in html


def test_section_rows_cap_and_mehr_anzeigen():
    """MEN-24c: rows секции режет строки на группу (тег), кнопка под списком
    меняет подпись на «Mehr anzeigen»; без rows — прежняя «Ganze Speisekarte»."""
    _seed_products()
    cat = Category.objects.get(slug="pl-buffets")
    for i in range(3):
        Product.objects.create(
            name={"de": f"Extra {i}"}, base_price="5.00", category=cat, is_active=True
        )
    capped = TenantFactory.build(
        site_config={
            "sections": [{"key": "products", "enabled": True, "style": "preisliste", "rows": 2}]
        }
    )
    html = _render_home(capped)
    assert "Mehr anzeigen" in html and "Ganze Speisekarte" not in html
    assert "Buffet Vegetarisch" in html and "Extra 2" not in html  # хвост срезан

    uncapped = TenantFactory.build(
        site_config={"sections": [{"key": "products", "enabled": True, "style": "preisliste"}]}
    )
    html2 = _render_home(uncapped)
    assert "Ganze Speisekarte" in html2 and "Mehr anzeigen" not in html2
    assert "Extra 2" in html2


def test_section_rows_normalize_clamped_presence_minimal():
    row = next(
        s
        for s in siteconfig.normalize(
            {"sections": [{"key": "products", "enabled": True, "rows": 99}]}
        )["sections"]
        if s["key"] == "products"
    )
    assert row["rows"] == 20  # кламп
    bare = next(
        s
        for s in siteconfig.normalize({"sections": [{"key": "products", "enabled": True}]})[
            "sections"
        ]
        if s["key"] == "products"
    )
    assert "rows" not in bare  # presence-minimal — golden целы


def test_food_label_translations_are_identity_in_de():
    """MEN-24a (стенд нашёл «c = Eigentümer»): DeepL-коротыши в .po коверкали
    LMIV-метки — Eier→Eigentümer, Soja→Soldat, Halal→Wahl, Bio→Biografie.
    Немецкие msgid реестров food обязаны рендериться в de КАК ЕСТЬ."""
    from django.utils import translation

    from apps.catalog.food import ADDITIVES, ALLERGENS, DIETS

    labels = (
        [lb for _c, lb in ALLERGENS] + [lb for _c, lb, _i in DIETS] + [lb for _c, lb in ADDITIVES]
    )
    with translation.override(None):  # msgid как написан в реестре
        raw = [str(lb) for lb in labels]
    with translation.override("de"):
        rendered = [str(lb) for lb in labels]
    assert rendered == raw, [p for p in zip(raw, rendered, strict=True) if p[0] != p[1]]
