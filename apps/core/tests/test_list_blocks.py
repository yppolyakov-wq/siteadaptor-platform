"""LB-1: блок «Liste» — ЧТО выводим (источник × фильтр × сортировка × лимит) и КАК
(сетка/лента, колонки, ряды, форма карточки) на любой странице.

План — `docs/lb-list-blocks-plan-2026-10-02.md` §9 (решения владельца §8). Замки
написаны ДО кода. Что запирает файл:

* данные блока — только поля СВОЕГО источника, мусор отброшен, пустое не пишется
  (presence-minimal: golden-эталоны не меняются);
* легаси «Aktionen eines Typs» (PT-6) читается как этот блок на всех трёх входах
  конфига — живые сайты и демо продолжают работать без миграции;
* вид наследуется «блок → тип → страница источника → сайт», а своя форма карточки у
  самого объекта (DL-19) по-прежнему сильнее всех;
* «Alle N →» — только когда показаны не все (правило SF-5), и ведёт туда, где виден
  весь список с ТЕМ ЖЕ фильтром (решение N-4: тип → страница типа);
* карточки акций несут §11 PAngV, число запросов не растёт с числом карточек;
* кодовые поля не уезжают в перевод (класс LAY-6).
"""

import itertools
import re
from datetime import timedelta
from decimal import Decimal

import pytest
from django.contrib.sessions.middleware import SessionMiddleware
from django.db import connection
from django.test import RequestFactory
from django.test.utils import CaptureQueriesContext
from django.utils import timezone

from apps.catalog.models import Category, Product
from apps.promotions import public_views
from apps.promotions.models import Promotion
from apps.tenants import siteconfig
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db

_N = itertools.count()


@pytest.fixture(autouse=True)
def _urlconf(settings):
    settings.ROOT_URLCONF = "config.urls_tenant"


def _block(**data):
    return {"key": "list", "id": f"lb{next(_N)}", "enabled": True, "data": data}


def _tenant(sections=None, **cfg):
    """Тенант, у которого на главной ТОЛЬКО блоки теста: фикс-секции выключены явно,
    иначе секции «Aktionen»/«Produkte» показали бы те же карточки и ассерты по телу
    страницы проверяли бы не блок."""
    # Схема НЕ public: context-processor витрины для public-схемы молчит
    # (`modules_nav` → {}), и карточки рендерились бы без своих переменных
    # (`is_preview`, форма карточки сайта, quick-add) — тест проверял бы не ту витрину.
    t = TenantFactory(slug=f"lbt{next(_N)}", name="LB")
    config = dict(cfg)
    if sections is not None:
        fixed = [{"key": key, "enabled": False} for key, _label, _on in siteconfig.SECTIONS]
        config["sections"] = fixed + list(sections)
    t.site_config = config
    t.save(update_fields=["site_config"])
    return t


def _request(tenant, path="/", params=None):
    req = RequestFactory().get(path, params or {})
    SessionMiddleware(lambda r: None).process_request(req)
    req.tenant = tenant
    return req


def _home(tenant, preview=False):
    req = _request(tenant, "/", {"preview": "1"} if preview else None)
    return public_views.storefront_home(req).content.decode()


def _promo(title, **kw):
    kw.setdefault("promo_type", "discount")
    kw.setdefault("discount_percent", 10)
    return Promotion.objects.create(title={"de": title}, status="active", **kw)


def _cat(name, **kw):
    return Category.objects.create(
        name={"de": name}, slug=kw.pop("slug", None) or name.lower(), **kw
    )


def _product(name, price="4.90", **kw):
    return Product.objects.create(
        name={"de": name}, base_price=Decimal(price), is_active=True, **kw
    )


def _data(cfg, key="list"):
    return [s for s in cfg["sections"] if s.get("key") == key]


def _section(body, marker='data-sf-list="'):
    """Разметка первой секции блока «Liste» (до закрытия секции)."""
    i = body.index(marker)
    start = body.rindex("<section", 0, i)
    return body[start : body.index("</section>", i)]


def _promo_ids(html):
    """Карточки акций в разметке — по уникальным ссылкам на страницу акции."""
    return set(re.findall(r'href="/p/([0-9a-f-]{36})/"', html))


def _all_link(html):
    """Ссылка «Alle N →» в шапке блока или None."""
    m = re.search(r'<a [^>]*data-sf-list-all[^>]*href="([^"]+)"[^>]*>([^<]*)</a>', html)
    return (m.group(1).replace("&amp;", "&"), m.group(2)) if m else None


# ───────────────────────────── данные блока ─────────────────────────────


def test_block_keeps_only_the_fields_of_its_own_source():
    raw = {
        "type": "Räumung",
        "endet": "heute",
        "rabatt": 30,
        "category": "kaese",
        "only": "sale",
        "title": "Restposten",
    }
    promo = siteconfig._clean_cblock_data("list", {"source": "promotions", **raw})
    assert promo == {
        "source": "promotions",
        "type": "Räumung",
        "endet": "heute",
        "rabatt": 30,
        "title": "Restposten",
    }
    prod = siteconfig._clean_cblock_data("list", {"source": "products", **raw})
    assert prod == {
        "source": "products",
        "category": "kaese",
        "only": "sale",
        "title": "Restposten",
    }


def test_block_drops_garbage_and_writes_nothing_empty():
    data = siteconfig._clean_cblock_data(
        "list",
        {
            "source": "products",
            "only": "billig",  # нет такого фильтра
            "sort": "zufall",  # нет такой сортировки у провайдера
            "limit": "viel",
            "title": "  ",
            "intro": "",
            "out": "karussell",
            "cols": "9",
            "rows": "0",
            "card": "coupon",  # форма только для акций
        },
    )
    assert data == {"source": "products"}


def test_view_axes_are_validated_per_kind_of_card():
    promo = siteconfig._clean_cblock_data(
        "list",
        {"source": "promotions", "out": "slider", "cols": "4", "rows": "2", "card": "coupon"},
    )
    assert promo == {
        "source": "promotions",
        "out": "slider",
        "cols": 4,
        "rows": 2,
        "card": "coupon",
    }
    prod = siteconfig._clean_cblock_data("list", {"source": "products", "card": "overlay"})
    assert prod["card"] == "overlay"
    assert "card" not in siteconfig._clean_cblock_data(
        "list", {"source": "promotions", "card": "overlay"}
    )
    # лимит — в границах, а не отбрасывается: «Höchstens 50» значит «как можно больше»
    assert siteconfig._clean_cblock_data("list", {"limit": "50"})["limit"] == 24


def test_sort_keys_come_from_the_facet_provider_of_the_source():
    """Кабинет не должен предлагать сортировку, которую выдача не умеет (правило STU-9)."""
    for key in ("endet", "rabatt", "preis"):
        assert (
            siteconfig._clean_cblock_data("list", {"source": "promotions", "sort": key})["sort"]
            == key
        )
    for key in ("newest", "price_asc", "price_desc", "featured"):
        assert (
            siteconfig._clean_cblock_data("list", {"source": "products", "sort": key})["sort"]
            == key
        )
    assert "sort" not in siteconfig._clean_cblock_data(
        "list", {"source": "promotions", "sort": "price_asc"}
    )


def test_missing_source_reads_as_promotions():
    """Легаси-блок PT-6 источника не знал — его данные {type,title,limit} без поля source."""
    assert siteconfig._clean_cblock_data("list", {"type": "A"}) == {
        "source": "promotions",
        "type": "A",
    }


def test_legacy_promo_list_reads_as_list_on_every_input():
    legacy = {"key": "promo_list", "id": "old1", "data": {"type": "A", "title": "T", "limit": 3}}
    want = {"source": "promotions", "type": "A", "title": "T", "limit": 3}

    cfg = siteconfig.normalize({"sections": [legacy]})
    assert [b["data"] for b in _data(cfg)] == [want]
    assert not _data(cfg, "promo_list")

    cfg = siteconfig.normalize({"page_blocks": {"info": [legacy]}})
    assert cfg["page_blocks"]["info"][0]["key"] == "list"
    assert cfg["page_blocks"]["info"][0]["data"] == want

    cfg = siteconfig.normalize(
        {"block_templates": {"t1": {"key": "promo_list", "data": legacy["data"]}}}
    )
    assert cfg["block_templates"]["t1"]["key"] == "list"
    assert cfg["block_templates"]["t1"]["data"] == want
    # повторный normalize ничего не меняет (идемпотентность)
    again = siteconfig.normalize(siteconfig.normalize({"sections": [legacy]}))
    assert [b["data"] for b in _data(again)] == [want]


def test_two_blocks_of_the_same_source_are_not_merged():
    cfg = siteconfig.normalize(
        {"sections": [_block(source="promotions", title="Erste"), _block(source="promotions")]}
    )
    assert len(_data(cfg)) == 2


def test_block_is_allowed_on_every_page_host():
    """Класс «молча выпал»: блок обязан жить на каждой странице с блоками."""
    for host in siteconfig.PAGE_BLOCK_HOSTS:
        cfg = siteconfig.normalize({"page_blocks": {host: [_block(source="products")]}})
        assert cfg["page_blocks"][host][0]["key"] == "list", host


def test_code_fields_never_travel_into_a_translation():
    """Смена источника/фильтра в редакторе на ru — структура, а не перевод (LAY-6)."""
    for name in ("source", "endet", "category", "only", "sort", "out", "card", "type"):
        assert not siteconfig._is_translatable_field(name), name
    for name in ("title", "intro"):
        assert siteconfig._is_translatable_field(name), name


# ───────────────────────────── выборка: акции ─────────────────────────────


def test_promotions_of_one_type_only():
    t = _tenant([_block(source="promotions", type="Räumung")])
    _promo("Restposten Käse", group="Räumung")
    _promo("Wochenknaller", group="Wochenangebote")
    sec = _section(_home(t))
    assert "Restposten Käse" in sec and "Wochenknaller" not in sec
    assert 'data-sf-promo-type="Räumung"' in sec


def test_promotions_without_a_type_are_all_promotions():
    """У нового блока «нет фильтра» = «всё» (осознанно иначе, чем у легаси PT-6)."""
    t = _tenant([_block(source="promotions")])
    _promo("Eins", group="Räumung")
    _promo("Zwei")
    sec = _section(_home(t))
    assert "Eins" in sec and "Zwei" in sec


def test_garbage_type_renders_nothing_but_the_page_lives():
    t = _tenant([_block(source="promotions", type="sys:erfunden")])
    _promo("Irgendwas")
    body = _home(t)
    assert 'data-sf-list="' not in body


def test_ending_today_and_minimum_discount_filters():
    now = timezone.now()
    end_of_day = timezone.localtime(now).replace(hour=23, minute=59, second=59, microsecond=0)
    today = now + (end_of_day - now) / 2
    t = _tenant(
        [
            _block(source="promotions", endet="heute", title="Heute"),
            _block(source="promotions", rabatt=30, title="Stark"),
        ]
    )
    _promo("Läuft heute aus", ends_at=today)
    _promo("Läuft in drei Tagen aus", ends_at=now + timedelta(days=3))
    _promo("Kräftig reduziert", discount_percent=40)
    body = _home(t)
    first = _section(body)
    assert "Läuft heute aus" in first and "Läuft in drei Tagen aus" not in first
    second = _section(body[body.index(first) + len(first) :])
    assert "Kräftig reduziert" in second and "Läuft heute aus" not in second


def test_sorting_by_discount():
    t = _tenant([_block(source="promotions", sort="rabatt")])
    _promo("Klein", discount_percent=10)
    _promo("Groß", discount_percent=50)
    sec = _section(_home(t))
    assert sec.index("Groß") < sec.index("Klein")


# ───────────────────────────── выборка: товары ─────────────────────────────


def test_products_of_a_category_include_its_direct_children():
    root = _cat("Käse", slug="kaese")
    child = _cat("Hartkäse", slug="hartkaese", parent=root)
    other = _cat("Brot", slug="brot")
    _product("Bergkäse", category=child)
    _product("Feta", category=root)
    _product("Roggenbrot", category=other)
    t = _tenant([_block(source="products", category="kaese")])
    sec = _section(_home(t))
    assert "Bergkäse" in sec and "Feta" in sec and "Roggenbrot" not in sec


def test_featured_only_and_featured_first():
    _product("Normal")
    _product("Empfohlen", is_featured=True)
    t = _tenant([_block(source="products", only="featured")])
    sec = _section(_home(t))
    assert "Empfohlen" in sec and "Normal" not in sec

    t2 = _tenant([_block(source="products", sort="featured")])
    sec2 = _section(_home(t2))
    assert sec2.index("Empfohlen") < sec2.index("Normal")


def test_products_on_sale_only():
    cheap = _product("Im Angebot", price="5.00")
    _product("Voller Preis", price="5.00")
    _promo("Aktion Käse", product=cheap, discount_percent=20)
    t = _tenant([_block(source="products", only="sale")])
    sec = _section(_home(t))
    assert "Im Angebot" in sec and "Voller Preis" not in sec


def test_products_sorted_by_price():
    _product("Teuer", price="9.00")
    _product("Günstig", price="1.00")
    t = _tenant([_block(source="products", sort="price_asc")])
    sec = _section(_home(t))
    assert sec.index("Günstig") < sec.index("Teuer")


# ───────────────────────────── «Alle N →» ─────────────────────────────


def test_show_all_link_appears_only_when_something_is_cut():
    for i in range(3):
        _promo(f"Rest {i}", group="Räumung")
    cut = _section(_home(_tenant([_block(source="promotions", type="Räumung", limit=2)])))
    assert len(_promo_ids(cut)) == 2
    href, text = _all_link(cut)
    # N-4: «Alle →» у блока типа ведёт на страницу ТИПА (её шаблон), а не в результаты
    assert href == "/aktionen/?gruppe=R%C3%A4umung"
    assert "3" in text  # «Alle 3»: сколько всего, а не сколько показано
    whole = _section(_home(_tenant([_block(source="promotions", type="Räumung", limit=5)])))
    assert _all_link(whole) is None  # SF-5: всё уже на экране — ссылка не нужна


def test_show_all_link_keeps_the_filter_of_the_block():
    root = _cat("Käse", slug="kaese")
    for i in range(3):
        _product(f"Käse {i}", category=root)
    sec = _section(_home(_tenant([_block(source="products", category="kaese", limit=1)])))
    assert _all_link(sec)[0] == "/sortiment/kaese/"

    cheap = [_product(f"Billig {i}", price="5.00") for i in range(3)]
    for p in cheap:
        _promo(f"Aktion {p.pk}", product=p, discount_percent=20)
    sale = _section(_home(_tenant([_block(source="products", only="sale", limit=1)])))
    assert _all_link(sale)[0] == "/sortiment/?sale=1"

    for i in range(2):
        _promo(f"Bald vorbei {i}", ends_at=timezone.now() + timedelta(days=2))
    week = _section(_home(_tenant([_block(source="promotions", endet="woche", limit=1)])))
    assert _all_link(week)[0] == "/aktionen/?endet=woche"


def test_empty_block_disappears_live_and_keeps_an_anchor_in_preview():
    t = _tenant([_block(source="promotions", type="Räumung")])
    assert 'data-sf-list="' not in _home(t)
    assert 'data-sf-list="' in _home(t, preview=True)


# ───────────────────────────── вид: наследование ─────────────────────────────


def test_empty_view_inherits_the_view_of_the_promotion_type():
    t = _tenant(
        [_block(source="promotions", type="Räumung")],
        promo_groups={"Räumung": {"layout": {"preset": "cols4", "scroll": True}, "card": "coupon"}},
    )
    _promo("Restposten", group="Räumung")
    sec = _section(_home(t))
    assert "data-promo-strip" in sec
    assert 'data-card-form="coupon"' in sec


def test_own_view_of_the_block_beats_the_type():
    t = _tenant(
        [_block(source="promotions", type="Räumung", out="grid", cols=4, card="ring")],
        promo_groups={"Räumung": {"layout": {"preset": "cols3", "scroll": True}, "card": "coupon"}},
    )
    _promo("Restposten", group="Räumung")
    sec = _section(_home(t))
    assert "data-promo-strip" not in sec
    assert "lg:grid-cols-4" in sec
    assert 'data-card-form="ring"' in sec


def test_own_card_form_of_the_object_beats_the_block():
    """DL-19: «эта акция выглядит иначе» сильнее любого дефолта — и дефолта блока."""
    t = _tenant([_block(source="promotions", card="coupon")])
    _promo("Mit eigener Form", card_style="ring")
    sec = _section(_home(t))
    assert 'data-card-form="ring"' in sec and 'data-card-form="coupon"' not in sec


def test_product_block_card_form():
    _product("Brot")
    sec = _section(_home(_tenant([_block(source="products", card="regal")])))
    assert 'data-card-form="regal"' in sec


def test_rows_limit_the_grid_to_full_rows():
    """LAY-3b: «сколько рядов», а не абсолютное число — 4 колонки × 1 ряд = 4."""
    for i in range(10):
        _promo(f"Angebot {i}")
    sec = _section(_home(_tenant([_block(source="promotions", cols=4, rows=1)])))
    assert len(_promo_ids(sec)) == 4
    # явный «Höchstens» сильнее рядов
    sec = _section(_home(_tenant([_block(source="promotions", cols=4, rows=1, limit=6)])))
    assert len(_promo_ids(sec)) == 6
    # ничего не задано — 12, потолок блока 24
    sec = _section(_home(_tenant([_block(source="promotions")])))
    assert len(_promo_ids(sec)) == 10


# ───────────────────────────── §11 PAngV и запросы ─────────────────────────────


def test_promotion_cards_carry_the_lowest_price_of_30_days():
    """Блок PT-6 не навешивал `lowest_30d` — у его карточек не было строки §11 PAngV."""
    p = _product("Bergkäse", price="4.90")
    _promo("Käse-Aktion", product=p, discount_percent=20)
    sec = _section(_home(_tenant([_block(source="promotions")])))
    assert "Lowest price in the last 30 days" in sec or "Niedrigster Preis" in sec


def test_block_data_is_fetched_in_batches_not_per_card():
    """Выборка и оформление карточек акций (§11 PAngV) — батчами, без N+1.

    Замок на `resolve`, а не на всю страницу: сами карточки спрашивают варианты
    товара (`Product.has_variants`, и через него `Promotion.grundpreis`) — это
    свойство карточки на всех поверхностях (главная, каталог, /aktionen/), а не блока.
    Поэтому и у товаров замка нет: ценовой слой (`price_layer.attach_promos`) тоже
    спрашивает варианты по одному товару — найдено разведкой LB-1, вынесено в план.
    """
    source = "promotions"
    from apps.core import list_blocks

    def count_for(n):
        Promotion.objects.all().delete()
        Product.objects.all().delete()
        for i in range(n):
            prod = _product(f"Artikel {i}")
            _promo(f"Aktion {i}", product=prod, discount_percent=20)
        with CaptureQueriesContext(connection) as ctx:
            out = list_blocks.resolve(siteconfig.normalize({}), {"source": source})
        assert len(out["items"]) == n
        return len(ctx.captured_queries)

    assert count_for(6) == count_for(2)


# ───────────────────────────── редактор ─────────────────────────────


def test_sort_keys_are_the_providers_own():
    """Дубля словаря нет: ключи сортировок блока = ключи провайдера (+ «featured»)."""
    from apps.catalog.facets import CatalogFacets
    from apps.promotions.facets import PromoFacets

    assert siteconfig.list_sort_keys("promotions") == frozenset(PromoFacets().sort_keys())
    assert siteconfig.list_sort_keys("products") == frozenset(CatalogFacets().sort_keys()) | {
        "featured"
    }


def test_editor_options_are_marked_with_their_source():
    from apps.core import list_blocks

    cards = {key: srcs.split() for key, _label, srcs in list_blocks.card_options()}
    assert cards["coupon"] == ["promotions"] and cards["overlay"] == ["products"]
    assert sorted(cards["regal"]) == ["products", "promotions"]
    sorts = {key: srcs.split() for key, _label, srcs in list_blocks.sort_options()}
    assert sorted(sorts[""]) == ["products", "promotions"]  # «новые первыми» у обоих
    assert sorts["rabatt"] == ["promotions"] and sorts["price_asc"] == ["products"]
    assert sorts["featured"] == ["products"]


def _builder_html(tenant):
    from apps.core.tests.test_stu12_groups import _builder

    return _builder(tenant)


def test_builder_row_offers_both_sources_and_shows_where_the_view_comes_from():
    _cat("Käse", slug="kaese")
    block = _block(source="promotions", type="Räumung")
    t = _tenant(
        [block],
        promo_groups={"Räumung": {"layout": {"preset": "cols3", "scroll": True}}},
    )
    body = _builder_html(t)
    bid = block["id"]
    i = body.index(f'name="cb_{bid}_source"')
    row = body[body.rindex("data-lb-row", 0, i) : body.index("</details>\n    </div>", i)]
    # поля ОБОИХ источников в DOM (W0), чужие скрыты
    assert f'name="cb_{bid}_type"' in row and f'name="cb_{bid}_category"' in row
    assert 'data-lb-src="products" hidden' in row
    assert 'value="kaese"' in row  # категории каталога в фильтре товаров
    # пустой пункт вида знает, что придёт от ТИПА (у типа — лента)
    assert 'data-inherit-mode="slider"' in row
    # «Tempo» виден, потому что действующий вид — лента
    assert "data-lb-speed hidden" not in row


def test_inserted_row_gets_the_same_selectors_as_the_form():
    """Вставка без перезагрузки рендерит строку тем же набором селекторов, что форма."""
    import json
    import uuid

    from django.contrib.auth import get_user_model
    from django.contrib.messages.middleware import MessageMiddleware

    from apps.core import views as core_views

    _cat("Käse", slug="kaese")
    t = _tenant([])
    req = RequestFactory().post(
        "/dashboard/site/home/",
        {"action": "add_block", "block_type": "list", "variant": "new", "page_key": "info"},
        HTTP_X_REQUESTED_WITH="fetch",
    )
    SessionMiddleware(lambda r: None).process_request(req)
    MessageMiddleware(lambda r: None).process_request(req)
    req.tenant = t
    owner = uuid.uuid4().hex[:8]
    req.user = get_user_model().objects.create_user(
        username=f"o-{owner}", email=f"o-{owner}@t.de", password="pw12345678"
    )
    payload = json.loads(core_views.home_builder_view(req).content)
    assert payload["ok"] is True
    row = payload["row_html"]
    assert "data-lb-row" in row and 'value="kaese"' in row
    t.refresh_from_db()
    saved = siteconfig.normalize(t.site_config)["page_blocks"]["info"][0]
    # пресет «Neu im Sortiment» = товары, новые первыми (поверх демо-данных блока)
    assert saved["data"]["source"] == "products" and saved["data"]["sort"] == "newest"


def test_block_disappears_when_the_module_of_its_source_is_off():
    """У выключенных акций нет страницы `/aktionen/` — блок вёл бы в 404."""
    t = _tenant([_block(source="promotions")])
    _promo("Irgendwas")
    t.disabled_modules = ["promotions"]
    t.save(update_fields=["disabled_modules"])
    assert 'data-sf-list="' not in _home(t)


def test_deal_form_gets_at_most_two_inherited_columns():
    """«Deal» — строка «фото · текст · кнопка»: в трёх колонках текст схлопывается
    до буквы (стенд LB-1). Унаследованные колонки ужимаются, явные — нет."""
    from apps.core import list_blocks

    cfg = siteconfig.normalize({})
    inherited = list_blocks.effective_view(cfg, {"source": "promotions", "card": "deal"})
    assert inherited["layout"]["cols"] == 2 and inherited["layout"]["mobile"] == 1
    explicit = list_blocks.effective_view(cfg, {"source": "promotions", "card": "deal", "cols": 3})
    assert explicit["layout"]["cols"] == 3
    other = list_blocks.effective_view(cfg, {"source": "promotions", "card": "coupon"})
    assert other["layout"]["cols"] == 3
