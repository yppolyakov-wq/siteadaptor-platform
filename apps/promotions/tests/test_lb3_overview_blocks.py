"""LB-3: обзор `/aktionen/` блоками — Sprungleiste, остаток, результаты.

План — `docs/lb-list-blocks-plan-2026-10-02.md` §12 (решения владельца N-1…N-4, Р-5 (а)).
Замки написаны ДО кода.

Страница акций строится из блоков, как только на ней есть хотя бы один ВКЛЮЧЁННЫЙ блок
«Liste» с акциями. Без таких блоков — сегодняшняя страница (переход без поломок).
Встроенное заменяется только РАВНОЗНАЧНЫМ блоком — тем, что показывает то же множество
акций (§12.8): секция рубрики X ↔ блок «тип X» без сужающих фильтров; «Ending soon» ↔
блок «Endet …» без типа; «Vorschau» ↔ блок «Demnächst» без типа. Основной список в
обзоре = остаток (N-3). На странице типа и в результатах блоков «Liste» с акциями нет.
"""

import itertools
import re
from datetime import timedelta
from types import SimpleNamespace

import pytest
from django.contrib.messages.middleware import MessageMiddleware
from django.contrib.sessions.middleware import SessionMiddleware
from django.test import RequestFactory
from django.utils import timezone

from apps.core import list_blocks, page_presets
from apps.promotions import public_views
from apps.promotions.models import Promotion
from apps.tenants import siteconfig
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db

_N = itertools.count()
MAIN = {"key": "main"}
TYPE_CHIPS = '<div class="flex flex-wrap gap-2 mb-3">'


@pytest.fixture(autouse=True)
def _urlconf(settings):
    settings.ROOT_URLCONF = "config.urls_tenant"


def _tenant(**cfg):
    # Схема НЕ public: context-processor витрины для public-схемы молчит (урок ST-3).
    t = TenantFactory(slug=f"lb3t{next(_N)}", name="LB3")
    t.site_config = cfg
    t.save(update_fields=["site_config"])
    return t


def _req(tenant, path="/aktionen/", method="get", data=None):
    req = getattr(RequestFactory(), method)(path, data or {})
    SessionMiddleware(lambda r: None).process_request(req)
    MessageMiddleware(lambda r: None).process_request(req)
    req.user = SimpleNamespace(is_authenticated=True)
    req.tenant = tenant
    return req


def _page(tenant, **params):
    return public_views.promotion_list(_req(tenant, data=params)).content.decode()


def _lb(bid, **data):
    return {"key": "list", "id": bid, "enabled": True, "data": {"source": "promotions", **data}}


def _text(bid, title):
    return {"key": "text", "id": bid, "enabled": True, "data": {"title": title, "body": "x"}}


def _promo(title, group="", *, status="active", ends_in=20, starts_in=None, **kw):
    now = timezone.now()
    starts = now + timedelta(days=starts_in) if starts_in is not None else now - timedelta(days=1)
    return Promotion.objects.create(
        title={"de": title},
        status=status,
        promo_type="discount",
        group=group,
        discount_percent=kw.pop("discount_percent", 10),
        starts_at=starts,
        ends_at=now + timedelta(days=ends_in),
        **kw,
    )


def _shop():
    """Две рубрики по две акции, акция без рубрики, скоро истекающая и будущая."""
    _promo("LB3-Raeumung-1", "Räumung", discount_percent=40)
    _promo("LB3-Raeumung-2", "Räumung")
    _promo("LB3-Woche-1", "Wochenangebote")
    _promo("LB3-Woche-2", "Wochenangebote")
    _promo("LB3-Ohne", "")
    _promo("LB3-Bald-weg", "", ends_in=2)
    _promo("LB3-Zukunft", status="scheduled", starts_in=3)


def _segment(body, marker, end="</section>"):
    start = body.index(marker)
    return body[start : body.index(end, start)]


def _sections(body):
    """Ключи секций основного списка (остатка) в порядке страницы."""
    return re.findall(r'data-promo-section="([^"]*)"', body)


# ─────────────────────── характеризация: без блоков «Liste» ───────────────────────


def test_without_list_blocks_the_overview_is_todays_page():
    t = _tenant()
    _shop()
    body = _page(t)
    assert "data-ending-soon" in body
    assert "data-upcoming-strip" in body
    # Räumung, Wochenangebote, «More offers» — секции сегодняшнего вида
    assert body.count('<section class="mb-8">') == 3
    assert TYPE_CHIPS in body
    assert body.count("data-promo-search") == 1
    assert "data-promo-jump" not in body
    assert "data-promo-section" not in body


@pytest.mark.parametrize(
    "blocks",
    [
        [_text("t1", "LB3-Hinweis")],
        [_lb("p1", source="products")],
        [{**_lb("off", type="Räumung"), "enabled": False}, MAIN],
    ],
    ids=["text", "products", "disabled"],
)
def test_other_blocks_do_not_switch_to_block_mode(blocks):
    t = _tenant(page_blocks={"promos": blocks})
    _shop()
    body = _page(t)
    assert "data-promo-jump" not in body
    assert TYPE_CHIPS in body
    assert "data-ending-soon" in body and "data-upcoming-strip" in body
    assert body.count('<section class="mb-8">') == 3


# ─────────────────────────── режим блоков: остаток ───────────────────────────


def test_type_block_takes_its_section_out_of_the_main_list():
    t = _tenant(page_blocks={"promos": [_lb("b1", type="Räumung"), MAIN]})
    _shop()
    body = _page(t)
    assert _sections(body) == ["Wochenangebote", ""]
    block = _segment(body, 'data-sf-promo-type="Räumung"')
    assert "LB3-Raeumung-1" in block and "LB3-Raeumung-2" in block
    # встроенные полосы на месте — их блок не заменяет
    assert "data-ending-soon" in body and "data-upcoming-strip" in body


def test_narrowed_type_block_keeps_the_types_section():
    """«Räumung · endet bald» — не та же выборка: секция рубрики остаётся."""
    t = _tenant(page_blocks={"promos": [_lb("b1", type="Räumung", endet="woche"), MAIN]})
    _shop()
    assert set(_sections(_page(t))) == {"Räumung", "Wochenangebote", ""}


@pytest.mark.parametrize(
    "data",
    [{"type": "sys:mystery"}, {"sort": "rabatt", "title": "Top"}],
    ids=["builtin-type", "sort-only"],
)
def test_blocks_without_an_equivalent_take_nothing_away(data):
    t = _tenant(page_blocks={"promos": [_lb("b1", **data), MAIN]})
    _shop()
    body = _page(t)
    assert "data-promo-jump" in body  # режим блоков включён
    assert set(_sections(body)) == {"Räumung", "Wochenangebote", ""}
    assert "data-ending-soon" in body and "data-upcoming-strip" in body


def test_ending_block_replaces_ending_soon():
    t = _tenant(page_blocks={"promos": [_lb("b1", endet="woche", title="Endet bald"), MAIN]})
    _shop()
    body = _page(t)
    assert "data-ending-soon" not in body
    assert "LB3-Bald-weg" in _segment(body, 'data-sf-list="promotions"')
    assert "data-upcoming-strip" in body
    assert set(_sections(body)) == {"Räumung", "Wochenangebote", ""}


def test_empty_ending_block_does_not_hide_ending_soon():
    """Блок «Endet heute», которому сегодня нечего показать, полосу не гасит: иначе в
    дни без сегодняшних концов страница теряла бы выделение «скоро закончатся»."""
    t = _tenant(page_blocks={"promos": [_lb("b1", endet="heute"), MAIN]})
    _promo("LB3-Bald-weg", "", ends_in=2)
    _promo("LB3-Lange", "", ends_in=30)
    body = _page(t)
    assert "data-ending-soon" in body


def test_ending_block_with_a_type_keeps_ending_soon():
    t = _tenant(page_blocks={"promos": [_lb("b1", type="Räumung", endet="woche"), MAIN]})
    _shop()
    assert "data-ending-soon" in _page(t)


def test_upcoming_block_replaces_vorschau():
    t = _tenant(page_blocks={"promos": [_lb("b1", phase="upcoming"), MAIN]})
    _shop()
    body = _page(t)
    assert 'data-upcoming="' not in body  # встроенной «Vorschau» нет
    block = _segment(body, 'data-sf-list="promotions"')
    assert "LB3-Zukunft" in block and "data-promo-starts" in block


def test_typed_upcoming_block_keeps_vorschau():
    t = _tenant(page_blocks={"promos": [_lb("b1", phase="upcoming", type="Räumung"), MAIN]})
    _shop()
    assert 'data-upcoming="' in _page(t)


def test_time_grouping_drops_the_bucket_an_ending_block_shows():
    t = _tenant(
        promo_grouping="time",
        page_blocks={"promos": [_lb("b1", endet="woche"), MAIN]},
    )
    _shop()
    body = _page(t)
    sections = _sections(body)
    assert "heute" not in sections and "woche" not in sections
    assert "laenger" in sections


def test_flat_main_list_is_the_remainder_under_a_heading():
    t = _tenant(page_blocks={"promos": [_lb("b1", type="Räumung"), MAIN]})
    _promo("LB3-Raeumung-1", "Räumung")
    _promo("LB3-Raeumung-2", "Räumung")
    _promo("LB3-Solo", "Wochenangebote")
    body = _page(t)
    main = body[body.index("data-pb-main") :]
    # остатку не набирается секция → плоская сетка, но с заголовком и якорем
    assert 'id="aktionen-rest"' in main
    assert "LB3-Solo" in main and "LB3-Raeumung-1" not in main


def test_list_view_is_a_view_not_a_filter():
    """«Liste» (?ansicht=liste, шаблон «Preisliste») — вид основного списка: блоки
    остаются, таблица = остаток."""
    t = _tenant(page_blocks={"promos": [_lb("b1", type="Räumung"), MAIN]})
    _shop()
    body = _page(t, ansicht="liste")
    assert 'data-sf-promo-type="Räumung"' in body
    table = _segment(body, "data-promo-table", end="</table>")
    assert "LB3-Woche-1" in table and "LB3-Raeumung-1" not in table


def test_no_empty_state_when_blocks_show_every_offer():
    t = _tenant(page_blocks={"promos": [_lb("b1", type="Räumung"), MAIN]})
    _promo("LB3-Raeumung-1", "Räumung")
    body = _page(t)
    assert "LB3-Raeumung-1" in body
    assert "data-promo-empty" not in body


def test_empty_state_stays_when_nothing_is_on_offer():
    t = _tenant(page_blocks={"promos": [_lb("b1", type="Räumung"), MAIN]})
    assert "data-promo-empty" in _page(t)


# ─────────────────────── «Demnächst»: данные и редактор ───────────────────────


def test_upcoming_is_stored_as_phase_and_drops_the_ending_filters():
    out = siteconfig.normalize_page_blocks(
        {
            "promos": [
                _lb("x", endet="upcoming", rabatt=30, sort="rabatt", type="Räumung"),
            ]
        }
    )
    assert out["promos"][0]["data"] == {
        "source": "promotions",
        "phase": "upcoming",
        "type": "Räumung",
    }


def test_phase_is_accepted_directly_and_garbage_is_dropped():
    out = siteconfig.normalize_page_blocks(
        {
            "promos": [
                _lb("a", phase="upcoming"),
                _lb("b", phase="vergangen"),
                _lb("c", source="products", phase="upcoming"),
            ]
        }
    )
    data = {b["id"]: b["data"] for b in out["promos"]}
    assert data["a"].get("phase") == "upcoming"
    assert "phase" not in data["b"] and "phase" not in data["c"]


def test_phase_does_not_travel_into_a_translation():
    assert "phase" in siteconfig.NON_TRANSLATABLE_FIELDS


def test_upcoming_block_shows_only_future_scheduled_promotions_as_previews():
    t = _tenant(page_blocks={"promos": [_lb("b1", phase="upcoming", limit=1)]})
    _promo("LB3-Aktiv")
    _promo("LB3-Bald", status="scheduled", starts_in=3)
    _promo("LB3-Spaeter", status="scheduled", starts_in=9)
    _promo("LB3-Verpasst", status="scheduled", starts_in=-1)
    block = _segment(_page(t), 'data-sf-list="promotions"')
    assert "LB3-Bald" in block
    assert "LB3-Spaeter" not in block  # лимит 1, порядок — по старту
    assert "LB3-Aktiv" not in block and "LB3-Verpasst" not in block
    assert "data-promo-starts" in block and "data-countdown" not in block
    # страницы «будущих» нет — ссылки «Alle N →» тоже нет, даже при обрезке
    assert "data-sf-list-all" not in block


def test_upcoming_block_with_a_type_shows_only_that_type():
    _promo("LB3-Bald-R", "Räumung", status="scheduled", starts_in=3)
    _promo("LB3-Bald-W", "Wochenangebote", status="scheduled", starts_in=3)
    cfg = siteconfig.normalize({})
    out = list_blocks.resolve(cfg, {"source": "promotions", "phase": "upcoming", "type": "Räumung"})
    assert [p.title["de"] for p in out["items"]] == ["LB3-Bald-R"]
    assert out["preview"] is True and out["more"] is False


def _builder(tenant):
    from apps.core import views

    return views.home_builder_view(_req(tenant, "/dashboard/site/home/")).content.decode()


def test_editor_offers_demnaechst_and_keeps_it_selected():
    t = _tenant(page_blocks={"promos": [_lb("b1", phase="upcoming")]})
    body = _builder(t)
    select = _segment(body, 'name="cb_b1_endet"', end="</select>")
    assert re.search(r'value="upcoming"\s+selected', select)


def test_save_keeps_demnaechst():
    from apps.core import views

    t = _tenant(page_blocks={"promos": [_lb("b1")]})
    post = {
        "pb_present": "1",
        "pb_id": ["b1"],
        "pb_page_b1": "promos",
        "cb_type_b1": "list",
        "order_cb_b1": "1",
        "enabled_cb_b1": "on",
        "cb_b1_source": "promotions",
        "cb_b1_endet": "upcoming",
    }
    resp = views.home_builder_view(_req(t, "/dashboard/site/home/", "post", post))
    assert resp.status_code == 302
    t.refresh_from_db()
    stored = siteconfig.normalize(t.site_config)["page_blocks"]["promos"][0]["data"]
    assert stored.get("phase") == "upcoming" and "endet" not in stored


# ─────────────────────── страница типа и результаты ───────────────────────


@pytest.mark.parametrize(
    "params",
    [
        {"gruppe": "Räumung"},
        {"q": "LB3"},
        {"endet": "woche"},
        {"sort": "rabatt"},
        {"rabatt": "20"},
    ],
    ids=["type-page", "search", "ending", "sort", "discount"],
)
def test_promo_list_blocks_stay_off_type_pages_and_results(params):
    t = _tenant(
        page_blocks={"promos": [_lb("b1", sort="rabatt", title="LB3-Top"), _text("t1", "LB3-Text")]}
    )
    _shop()
    body = _page(t, **params)
    assert 'data-sf-list="promotions"' not in body
    assert "LB3-Text" in body  # прочие блоки — как раньше
    assert "data-promo-jump" not in body


# ─────────────────────────────── Sprungleiste ───────────────────────────────


def _chips(body):
    """[(якорь, подпись, счётчик)] чипов полосы."""
    return [
        (anchor, label.strip(), int(count))
        for anchor, label, count in re.findall(
            r'data-jump="([^"]+)"[^>]*>([^<]*)<span[^>]*data-jump-count[^>]*>(\d+)<', body
        )
    ]


def test_jump_bar_lists_the_sections_in_page_order():
    t = _tenant(
        page_blocks={
            "promos": [
                _lb("oben", type="Räumung", title="LB3 Räumung jetzt"),
                MAIN,
                _lb("unten", sort="rabatt", title="LB3 Top-Rabatte"),
            ]
        }
    )
    _shop()
    body = _page(t)
    chips = _chips(body)
    assert [anchor for anchor, _label, _n in chips] == [
        "lb-oben",
        "aktionen-bald",
        "aktionen-vorschau",
        "aktionen-1",
        "aktionen-2",
        "lb-unten",
    ]
    for anchor, _label, _n in chips:
        assert f'id="{anchor}"' in body, anchor
    assert chips[0][1:] == ("LB3 Räumung jetzt", 2)
    assert chips[3][1:] == ("Wochenangebote", 2)


def test_jump_bar_skips_blocks_with_nothing_to_show():
    t = _tenant(page_blocks={"promos": [_lb("leer", type="Gibt-es-nicht"), MAIN]})
    _shop()
    anchors = [anchor for anchor, _label, _n in _chips(_page(t))]
    assert "lb-leer" not in anchors and "aktionen-1" in anchors


def test_jump_bar_holds_the_search_and_the_filters():
    t = _tenant(page_blocks={"promos": [_lb("b1", type="Räumung"), MAIN]})
    _shop()
    body = _page(t)
    bar = _segment(body, "data-promo-jump", end="</nav>")
    # поиск по акциям один — в полосе (поиск в шапке сайта ведёт в другой листинг)
    assert "data-promo-search" in bar and body.count("data-promo-search") == 1
    assert 'name="q"' in _segment(bar, "data-promo-search", end="</form>")
    # входы на страницы типов и системные фильтры — в панели полосы, не над списком
    assert TYPE_CHIPS in bar and body.count(TYPE_CHIPS) == 1
    assert "data-promo-filters" in bar


def test_jump_script_lives_outside_the_swap_zone():
    """KAT-5 подменяет `[data-listing-root]` fetch'ем — инлайн-скрипт внутри зоны после
    подмены не исполнился бы (урок HF). Скрипт полосы — снаружи, делегированный."""
    t = _tenant(page_blocks={"promos": [_lb("b1", type="Räumung"), MAIN]})
    _shop()
    body = _page(t)
    assert body.index("__sfJumpBound") > body.index("<!--/listing-root-->")


# ───────────────────── LB-3b: пресет страницы и подсказка Студии ─────────────────────


def test_promos_host_offers_standard_and_prospekt_presets():
    assert [p["key"] for p in page_presets.presets_for("promos")] == ["standard", "prospekt"]


def test_prospekt_preset_builds_blocks_above_the_main_list():
    _shop()
    cfg = {}
    assert page_presets.apply_page_preset(cfg, "promos", "prospekt")
    rows = siteconfig.normalize(cfg)["page_blocks"]["promos"]
    keys = [b.get("key") for b in rows]
    assert keys[-1] == "main"  # все блоки пресета — НАД основным списком
    lists = [b["data"] for b in rows if b.get("key") == "list"]
    assert any(d.get("endet") == "heute" and d.get("out") == "slider" for d in lists)
    assert any(d.get("phase") == "upcoming" for d in lists)
    # по блоку на каждую живую рубрику (встроенные типы — нет: они пересекают рубрики)
    assert sorted(d["type"] for d in lists if d.get("type")) == ["Räumung", "Wochenangebote"]


def test_prospekt_preset_is_idempotent_and_keeps_the_owners_blocks():
    _shop()
    cfg = {"page_blocks": {"promos": [_text("mine", "LB3-Meins")]}}
    page_presets.apply_page_preset(cfg, "promos", "prospekt")
    first = siteconfig.normalize(cfg)["page_blocks"]["promos"]
    page_presets.apply_page_preset(cfg, "promos", "prospekt")
    second = siteconfig.normalize(cfg)["page_blocks"]["promos"]
    assert first == second
    assert [b.get("id") for b in second].count("mine") == 1
    # блок владельца был под списком — там и остался
    assert [b.get("key") for b in second].index("main") < [b.get("id") for b in second].index(
        "mine"
    )
    assert page_presets.current_preset(siteconfig.normalize(cfg), "promos") == "prospekt"


def test_standard_preset_takes_back_only_the_seeded_blocks():
    _shop()
    cfg = {"page_blocks": {"promos": [_text("mine", "LB3-Meins")]}}
    page_presets.apply_page_preset(cfg, "promos", "prospekt")
    page_presets.apply_page_preset(cfg, "promos", "standard")
    rows = siteconfig.normalize(cfg)["page_blocks"]["promos"]
    assert [b.get("id") for b in rows] == ["mine"]
    assert page_presets.current_preset(siteconfig.normalize(cfg), "promos") == "standard"


def test_builder_suggests_a_block_for_each_type_without_one():
    t = _tenant(page_blocks={"promos": [_lb("b1", type="Räumung"), MAIN]})
    _shop()
    body = _builder(t)
    assert 'value="add_type_block:Wochenangebote"' in body
    assert 'value="add_type_block:Räumung"' not in body  # у неё блок уже есть
    assert 'value="use_page_preset:promos:prospekt"' in body


def test_add_type_block_puts_it_above_the_main_list():
    from apps.core import views

    t = _tenant(page_blocks={"promos": [_lb("b1", type="Räumung"), MAIN, _text("t1", "x")]})
    _shop()
    post = {"action": "add_type_block:Wochenangebote", "page_path": "/aktionen/"}
    resp = views.home_builder_view(_req(t, "/dashboard/site/home/", "post", post))
    assert resp.status_code == 302
    t.refresh_from_db()
    rows = siteconfig.normalize(t.site_config)["page_blocks"]["promos"]
    keys = [(b.get("key"), (b.get("data") or {}).get("type")) for b in rows]
    assert keys == [
        ("list", "Räumung"),
        ("list", "Wochenangebote"),
        ("main", None),
        ("text", None),
    ]


def test_page_preset_keeps_the_owners_translation_on_its_block():
    """Пресет вставляет блоки ПЕРЕД блоком владельца — его перевод обязан уехать с ним
    (класс LB-2 §11.7: оверлей мёржится по позиции)."""
    from apps.core import views

    t = _tenant(
        page_blocks={"promos": [_text("mine", "LB3-Meins")]},
        i18n={"ru": {"page_blocks": {"promos": [{"data": {"title": "LB3-Моё"}}]}}},
    )
    t.enabled_locales = ["de", "ru"]
    t.save(update_fields=["enabled_locales"])
    _shop()
    post = {"action": "use_page_preset:promos:prospekt", "page_path": "/aktionen/"}
    views.home_builder_view(_req(t, "/dashboard/site/home/", "post", post))
    t.refresh_from_db()
    shown = siteconfig.localize(siteconfig.normalize(t.site_config), "ru")["page_blocks"]["promos"]
    titles = {b.get("id"): (b.get("data") or {}).get("title") for b in shown}
    assert titles["mine"] == "LB3-Моё"
    assert all(title != "LB3-Моё" for bid, title in titles.items() if bid != "mine")


def test_aktionsmarkt_demo_promotions_page_is_built_from_blocks():
    """Демо: /aktionen/ собрана пресетом «Prospekt» — блок на каждую рубрику, полоса."""
    from apps.tenants import demo_kits

    t = TenantFactory(slug=f"lb3demo{next(_N)}", name="Sparfuchs", business_type="grocery")
    assert demo_kits.apply_kit(t, "aktionsmarkt")
    t.refresh_from_db()
    rows = siteconfig.normalize(t.site_config)["page_blocks"]["promos"]
    seeded = [b for b in rows if str(b.get("id", "")).startswith("pb-promos-prospekt-")]
    rubrics = set(
        Promotion.objects.filter(status="active").exclude(group="").values_list("group", flat=True)
    )
    assert rubrics, "у кита есть рубрики акций"
    assert {b["data"].get("type") for b in seeded if b["data"].get("type")} == rubrics
    body = _page(t)
    assert "data-promo-jump" in body
    assert len(_chips(body)) >= len(rubrics)
    # секции рубрик ушли в блоки: в остатке — только акции без рубрики
    assert set(_sections(body)) <= {""}
