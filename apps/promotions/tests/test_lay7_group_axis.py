"""LAY-7 — ось вывода владельца действует на СТРАНИЦЕ ГРУППЫ акций.

Находка стенда 2026-09-10 (план `docs/lay-unified-output-plan-2026-09-09.md §14`):
LAY-3a-2 завёл ключ `promo_index_layout` и контрол в панели, но провёл его только
в две ветки `promotions_list.html`. Живой тенант с композицией группы или лентой
групп ни одну из них не рендерит — владелец выставляет «5 в ряд, 2 ряда» и не
видит ничего. Это класс «обещание без исполнения» (правило STU-9) внутри самой
волны, которая его лечит.

Замки написаны ДО правок и краснеют на текущем коде.
"""

from datetime import timedelta
from decimal import Decimal

import pytest
from django.test import RequestFactory
from django.utils import timezone

from apps.promotions import public_views
from apps.promotions.models import Promotion
from apps.tenants import siteconfig
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _tenant_urlconf(settings):
    settings.ROOT_URLCONF = "config.urls_tenant"


def _promo(title, group="Wochenangebote", days=3, **kw):
    kw.setdefault("status", "active")
    kw.setdefault("promo_type", "discount")
    kw.setdefault("price_override", Decimal("2.49"))
    kw.setdefault("compare_at_price", Decimal("3.49"))
    kw.setdefault("ends_at", timezone.now() + timedelta(days=days) if days else None)
    return Promotion.objects.create(title={"de": title}, group=group, **kw)


def _tenant(cfg=None):
    tenant = TenantFactory.build()
    tenant.site_config = siteconfig.normalize(cfg or {})
    return tenant


def _render(tenant, **params):
    request = RequestFactory().get("/aktionen/", params)
    request.tenant = tenant
    request.session = {}
    return public_views.promotion_list(request).content.decode()


# ── LAY-7a: пять композиций группы читают раскладку владельца ──────────────

# Композиция → её ПРЕЖНИЕ классы (паритет без ключа) и триплет колонок.
_COMPOSITIONS = [
    ("schaufenster", "grid grid-cols-2 sm:grid-cols-2 lg:grid-cols-3 gap-4 md:gap-6", "2/2/3"),
    ("prospekt", "grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 gap-3", "2/3/5"),
    ("magazin", "grid grid-cols-1 sm:grid-cols-2 gap-4 md:gap-6", "1/2/2"),
    ("countdown", "grid grid-cols-2 sm:grid-cols-2 lg:grid-cols-3 gap-4 md:gap-6", "2/2/3"),
]


@pytest.mark.parametrize("style,legacy,triplet", _COMPOSITIONS)
def test_composition_keeps_its_markup_without_the_key(style, legacy, triplet):
    """Паритет: ключа нет — композиция рисует ровно прежние классы.

    Шесть акций, а не четыре: при меньшем числе элементов, чем колонок, DL-14
    сам сужает триплет (авто-колонки), и замок мерил бы не то.
    """
    for i in range(6):
        _promo(f"Angebot {i}")
    body = _render(
        _tenant({"site_defaults": {"promo_group_style": style}}), gruppe="Wochenangebote"
    )
    assert legacy in body, style
    assert f'data-sf-cols="{triplet}"' in body, style


@pytest.mark.parametrize("style,legacy,_triplet", _COMPOSITIONS)
def test_owner_grid_wins_over_the_composition(style, legacy, _triplet):
    """Владелец выставил 4 в ряд — композиция это уважает (правило LAY-5/Р-3)."""
    for i in range(6):
        _promo(f"Angebot {i}")
    tenant = _tenant(
        {
            "site_defaults": {"promo_group_style": style},
            "promo_index_layout": {"preset": "cols4", "mobile": 2},
        }
    )
    body = _render(tenant, gruppe="Wochenangebote")
    assert "lg:grid-cols-4" in body, style
    assert legacy not in body, style
    assert 'data-sf-cols="2/3/4"' in body, style


def test_vergleich_columns_follow_the_owner_too():
    """«Vergleich» — тоже сетка: колонок столько, сколько задал владелец."""
    for i in range(4):
        _promo(f"Paket {i}")
    tenant = _tenant(
        {
            "site_defaults": {"promo_group_style": "vergleich"},
            "promo_index_layout": {"preset": "cols4", "mobile": 1},
        }
    )
    body = _render(tenant, gruppe="Wochenangebote")
    assert "data-group-compare" in body
    assert "lg:grid-cols-4" in body


def test_owner_tail_reaches_the_composition():
    """«Letzte Reihe» (хвост DL-14) — часть той же оси, значит доезжает и сюда."""
    for i in range(5):
        _promo(f"Angebot {i}")
    tenant = _tenant(
        {
            "site_defaults": {"promo_group_style": "prospekt"},
            "promo_index_layout": {"preset": "cols4", "tail": "fill"},
        }
    )
    assert 'data-sf-tail="fill"' in _render(tenant, gruppe="Wochenangebote")


# ── LAY-7b: лента групп читает «Reihen» и «Tempo» ──────────────────────────


def _grouped_promos():
    """Две группы по две акции: секцию получает группа от двух (MIN_GROUP_SECTION)."""
    for group in ("Wochenangebote", "Räumung"):
        for i in range(2):
            _promo(f"{group} {i}", group=group)


def test_group_strip_has_no_slider_parameters_without_the_key():
    """Паритет: без ключа лента прежняя — ни рядов, ни автопрокрутки."""
    _grouped_promos()
    body = _render(_tenant({"promo_layout": "slider"}))
    assert "data-promo-strip" in body
    # Урок класса MEN: негативный замок на ГОЛЫЙ маркер ловит комментарий самого
    # скрипта слайдера — сверяем разметочную форму атрибута.
    assert 'data-sf-rows="' not in body
    assert 'data-sf-speed="' not in body


def test_group_strip_takes_rows_and_speed_from_the_axis():
    """Контролы «Reihen»/«Tempo» в панели обязаны что-то менять на ленте."""
    _grouped_promos()
    tenant = _tenant(
        {
            "promo_layout": "slider",
            "promo_index_layout": {"preset": "cols4", "rows": 2, "speed": 6},
        }
    )
    body = _render(tenant)
    assert "data-promo-strip" in body
    assert 'data-sf-rows="2"' in body
    assert 'data-sf-speed="6"' in body


def test_slider_attrs_are_narrow_and_never_add_grid_attributes():
    """У flex-полосы `data-sf-cols`/`data-sf-tail` ничего не значат — не навешиваем."""
    from apps.tenants.templatetags import siteui

    out = siteui.sf_slider_attrs({"preset": "cols4", "rows": 2, "speed": 6})
    assert 'data-sf-rows="2"' in out and 'data-sf-speed="6"' in out
    assert "data-sf-cols" not in out and "data-sf-tail" not in out
    assert siteui.sf_slider_attrs({"preset": "cols4"}) == ""
    assert siteui.sf_slider_attrs(None) == ""


# ── LAY-7d: литеральный триплет — ФОЛБЭК, а не приказ ─────────────────────


def test_literal_cols_is_only_a_fallback_for_hardcoded_markup():
    """Найдено при LAY-7: `cols="2/2/3"` побеждал раскладку владельца.

    Тринадцать колл-сайтов передают и раскладку, и литеральный триплет (он
    описывает ПРЕЖНЮЮ жёсткую вёрстку). Пока литерал был сильнее, класс шёл от
    владельца (4 колонки), а `data-sf-cols` — от литерала (3): CSS «полных рядов»
    считал ряды не для той сетки, то есть хвост обрезался/распределялся неверно.
    """
    from apps.tenants.templatetags import siteui

    owner = {"preset": "cols4", "mobile": 2}
    assert 'data-sf-cols="2/3/4"' in siteui.sf_grid_attrs(owner, cols="2/2/3", count=8)
    # Без раскладки владельца литерал остаётся единственным источником.
    assert 'data-sf-cols="2/2/3"' in siteui.sf_grid_attrs(None, cols="2/2/3", count=8)
    assert 'data-sf-cols="2/2/3"' in siteui.sf_grid_attrs({}, cols="2/2/3", count=8)


def test_home_sections_keep_the_literal_triplet_of_a_hardcoded_style():
    """Граница правила: у секций главной семантика литерала ОБРАТНАЯ.

    `grid_attrs` всегда получает раскладку секции (она материализуется), а
    `cols="1/2/3"` метит стиль с ЖЁСТКОЙ сеткой (DL-11: categories compact) —
    шаблон сам решает через `layout_is_default`, показывать ли его. Если бы
    правило LAY-7d жило в `grid_attr_string`, литерал там стал бы мёртвым.
    """
    assert 'data-sf-cols="1/2/3"' in siteconfig.grid_attr_string(
        {"preset": "cols4", "mobile": 2}, cols="1/2/3", count=8
    )


# ── LAY-7c: ОДИН контрол на «сетка или лента» (решение владельца 2026-09-10) ──


def test_axis_slider_mode_turns_groups_into_a_strip():
    """Ось «Ausgabe: Slider» теперь и есть выключатель ленты групп."""
    _grouped_promos()
    tenant = _tenant({"promo_index_layout": {"preset": "cols4", "scroll": True}})
    body = _render(tenant)
    assert "data-promo-strip" in body
    assert "sf-scroll-grid" in body


def test_legacy_key_still_renders_a_strip_through_the_engine():
    """Живые сайты и демо-киты писали `promo_layout` — ключ читаем дальше."""
    _grouped_promos()
    body = _render(_tenant({"promo_layout": "slider"}))
    assert "data-promo-strip" in body
    assert "sf-scroll-grid" in body


def test_regale_composition_still_renders_strips():
    """Композиция «Regale» включает ленту во вьюхе — путь тот же."""
    _grouped_promos()
    tenant = _tenant({"promo_page_style": "regale"})
    assert "data-promo-strip" in _render(tenant)


def test_grid_mode_has_no_strip():
    _grouped_promos()
    body = _render(_tenant())
    assert "data-promo-strip" not in body
    assert 'data-grid="promo_list" class="grid' in body


def test_panel_no_longer_offers_the_duplicate_control():
    """Дубль убран из панели: контрол «Darstellung der Gruppen» и его запись."""
    from apps.core import studio_pages

    assert "promo_layout" not in studio_pages.SETTINGS
    used = {code for page in studio_pages.PAGE_TYPES for code in page.settings}
    assert "promo_layout" not in used
    markup = open("templates/tenant/site_home.html", encoding="utf-8").read()
    assert 'name="promo_layout"' not in markup
    assert 'data-stu-setting="promo_layout"' not in markup


def test_save_without_the_control_keeps_the_legacy_key():
    """Инвариант W0/W6: контрола нет — ключ живого сайта не должен пропасть."""
    cfg = siteconfig.normalize({"promo_layout": "slider"})
    assert cfg.get("promo_layout") == "slider"


def test_panel_shows_the_mode_that_the_page_actually_renders():
    """Легаси-ключ включает ленту — селект «Ausgabe» обязан показывать Slider.

    Иначе мы бы заменили один дубль другой рассинхронизацией: страница-лента, а
    панель пишет «Raster». Резолвер один на витрину и на панель.
    """
    layout = siteconfig.apply_legacy_promo_slider({}, "slider")
    assert layout.get("scroll") is True
    assert siteconfig.output_mode(layout) == "slider"
    # Без легаси-ключа раскладку не трогаем (в т.ч. остаётся пустой).
    assert siteconfig.apply_legacy_promo_slider({}, "") == {}
    # Явный выбор владельца сильнее: сетка остаётся сеткой, если он её выбрал.
    explicit = {"preset": "cols4", "scroll": True}
    assert siteconfig.apply_legacy_promo_slider(explicit, "slider") is explicit
