"""LB-3d-1: блок «Liste» — услуги, номера, события (план lb-list-blocks §13.3).

Замки написаны ДО кода. Источник блока описан в реестре (`siteconfig.LIST_SOURCES` +
`list_blocks.SOURCES`), а не веткой `if source == …`: фильтры и сортировки — у
провайдера фасетов источника, карточка — та же, что у его листинга, «Alle N →» —
листинг источника с тем же фильтром, модуль выключен — блока нет.
"""

import itertools
import re
from datetime import timedelta

import pytest
from django.contrib.sessions.middleware import SessionMiddleware
from django.db import connection
from django.template import Context, Template
from django.test import RequestFactory
from django.test.utils import CaptureQueriesContext
from django.utils import timezone

from apps.booking.models import Service
from apps.collections.models import Collection
from apps.core import list_blocks
from apps.events.models import Event
from apps.promotions import public_views
from apps.stays.models import StayUnit
from apps.tenants import siteconfig
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db

_N = itertools.count()


@pytest.fixture(autouse=True)
def _urlconf(settings):
    settings.ROOT_URLCONF = "config.urls_tenant"


def _block(**data):
    return {"key": "list", "id": f"lbs{next(_N)}", "enabled": True, "data": data}


def _tenant(sections=None, disabled=(), **cfg):
    # Схема НЕ public: context-processor витрины для public-схемы молчит (урок ST-3).
    # Модуль активен = доступен по тарифу − выключен владельцем (`disabled_modules`).
    t = TenantFactory(slug=f"lbs{next(_N)}", name="LBS", disabled_modules=list(disabled))
    config = dict(cfg)
    if sections is not None:
        fixed = [{"key": key, "enabled": False} for key, _label, _on in siteconfig.SECTIONS]
        config["sections"] = fixed + list(sections)
    t.site_config = config
    t.save(update_fields=["site_config"])
    return t


def _home(tenant):
    req = RequestFactory().get("/")
    SessionMiddleware(lambda r: None).process_request(req)
    req.tenant = tenant
    return public_views.storefront_home(req).content.decode()


def _section(body, source):
    i = body.index(f'data-sf-list="{source}"')
    start = body.rindex("<section", 0, i)
    return body[start : body.index("</section>", i)]


def _all_link(html):
    m = re.search(r'<a [^>]*data-sf-list-all[^>]*href="([^"]+)"', html)
    return m.group(1).replace("&amp;", "&") if m else None


def _clean(**data):
    return siteconfig._clean_cblock_data("list", data)


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


def _collection(slug):
    return Collection.objects.create(name=slug.title(), slug=slug)


def _names(items, attr="name"):
    return [getattr(i, attr) for i in items]


# ───────────────────────────── данные блока ─────────────────────────────


def test_service_block_keeps_only_its_own_filters():
    data = _clean(
        source="services",
        collection="damen",
        only="video",
        sort="price_asc",
        category="kaese",  # фильтр товаров
        type="Räumung",  # фильтр акций
        event_category="yoga",  # фильтр событий
    )
    assert data == {
        "source": "services",
        "collection": "damen",
        "only": "video",
        "sort": "price_asc",
    }


def test_stay_block_keeps_only_its_own_filters():
    data = _clean(source="stays", collection="seeblick", only="video", sort="newest")
    # у номеров нет ни «только видео», ни сортировки «новые» (провайдер её не умеет)
    assert data == {"source": "stays", "collection": "seeblick"}


def test_event_block_keeps_only_its_own_filters():
    data = _clean(
        source="events", event_category="yoga", only="soon", collection="x", sort="price_desc"
    )
    assert data == {
        "source": "events",
        "event_category": "yoga",
        "only": "soon",
        "sort": "price_desc",
    }


def test_products_block_accepts_a_collection():
    assert _clean(source="products", collection="sommer") == {
        "source": "products",
        "collection": "sommer",
    }


def test_garbage_filters_of_new_sources_are_dropped():
    assert _clean(source="services", collection="Da men/", only="soon") == {"source": "services"}
    assert _clean(source="events", only="video", event_category="  ") == {"source": "events"}


def test_new_code_fields_never_travel_into_a_translation():
    for field in ("collection", "event_category"):
        assert field in siteconfig.NON_TRANSLATABLE_FIELDS


# ───────────────────────────── выборка ─────────────────────────────


def test_service_block_filters_by_collection_and_video():
    damen = _collection("damen")
    schnitt = _service("Schnitt")
    schnitt.collections.add(damen)
    _service("Video-Beratung", is_video=True)
    _service("Bart")
    cfg = siteconfig.normalize({})
    out = list_blocks.resolve(cfg, {"source": "services", "collection": "damen"})
    assert _names(out["items"]) == ["Schnitt"]
    out = list_blocks.resolve(cfg, {"source": "services", "only": "video"})
    assert _names(out["items"]) == ["Video-Beratung"]


def test_empty_sort_of_a_service_block_follows_the_page():
    """Пустая сортировка = порядок страницы источника: то, что покажет «Alle N →»."""
    _service("Teuer", price_cents=9000)
    _service("Billig", price_cents=1000)
    _service("Mittel", price_cents=5000)
    plain = list_blocks.resolve(siteconfig.normalize({}), {"source": "services"})
    assert _names(plain["items"]) == ["Billig", "Mittel", "Teuer"]  # «Standard» = по имени
    by_price = siteconfig.normalize({"services_sort": "price_desc"})
    out = list_blocks.resolve(by_price, {"source": "services"})
    assert _names(out["items"]) == ["Teuer", "Mittel", "Billig"]
    own = list_blocks.resolve(by_price, {"source": "services", "sort": "price_asc"})
    assert _names(own["items"]) == ["Billig", "Mittel", "Teuer"]


def test_stay_block_filters_by_collection():
    seeblick = _collection("seeblick")
    _unit("Doppelzimmer Seeblick").collections.add(seeblick)
    _unit("Einzelzimmer")
    out = list_blocks.resolve(
        siteconfig.normalize({}), {"source": "stays", "collection": "seeblick"}
    )
    assert _names(out["items"]) == ["Doppelzimmer Seeblick"]


def test_event_block_shows_upcoming_published_and_folds_a_series():
    """Как листинг: только будущие опубликованные, серия — одной карточкой «+N Termine»."""
    _event("Vorbei", days=-3)
    _event("Entwurf", status=Event.STATUS_DRAFT)
    first = _event("Kurs A", days=5, series_id="11111111-1111-1111-1111-111111111111")
    _event("Kurs A", days=12, series_id="11111111-1111-1111-1111-111111111111")
    _event("Konzert", days=8)
    out = list_blocks.resolve(siteconfig.normalize({}), {"source": "events"})
    assert [e.pk for e in out["items"]][0] == first.pk
    assert _names(out["items"], "title") == ["Kurs A", "Konzert"]
    assert out["items"][0].more_dates == 1
    assert out["total"] == 2


def test_event_block_filters_by_category_and_soon():
    _event("Yoga bald", days=5, category="yoga")
    _event("Yoga später", days=40, category="yoga")
    _event("Meditation bald", days=3, category="meditation")
    cfg = siteconfig.normalize({})
    out = list_blocks.resolve(cfg, {"source": "events", "event_category": "yoga"})
    assert _names(out["items"], "title") == ["Yoga bald", "Yoga später"]
    out = list_blocks.resolve(cfg, {"source": "events", "event_category": "yoga", "only": "soon"})
    assert _names(out["items"], "title") == ["Yoga bald"]


def test_event_block_queries_do_not_grow_with_cards():
    """Места события — одним агрегатом на выдачу: карточка спрашивает «распродано» и
    «осталось мест», и без подсказки это 3–5 запросов на карточку."""

    def count_for(n):
        Event.objects.all().delete()
        for i in range(n):
            _event(f"Abend {i}", days=5 + i, capacity=20)
        t = _tenant([_block(source="events")])
        with CaptureQueriesContext(connection) as ctx:
            body = _home(t)
        assert body.count('href="/veranstaltung/') >= n
        return len(ctx.captured_queries)

    assert count_for(6) == count_for(2)


# ───────────────────────────── витрина ─────────────────────────────


def test_blocks_render_the_cards_of_their_source():
    s = _service("Haarschnitt")
    u = _unit("Doppelzimmer")
    e = _event("Klangabend", days=6)
    body = _home(
        _tenant(
            [
                _block(source="services"),
                _block(source="stays"),
                _block(source="events"),
            ]
        )
    )
    assert f'href="/leistung/{s.pk}/"' in _section(body, "services")
    assert f'href="/unterkunft/{u.pk}/"' in _section(body, "stays")
    events = _section(body, "events")
    assert f'href="/veranstaltung/{e.pk}/"' in events
    assert e.starts_at.astimezone(timezone.get_current_timezone()).strftime("%d.%m.%Y") in events


def test_event_card_in_a_card_form_shows_the_date_not_minutes():
    """У общей карточки не было ветки события: событие падало в ветку услуги и
    печатало « min» без даты (Finder, полки, форма карточки на /veranstaltung/)."""
    e = _event("Waldbaden", days=9, price_cents=0, tiers=[{"label": "A", "price_cents": 1900}])
    html = Template("{% load sellable_ui %}{% sellable_card 'event' e %}").render(
        Context({"e": e, "storefront_card_style": "overlay"})
    )
    assert " min" not in html
    assert e.starts_at.astimezone(timezone.get_current_timezone()).strftime("%d.%m.%Y") in html
    assert "19,00" in html or "19.00" in html


def test_event_block_with_a_card_form_uses_the_shared_card():
    _event("Waldbaden", days=9)
    body = _home(_tenant([_block(source="events", card="overlay")]))
    sec = _section(body, "events")
    assert " min<" not in sec and "Waldbaden" in sec


def test_show_all_links_point_to_the_listing_of_the_source():
    damen = _collection("damen")
    for name in ("A", "B"):
        _service(name).collections.add(damen)
    seeblick = _collection("seeblick")
    for name in ("C", "D"):
        _unit(name).collections.add(seeblick)
    for title in ("Yoga 1", "Yoga 2"):
        _event(title, category="yoga")
    body = _home(
        _tenant(
            [
                _block(source="services", collection="damen", limit=1),
                _block(source="stays", collection="seeblick", limit=1),
                _block(source="events", event_category="yoga", limit=1),
            ]
        )
    )
    assert _all_link(_section(body, "services")) == "/termin/?kollektion=damen"
    assert _all_link(_section(body, "stays")) == "/unterkunft/?kollektion=seeblick"
    assert _all_link(_section(body, "events")) == "/veranstaltung/?cat=yoga"


def test_block_of_a_disabled_module_is_not_rendered():
    _unit("Doppelzimmer")
    # положительный контроль: с включённым модулем блок есть (иначе замок зелёный
    # по ложной причине — неизвестный источник молча читался как «акции»)
    assert 'data-sf-list="stays"' in _home(_tenant([_block(source="stays")]))
    body = _home(_tenant([_block(source="stays")], disabled=["stays"]))
    assert 'data-sf-list="stays"' not in body


def test_block_label_follows_the_selection():
    damen = _collection("damen")
    _service("Schnitt").collections.add(damen)
    cfg = siteconfig.normalize({})
    out = list_blocks.resolve(cfg, {"source": "services", "collection": "damen"})
    assert out["label"] == "Damen"
    _event("Yoga", category="yoga")
    out = list_blocks.resolve(cfg, {"source": "events", "event_category": "yoga"})
    assert out["label"] == "Yoga"


# ───────────────────────────── листинг событий (характеризация) ─────────────────────────────


def test_events_listing_folds_a_series_into_one_card():
    """Свёртка серии на /veranstaltung/ — замок ДО выноса помощников (его не было)."""
    from apps.events import public_views as events_public

    series = "22222222-2222-2222-2222-222222222222"
    first = _event("Kurs B", days=4, series_id=series)
    second = _event("Kurs B", days=11, series_id=series)
    t = _tenant()
    req = RequestFactory().get("/veranstaltung/")
    SessionMiddleware(lambda r: None).process_request(req)
    req.tenant = t
    body = events_public.veranstaltung_index(req).content.decode()
    assert f"/veranstaltung/{first.pk}/" in body
    assert f"/veranstaltung/{second.pk}/" not in body
    assert "+1 Termine" in body


# ───────────────────────────── редактор ─────────────────────────────


def test_sort_and_card_options_know_the_new_sources():
    sorts = list_blocks.sort_options(siteconfig.normalize({}))
    by_source = {}
    for key, label, srcs in sorts:
        for src in srcs.split():
            by_source.setdefault(src, {})[key] = label
    assert set(by_source["services"]) == {"", "price_asc", "price_desc", "newest"}
    assert set(by_source["stays"]) == {"", "price_asc", "price_desc"}
    assert set(by_source["events"]) == {"", "price_asc", "price_desc"}
    # у каждого источника пункт «пусто» подписан СВОИМ порядком по умолчанию
    assert by_source["promotions"][""] != by_source["events"][""]
    cards = {key: srcs.split() for key, _label, srcs in list_blocks.card_options()}
    assert {"products", "services", "stays", "events"} <= set(cards["overlay"])


def test_empty_sort_label_names_the_page_default():
    """Пустой пункт подписан тем, что придёт со страницы, — как пустые оси вида."""
    from apps.booking.facets import ServiceFacets

    rows = list_blocks.sort_options(siteconfig.normalize({"services_sort": "price_desc"}))
    empty = [label for key, label, srcs in rows if key == "" and "services" in srcs.split()]
    assert len(empty) == 1
    page_label = str(dict(ServiceFacets().sort_options())["price_desc"])
    assert page_label in empty[0]


def _builder_html(tenant):
    from apps.core.tests.test_stu12_groups import _builder

    return _builder(tenant)


def _row(body, bid):
    i = body.index(f'name="cb_{bid}_source"')
    return body[body.rindex("data-lb-row", 0, i) : body.index("</details>\n    </div>", i)]


def test_source_select_offers_active_modules_and_keeps_the_blocks_own():
    block = _block(source="stays")
    t = _tenant([block], disabled=["stays", "events"])
    row = _row(_builder_html(t), block["id"])
    select = row[row.index(f'name="cb_{block["id"]}_source"') :]
    select = select[: select.index("</select>")]
    assert 'value="services"' in select  # модуль включён
    assert 'value="events"' not in select  # модуль выключен — источника не предлагаем
    # источник самого блока остаётся выбранным, хотя модуль выключен (W0)
    assert re.search(r'value="stays"[^>]*selected', select)


def test_editor_offers_collections_and_event_categories():
    _collection("damen")
    _event("Yoga", category="yoga")
    block = _block(source="services", collection="damen")
    t = _tenant([block])
    row = _row(_builder_html(t), block["id"])
    assert f'name="cb_{block["id"]}_collection"' in row
    assert re.search(r'value="damen"[^>]*selected', row)
    assert f'name="cb_{block["id"]}_event_category"' in row and 'value="yoga"' in row


def test_service_card_in_a_block_shows_its_price():
    _service("Färben", price_cents=4500)
    body = _home(_tenant([_block(source="services")]))
    assert "45,00" in _section(body, "services") or "45.00" in _section(body, "services")
