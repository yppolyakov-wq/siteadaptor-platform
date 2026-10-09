"""LB-4d-1: библиотека «＋» блока «Liste» по всем источникам + фильтр «Gilt für».

План — `docs/lb4-home-lists-archetypes-plan-2026-10-04.md` §12.1. Замки ДО кода:

* у КАЖДОГО источника блока есть пресет в библиотеке, и пресет проходит normalize;
* инсертер предлагает пресет, только если включён модуль его источника (и модуль цели
  у «Angebote für …») и источнику есть что показать — кроме главного товара архетипа
  (его предлагаем и пустым: это то, что владелец заведёт первым); главный — первым;
* «Gilt für» (`ziel`) у акций — одна точка истины `PromoFacets`: блок, встроенная
  секция главной, «Ending soon» и `/aktionen/?ziel=` фильтруют одинаково; обзор
  `/aktionen/` считает его СУЖАЮЩИМ фильтром (не гасит встроенное);
* поле — в строке блока и во встроенной секции акций, переживает Save и черновик.
"""

import itertools
import json
import re
from datetime import timedelta
from decimal import Decimal

import pytest
from django.contrib.sessions.middleware import SessionMiddleware
from django.test import RequestFactory
from django.utils import timezone

from apps.booking.models import Service
from apps.catalog.models import Combo, Product
from apps.core import list_blocks
from apps.core.tests.test_list_block_sources import (
    _all_link,
    _block,
    _builder_html,
    _home,
    _row,
    _section,
    _tenant,
)
from apps.core.tests.test_stu12_groups import TPL, _post_builder, _segment
from apps.events.models import Event, Tour
from apps.promotions import public_views
from apps.promotions.models import Promotion
from apps.stays.models import StayUnit
from apps.tenants import siteconfig

pytestmark = pytest.mark.django_db

_N = itertools.count()


@pytest.fixture(autouse=True)
def _urlconf(settings):
    settings.ROOT_URLCONF = "config.urls_tenant"


def _promo(title, days_left=10, pct=20, **kw):
    return Promotion.objects.create(
        title={"de": title},
        status="active",
        discount_percent=pct,
        ends_at=timezone.now() + timedelta(days=days_left),
        **kw,
    )


def _unit(name="Doppelzimmer"):
    return StayUnit.objects.create(name=name, price_cents=9000)


def _service(name="Haarschnitt"):
    return Service.objects.create(name=name, duration_minutes=30, price_cents=3000)


def _product(name="Brot"):
    return Product.objects.create(name={"de": name}, base_price=Decimal("3.00"), is_active=True)


def _keys(presets):
    return [p["key"] for p in presets]


def _src(preset):
    return (preset.get("data") or {}).get("source") or siteconfig.LIST_SOURCE_DEFAULT


def _about(preset):
    """Источник, о котором пресет: у «Angebote für Zimmer» — номера."""
    data = preset.get("data") or {}
    target = data.get("ziel")
    return list_blocks.TARGET_SOURCES[target] if target else _src(preset)


def _aktionen(tenant, query=""):
    req = RequestFactory().get("/aktionen/" + query)
    SessionMiddleware(lambda r: None).process_request(req)
    req.tenant = tenant
    return public_views.promotion_list(req).content.decode()


# ───────────────────────────── реестр ─────────────────────────────


def test_every_block_source_has_a_library_preset():
    covered = {_src(v) for v in siteconfig.CBLOCK_VARIANTS["list"]}
    assert covered == set(siteconfig.LIST_SOURCES), sorted(set(siteconfig.LIST_SOURCES) - covered)


def test_target_presets_keep_their_target_through_normalize():
    for key, target in (("promo_rooms", "stay"), ("promo_services", "service")):
        preset = siteconfig.cblock_insert_preset("list", key)
        cfg = siteconfig.normalize(
            {"sections": [{"key": "list", "id": "x1", "enabled": True, **preset}]}
        )
        block = next(s for s in cfg["sections"] if s.get("id") == "x1")
        assert block["data"]["source"] == "promotions"
        assert block["data"]["ziel"] == target


def test_target_is_kept_only_for_promotions_and_known_values():
    clean = lambda **d: siteconfig._clean_cblock_data("list", d)  # noqa: E731
    assert clean(source="promotions", ziel="stay")["ziel"] == "stay"
    assert clean(source="promotions", ziel="combo")["ziel"] == "combo"
    assert "ziel" not in clean(source="promotions", ziel="event")  # у события цели нет
    assert "ziel" not in clean(source="promotions", ziel="<x>")
    assert "ziel" not in clean(source="products", ziel="stay")  # фильтр акций
    assert "ziel" not in clean(source="promotions")  # presence-minimal
    # «Demnächst» сужается целью так же, как действующие акции
    assert clean(source="promotions", phase="upcoming", ziel="stay")["ziel"] == "stay"


# ───────────────────────────── гейт и порядок ─────────────────────────────


def test_library_hides_presets_of_switched_off_modules():
    _unit()
    _service()
    t = _tenant(disabled=["stays", "booking"])
    presets = list_blocks.library_presets(t)
    assert presets, "библиотека не может опустеть целиком"
    assert not [p["key"] for p in presets if _about(p) in ("stays", "services")]


def test_library_hides_sources_with_nothing_to_show_but_keeps_the_primary():
    t = _tenant(primary_module="stays")  # отель без номеров, товаров и событий
    keys = _keys(list_blocks.library_presets(t))
    # главный товар архетипа предлагаем и пустым — его заводят первым
    assert "rooms" in keys
    # пустой каталог у отеля — не его товар: «Neu im Sortiment» обещал бы пустое
    assert "new" not in keys and "categories" not in keys
    _product()
    assert "new" in _keys(list_blocks.library_presets(t))


def test_library_puts_the_archetype_first():
    _unit()
    _service()
    _product()
    _promo("Sommer", stay_unit=StayUnit.objects.first())
    _promo("Schnitt", service=Service.objects.first())
    cases = {"stays": "stays", "booking": "services", "catalog": "products"}
    for module, source in cases.items():
        t = _tenant(primary_module=module)
        presets = list_blocks.library_presets(t)
        assert _about(presets[0]) == source, (module, _keys(presets))
        # всё главное — одним куском впереди, без вкраплений чужого
        heads = [_about(p) == source for p in presets]
        assert heads == sorted(heads, reverse=True), (module, _keys(presets))


def test_tour_operator_gets_tours_first():
    tour = Tour.objects.create(title="Nepal", slug="nepal", is_published=True)
    Event.objects.create(
        title="Nepal",
        tour=tour,
        starts_at=timezone.now() + timedelta(days=30),
        status=Event.STATUS_PUBLISHED,
        capacity=0,
    )
    t = _tenant(primary_module="events")
    assert _src(list_blocks.library_presets(t)[0]) == "tours"


def test_builder_offers_exactly_the_gated_library():
    _unit()
    t = _tenant(primary_module="stays", disabled=["booking"])
    body = _builder_html(t)
    raw = _segment(body, "var CB_VARIANTS = ", ";\n")[len("var CB_VARIANTS = ") :]
    offered = [v["key"] for v in json.loads(raw)["list"]]
    assert offered == _keys(list_blocks.library_presets(t))
    assert "video" not in offered  # модуль услуг выключен


def test_combos_preset_is_named_like_the_business_type():
    Combo.objects.create(name="Mittagsmenü", price=Decimal("12.90"), is_active=True)
    t = _tenant(primary_module="catalog")
    t.business_type = "restaurant"
    t.save(update_fields=["business_type"])
    body = _builder_html(t)
    raw = _segment(body, "var CB_VARIANTS = ", ";\n")[len("var CB_VARIANTS = ") :]
    combos = next(v for v in json.loads(raw)["list"] if v["key"] == "combos")
    assert combos["label"] == list_blocks.source_label("combos", t)


# ───────────────────────────── фильтр «Gilt für» ─────────────────────────────


def _targets():
    unit, service, product = _unit(), _service(), _product()
    return {
        "stay": _promo("Zimmer-Deal", stay_unit=unit),
        "service": _promo("Schnitt-Deal", service=service),
        "product": _promo("Brot-Deal", product=product),
        "": _promo("Frei"),
    }


def test_block_filters_promotions_by_target():
    promos = _targets()
    for target in ("stay", "service", "product"):
        items, total = list_blocks._promotions({"ziel": target}, 10)
        assert [p.pk for p in items] == [promos[target].pk], target
        assert total == 1


def test_home_section_and_block_share_the_target_filter():
    _targets()
    block = _block(source="promotions", ziel="stay", title="Für Ihren Aufenthalt")
    t = _tenant([block])
    cfg = dict(t.site_config)
    for row in cfg["sections"]:
        if row["key"] == "promotions":
            row.update(enabled=True, data={"ziel": "service"})
    t.site_config = cfg
    t.save(update_fields=["site_config"])
    body = _home(t)
    own = body[body.index(f'id="lb-{block["id"]}"') :]
    own = own[: own.index("</section>")]
    assert "Zimmer-Deal" in own and "Schnitt-Deal" not in own and "Frei" not in own
    section = body[body.index('id="aktionen"') :]
    section = section[: section.index("</section>")]
    assert "Schnitt-Deal" in section and "Zimmer-Deal" not in section


def test_all_link_carries_the_target():
    assert list_blocks._all_url({"source": "promotions", "ziel": "stay"}) == "/aktionen/?ziel=stay"


def test_block_more_link_keeps_the_target():
    unit = _unit()
    for i in range(3):
        _promo(f"Zimmer {i}", stay_unit=unit)
    block = _block(source="promotions", ziel="stay", limit=2)
    body = _home(_tenant([block]))
    assert _all_link(_section(body, "promotions")) == "/aktionen/?ziel=stay"


def test_ending_soon_respects_the_target():
    unit = _unit()
    room = _promo("Zimmer bald", days_left=1, stay_unit=unit)
    _promo("Frei bald", days_left=1)
    soon = list_blocks.promotions_ending_soon({"ziel": "stay"})
    assert [p.pk for p in soon] == [room.pk]


def test_aktionen_page_filters_by_target():
    _targets()
    body = _aktionen(_tenant(), "?ziel=stay")
    assert "Zimmer-Deal" in body
    assert "Schnitt-Deal" not in body and "Brot-Deal" not in body and "Frei" not in body


def test_aktionen_shows_the_target_chip_only_while_it_filters():
    """Цели в ряд чипов не выводим (страницу собирает владелец рубриками — у отеля
    «Zimmer-Angebote» рядом с «Angebote für Zimmer» читались бы дублем); активный
    фильтр, пришедший из «Alle N →» блока, снимается своим чипом."""
    _promo("Brot-Deal", product=_product())
    _promo("Zimmer-Deal", stay_unit=_unit())
    t = _tenant()
    assert "?ziel=" not in _aktionen(t)
    body = _aktionen(t, "?ziel=stay")
    chips = _segment(body, "data-promo-filters", "</div>")
    label = re.escape(str(_label("stay", t)))
    assert re.search(r'href="/aktionen/"\s+class="[^"]*bg-gray-900[^"]*">' + label + "<", chips)


def _label(target, tenant):
    return list_blocks.target_label(target)


def test_overview_treats_the_target_as_a_narrowing_filter():
    rows = [
        {
            "key": "list",
            "id": "a",
            "data": {"source": "promotions", "type": "Wochen", "ziel": "stay"},
        },
        {
            "key": "list",
            "id": "b",
            "data": {"source": "promotions", "endet": "heute", "ziel": "stay"},
        },
        {
            "key": "list",
            "id": "c",
            "data": {"source": "promotions", "phase": "upcoming", "ziel": "stay"},
        },
    ]
    plan = list_blocks.overview_blocks({"page_blocks": {"promos": rows}})
    assert plan["active"]
    assert plan["types"] == set()  # «Wochen · für Zimmer» не гасит рубрику
    assert plan["ending"] == []  # «Endet heute · für Zimmer» не гасит «Ending soon»
    assert plan["upcoming"] is False  # «Demnächst · für Zimmer» не гасит «Vorschau»


# ───────────────────────────── Студия ─────────────────────────────


def test_block_row_offers_the_target_select_by_module():
    block = _block(source="promotions", ziel="stay")
    t = _tenant([block], disabled=["stays"])
    row = _row(_builder_html(t), block["id"])
    select = row[row.index(f'name="cb_{block["id"]}_ziel"') :]
    select = select[: select.index("</select>")]
    assert 'value="service"' in select and 'value="product"' in select
    # модуль номеров выключен: пункта не предлагаем, но значение блока цело (W0)
    assert re.search(r'value="stay"[^>]*selected', select)
    assert select.count('value="stay"') == 1


def test_builtin_promotions_row_has_the_target_and_saves_it():
    t = _tenant([])
    cfg = dict(t.site_config)
    for row in cfg["sections"]:
        if row["key"] == "promotions":
            row["enabled"] = True
    t.site_config = cfg
    t.save(update_fields=["site_config"])
    body = _builder_html(t)
    assert 'name="sl_promotions_ziel"' in body
    saved = _post_builder(
        t,
        {
            "order_promotions": "1",
            "enabled_promotions": "on",
            "sl_promotions_present": "1",
            "sl_promotions_ziel": "stay",
        },
    )
    row = next(s for s in saved["sections"] if s["key"] == "promotions")
    assert row["data"] == {"ziel": "stay"}


def test_target_reaches_the_draft_and_the_builtin_draft():
    tpl = TPL.read_text("utf-8")
    cb = set(re.findall(r'"(\w+)"', _segment(tpl, "var CB_DATA_FIELDS", "]")))
    sl = set(re.findall(r'"(\w+)"', _segment(tpl, "var SL_DATA_FIELDS", "]")))
    assert "ziel" in cb and "ziel" in sl
    assert "ziel" in list_blocks.BUILTIN_WHAT_FIELDS
