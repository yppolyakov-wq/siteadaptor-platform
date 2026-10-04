"""LB-4a: списочные секции главной = блоки «Liste» с закреплённым источником.

План — `docs/lb4-home-lists-archetypes-plan-2026-10-04.md` §2–§4. Замки написаны ДО
кода, тремя группами:

* **характеризация** — что секции главной показывают сегодня (выборка, порядок, лимит,
  «все» у услуг и номеров): после перевода на движок блока это обязано остаться;
* **сознательные отличия** (§4.1) — главная следует листингам: серия событий одной
  карточкой, направление без товаров не показывается, статья без даты — в конце,
  порядок листинга по умолчанию у услуг;
* **новые оси** — у строки секции появляются «ЧТО» блока (фильтр, сортировка, форма
  карточки) в `row["data"]`, presence-minimal, а «View all» несёт тот же фильтр.
"""

import itertools
import re
import uuid
from datetime import timedelta
from decimal import Decimal

import pytest
from django.contrib.sessions.middleware import SessionMiddleware
from django.db import connection
from django.test import RequestFactory
from django.test.utils import CaptureQueriesContext
from django.utils import timezone

from apps.booking.models import Service
from apps.catalog.models import Category, Product
from apps.collections.models import Collection
from apps.events.models import BlogPost, Event, Tour
from apps.promotions import public_views
from apps.promotions.models import Promotion
from apps.stays.models import StayUnit
from apps.tenants import siteconfig
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db

_N = itertools.count()


@pytest.fixture(autouse=True)
def _urlconf(settings):
    settings.ROOT_URLCONF = "config.urls_tenant"


def _tenant(*rows, disabled=(), **cfg):
    """Тенант, у которого включены ровно `rows` (встроенные строки главной)."""
    keys = {r["key"] for r in rows}
    sections = [{"enabled": True, **r} for r in rows]
    sections += [{"key": k, "enabled": False} for k, _l, _on in siteconfig.SECTIONS if k not in keys]
    t = TenantFactory(slug=f"lb4{next(_N)}", name="LB4", disabled_modules=list(disabled))
    t.site_config = {"sections": sections, **cfg}
    t.save(update_fields=["site_config"])
    return t


def _home(tenant):
    req = RequestFactory().get("/")
    SessionMiddleware(lambda r: None).process_request(req)
    req.tenant = tenant
    return public_views.storefront_home(req).content.decode()


def _grid(body, key):
    """HTML секции главной по её сетке (`data-grid="<ключ>"`)."""
    i = body.index(f'data-grid="{key}"')
    start = body.rindex("<section", 0, i)
    return body[start : body.index("</section>", i)]


def _order(html, names):
    """Имена, которые есть в html, — в порядке появления."""
    found = [(html.index(n), n) for n in names if n in html]
    return [n for _i, n in sorted(found)]


def _hrefs(html):
    return [h.replace("&amp;", "&") for h in re.findall(r'href="([^"]+)"', html)]


def _category(name, parent=None, **kw):
    return Category.objects.create(
        name={"de": name},
        slug=kw.pop("slug", None) or f"c{next(_N)}",
        parent=parent,
        is_active=kw.pop("is_active", True),
        **kw,
    )


def _product(name, category=None, days=0, **kw):
    p = Product.objects.create(
        name={"de": name},
        base_price=kw.pop("price", Decimal("5.00")),
        category=category,
        is_active=kw.pop("is_active", True),
        **kw,
    )
    if days:
        Product.objects.filter(pk=p.pk).update(created_at=timezone.now() - timedelta(days=days))
    return p


def _promo(title, days=0, **kw):
    kw.setdefault("status", "active")
    kw.setdefault("discount_percent", 10)
    p = Promotion.objects.create(title={"de": title}, **kw)
    if days:
        Promotion.objects.filter(pk=p.pk).update(created_at=timezone.now() - timedelta(days=days))
    return p


def _service(name, **kw):
    kw.setdefault("duration_minutes", 30)
    kw.setdefault("price_cents", 3000)
    return Service.objects.create(name=name, **kw)


def _unit(name, **kw):
    kw.setdefault("price_cents", 9000)
    return StayUnit.objects.create(name=name, **kw)


def _event(title, days=10, **kw):
    kw.setdefault("status", Event.STATUS_PUBLISHED)
    kw.setdefault("capacity", 0)
    kw.setdefault("price_cents", 2500)
    return Event.objects.create(title=title, starts_at=timezone.now() + timedelta(days=days), **kw)


def _tour(title, **kw):
    return Tour.objects.create(
        title=title, slug=f"t{next(_N)}", is_published=kw.pop("published", True), **kw
    )


def _post(title, days=1, **kw):
    published_at = None if days is None else timezone.now() - timedelta(days=days)
    return BlogPost.objects.create(
        title=title,
        slug=f"p{next(_N)}",
        is_published=kw.pop("published", True),
        published_at=published_at,
        **kw,
    )


# ═══════════════════════ характеризация: как сейчас ═══════════════════════


def test_products_section_order_follows_its_source():
    bread = _category("Brot")
    _product("Alt-Empfohlen", bread, days=5, is_featured=True)
    _product("Mittel", bread, days=3)
    _product("Neu", bread, days=1)
    names = ["Alt-Empfohlen", "Mittel", "Neu"]
    featured_first = _grid(_home(_tenant({"key": "products"})), "products")
    assert _order(featured_first, names) == ["Alt-Empfohlen", "Neu", "Mittel"]
    newest = _grid(_home(_tenant({"key": "products", "source": "newest"})), "products")
    assert _order(newest, names) == ["Neu", "Mittel", "Alt-Empfohlen"]
    only = _grid(_home(_tenant({"key": "products", "source": "featured_only"})), "products")
    assert _order(only, names) == ["Alt-Empfohlen"]
    two = _grid(_home(_tenant({"key": "products", "source": "newest", "limit": 2})), "products")
    assert _order(two, names) == ["Neu", "Mittel"]


def test_promotions_section_shows_active_newest_first_up_to_its_limit():
    _promo("Alte Aktion", days=3)
    _promo("Neue Aktion", days=1)
    _promo("Entwurf", status="draft")
    names = ["Alte Aktion", "Neue Aktion", "Entwurf"]
    body = _grid(_home(_tenant({"key": "promotions"})), "promotions")
    assert _order(body, names) == ["Neue Aktion", "Alte Aktion"]
    one = _grid(_home(_tenant({"key": "promotions", "limit": 1})), "promotions")
    assert _order(one, names) == ["Neue Aktion"]


def test_services_and_rooms_sections_show_all_items_not_a_page_of_twelve():
    """У секций услуг и номеров лимита нет — показываются все (блок по умолчанию
    режет на 12: перевод на движок не должен этого принести)."""
    names = [f"Leistung {i:02d}" for i in range(14)]
    for name in reversed(names):
        _service(name)
    _service("Versteckt", is_active=False)
    for i in range(13):
        _unit(f"Zimmer {i:02d}")
    _unit("Gesperrt", is_active=False)
    body = _home(_tenant({"key": "services"}, {"key": "stay_rooms"}))
    services = _grid(body, "services")
    assert _order(services, names) == names  # по имени, все 14
    assert "Versteckt" not in services
    rooms = _grid(body, "stay_rooms")
    assert all(f"Zimmer {i:02d}" in rooms for i in range(13))
    assert "Gesperrt" not in rooms


def test_events_section_shows_published_upcoming_by_date_up_to_its_limit():
    _event("Später", days=20)
    _event("Bald", days=2)
    _event("Entwurf", status=Event.STATUS_DRAFT)
    _event("Vorbei", days=-3)
    names = ["Später", "Bald", "Entwurf", "Vorbei"]
    body = _grid(_home(_tenant({"key": "events"})), "events")
    assert _order(body, names) == ["Bald", "Später"]
    one = _grid(_home(_tenant({"key": "events", "limit": 1})), "events")
    assert _order(one, names) == ["Bald"]


def test_tours_section_follows_the_owners_order():
    _tour("Zweite", sort_order=2)
    _tour("Erste", sort_order=1)
    _tour("Entwurf", published=False)
    body = _grid(_home(_tenant({"key": "tours"})), "tours")
    assert _order(body, ["Zweite", "Erste", "Entwurf"]) == ["Erste", "Zweite"]


def test_blog_section_shows_published_newest_first():
    _post("Älter", days=5)
    _post("Neuer", days=1)
    _post("Entwurf", published=False)
    body = _grid(_home(_tenant({"key": "blog"})), "blog")
    assert _order(body, ["Älter", "Neuer", "Entwurf"]) == ["Neuer", "Älter"]


def test_categories_section_shows_roots_in_the_owners_order():
    b = _category("Backwaren", sort_order=2)
    a = _category("Aufstrich", sort_order=1)
    child_parent = _category("Feinkost", sort_order=3)
    child = _category("Käse", parent=child_parent)
    for cat in (a, b, child):
        _product(f"Ware {cat.slug}", cat)
    body = _grid(_home(_tenant({"key": "categories"})), "categories")
    assert _order(body, ["Backwaren", "Aufstrich", "Feinkost", "Käse"]) == [
        "Aufstrich",
        "Backwaren",
        "Feinkost",  # товары только у подкатегории — направление всё равно есть
    ]


# ═══════════════════════ сознательные отличия (§4.1) ═══════════════════════


def test_event_series_is_one_card_on_the_home_like_on_the_listing():
    series = uuid.uuid4()
    _event("Yoga-Kurs", days=3, series_id=series)
    _event("Yoga-Kurs", days=10, series_id=series)
    _event("Einzeltermin", days=5)
    body = _grid(_home(_tenant({"key": "events"})), "events")
    titles = re.findall(r'data-edit-field="title">([^<]+)<', body)
    assert titles.count("Yoga-Kurs") == 1 and titles.count("Einzeltermin") == 1


def test_category_without_products_is_not_offered_on_the_home():
    full = _category("Brot")
    _product("Laib", full)
    _category("Leer")
    body = _grid(_home(_tenant({"key": "categories"})), "categories")
    assert "Brot" in body and "Leer" not in body


def test_undated_blog_post_goes_last_not_first():
    _post("Ohne Datum", days=None)
    _post("Gestern", days=1)
    body = _grid(_home(_tenant({"key": "blog"})), "blog")
    assert _order(body, ["Ohne Datum", "Gestern"]) == ["Gestern", "Ohne Datum"]


def test_services_follow_the_listing_default_order_set_by_the_owner():
    _service("A billig", price_cents=1000)
    _service("B teuer", price_cents=9000)
    body = _grid(_home(_tenant({"key": "services"}, services_sort="price_desc")), "services")
    assert _order(body, ["A billig", "B teuer"]) == ["B teuer", "A billig"]


# ═══════════════════════ новые оси «ЧТО» у строки секции ═══════════════════════


def test_builtin_row_keeps_only_the_what_of_its_source_presence_minimal():
    row = {"key": "products", "enabled": True}
    out = siteconfig.normalize({"sections": [row]})["sections"]
    assert "data" not in next(s for s in out if s["key"] == "products")
    noisy = {
        "key": "products",
        "enabled": True,
        "data": {
            "category": "brot",
            "only": "featured",
            "sort": "price_asc",
            "card": "regal",
            "type": "Woche",  # фильтр акций
            "out": "slider",  # вид живёт в layout строки
            "cols": 3,
            "source": "promotions",  # источник закреплён ключом
        },
    }
    out = siteconfig.normalize({"sections": [noisy]})["sections"]
    data = next(s for s in out if s["key"] == "products")["data"]
    assert data == {"category": "brot", "only": "featured", "sort": "price_asc", "card": "regal"}
    promo = {"key": "promotions", "data": {"type": "Woche", "endet": "heute", "category": "x"}}
    out = siteconfig.normalize({"sections": [promo]})["sections"]
    assert next(s for s in out if s["key"] == "promotions")["data"] == {
        "type": "Woche",
        "endet": "heute",
    }
    junk = {"key": "services", "data": "nonsense"}
    out = siteconfig.normalize({"sections": [junk]})["sections"]
    assert "data" not in next(s for s in out if s["key"] == "services")
    # у секций без списка «ЧТО» не бывает
    out = siteconfig.normalize({"sections": [{"key": "faq", "data": {"sort": "x"}}]})
    assert "data" not in next(s for s in out["sections"] if s["key"] == "faq")


def test_builtin_sources_registry_covers_the_eight_list_sections():
    assert siteconfig.BUILTIN_LIST_SOURCES == {
        "promotions": "promotions",
        "products": "products",
        "categories": "categories",
        "services": "services",
        "stay_rooms": "stays",
        "events": "events",
        "tours": "tours",
        "blog": "blog",
    }
    for key, source in siteconfig.BUILTIN_LIST_SOURCES.items():
        assert key in {k for k, _l, _on in siteconfig.SECTIONS}
        assert source in siteconfig.LIST_SOURCES


def test_products_row_filters_by_category_and_view_all_keeps_it():
    bread = _category("Brot", slug="brot")
    cheese = _category("Käse", slug="kaese")
    _product("Laib", bread)
    _product("Gouda", cheese)
    body = _grid(_home(_tenant({"key": "products", "data": {"category": "brot"}})), "products")
    assert "Laib" in body and "Gouda" not in body
    assert "/sortiment/brot/" in _hrefs(body)


def test_products_row_sort_and_only_override_the_legacy_source():
    cat = _category("Alles")
    _product("Teuer", cat, price=Decimal("9.00"), is_featured=True)
    _product("Billig", cat, price=Decimal("1.00"))
    body = _grid(
        _home(_tenant({"key": "products", "source": "newest", "data": {"sort": "price_asc"}})),
        "products",
    )
    assert _order(body, ["Teuer", "Billig"]) == ["Billig", "Teuer"]
    body = _grid(_home(_tenant({"key": "products", "data": {"only": "featured"}})), "products")
    assert "Teuer" in body and "Billig" not in body


def test_products_row_card_form_applies_to_its_cards():
    _product("Laib", _category("Brot"))
    body = _grid(_home(_tenant({"key": "products", "data": {"card": "regal"}})), "products")
    assert 'data-card-form="regal"' in body


def test_promotions_row_filters_by_type_and_view_all_opens_the_type():
    _promo("Wochen-Deal", group="Woche")
    _promo("Sonstiges")
    body = _grid(_home(_tenant({"key": "promotions", "data": {"type": "Woche"}})), "promotions")
    assert "Wochen-Deal" in body and "Sonstiges" not in body
    section = _home(_tenant({"key": "promotions", "data": {"type": "Woche"}}))
    head = section[section.index('id="aktionen"') : section.index('data-grid="promotions"')]
    assert "/aktionen/?gruppe=Woche" in _hrefs(head)


def test_promotions_row_card_form_applies_to_its_cards():
    _promo("Deal")
    body = _grid(_home(_tenant({"key": "promotions", "data": {"card": "coupon"}})), "promotions")
    assert 'data-card-form="coupon"' in body


def test_services_row_filters_by_collection_and_video():
    hair = Collection.objects.create(name="Haar", slug="haar")
    cut = _service("Schnitt")
    cut.collections.add(hair)
    _service("Massage")
    _service("Video-Beratung", is_video=True)
    body = _grid(_home(_tenant({"key": "services", "data": {"collection": "haar"}})), "services")
    assert "Schnitt" in body and "Massage" not in body
    body = _grid(_home(_tenant({"key": "services", "data": {"only": "video"}})), "services")
    assert "Video-Beratung" in body and "Schnitt" not in body


def test_rooms_row_filters_by_collection():
    sea = Collection.objects.create(name="Meerblick", slug="meerblick")
    view = _unit("Seezimmer")
    view.collections.add(sea)
    _unit("Hofzimmer")
    body = _grid(
        _home(_tenant({"key": "stay_rooms", "data": {"collection": "meerblick"}})), "stay_rooms"
    )
    assert "Seezimmer" in body and "Hofzimmer" not in body


def test_events_row_filters_by_theme_and_soon():
    _event("Yoga", days=3, category="yoga")
    _event("Malen", days=4, category="kunst")
    _event("Fern", days=40, category="yoga")
    body = _grid(_home(_tenant({"key": "events", "data": {"event_category": "yoga"}})), "events")
    assert "Yoga" in body and "Malen" not in body
    body = _grid(_home(_tenant({"key": "events", "data": {"only": "soon"}})), "events")
    assert "Yoga" in body and "Fern" not in body


def test_tours_row_filters_by_country():
    _tour("Himalaya", country="Nepal")
    _tour("Rajasthan", country="Indien")
    body = _grid(_home(_tenant({"key": "tours", "data": {"country": "Nepal"}})), "tours")
    assert "Himalaya" in body and "Rajasthan" not in body


def test_categories_row_with_a_parent_shows_its_subcategories():
    parent = _category("Feinkost", slug="feinkost")
    for name in ("Käse", "Wurst"):
        _product(f"Ware {name}", _category(name, parent=parent))
    other = _category("Brot")
    _product("Laib", other)
    body = _grid(
        _home(_tenant({"key": "categories", "data": {"category": "feinkost"}})), "categories"
    )
    assert "Käse" in body and "Wurst" in body and "Brot" not in body


def test_home_queries_do_not_grow_with_cards():
    """Движок зовётся по разу на строку — запросы главной не растут с числом карточек.
    Товарные карточки сюда не входят: у них известный N+1 `Product.has_variants`
    (roadmap §Отложено, отдельный перф-инкремент)."""
    counts = []
    for n in (2, 6):
        for model in (Promotion, Event, BlogPost, Product, Category):
            model.objects.all().delete()
        for i in range(n):
            _promo(f"A{n}-{i}")
            _event(f"E{n}-{i}", days=i + 2)
            _post(f"B{n}-{i}", days=i + 1)
            _product(f"P{n}-{i}", _category(f"K{n}-{i}"))
        # лимиты выше числа карточек: COUNT при срезе — константа, а не рост
        t = _tenant(
            {"key": "promotions", "limit": 20},
            {"key": "categories", "limit": 20},
            {"key": "events", "limit": 20},
            {"key": "blog", "limit": 20},
        )
        with CaptureQueriesContext(connection) as ctx:
            _home(t)
        counts.append(len(ctx.captured_queries))
    assert counts[0] == counts[1]
