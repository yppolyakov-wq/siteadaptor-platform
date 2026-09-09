"""STU-15: шаблон страницы у деталей и дефолт сортировки листингов.

План — `docs/stu15-detail-templates-plan-2026-09-09.md`. Закрывает остаток проверки
STU-14: у детали акции не было ни одного шаблона страницы (только у товара), у деталей
услуги/номера/события — только скрытие секций, а у листингов услуг/номеров/событий
владелец не мог задать сортировку по умолчанию (у каталога такая настройка есть с UB2-2).

Замки написаны ДО правок и краснеют на текущем коде.
"""

import pytest

from apps.core import studio_pages
from apps.tenants import siteconfig

pytestmark = pytest.mark.django_db


# ── 15a. Деталь акции: свой шаблон страницы ──────────────────────────────────


def test_promotion_detail_styles_registry_exists():
    """Реестр шаблонов страницы акции — единственный источник допустимых значений."""
    from apps.promotions import group_styles

    codes = [c for c, _l, _h in group_styles.PROMOTION_DETAIL_STYLES]
    assert codes[0] == "", "первый вариант — Standard (прежний вид)"
    assert len(codes) >= 3, "нужны хотя бы Standard + два осмысленных шаблона"


def test_promotion_detail_style_resolver_prefers_the_offer():
    """Своё у акции побеждает дефолт сайта; мусор проваливается в прежний вид."""
    from apps.promotions import group_styles

    known = [c for c, _l, _h in group_styles.PROMOTION_DETAIL_STYLES if c][0]
    assert group_styles.promotion_detail_style(known, "") == known
    assert group_styles.promotion_detail_style("", known) == known, "дефолт сайта действует"
    assert group_styles.promotion_detail_style("quatsch", "") == "", "мусор → прежний вид"


def test_promotion_model_carries_page_style():
    """Поле на модели — иначе «только для этой акции» задать нечем (⚠️ миграция)."""
    from apps.promotions.models import Promotion

    assert Promotion._meta.get_field("page_style") is not None


# ── 15b. Детали услуги/номера/события: шаблон страницы ───────────────────────


@pytest.mark.parametrize("kind", ["service", "stay", "event"])
def test_detail_layout_resolver_for_every_kind(kind):
    """У каждой детали есть свой шаблон страницы (как `product_detail.layout`)."""
    assert siteconfig.detail_layout({f"{kind}_detail": {"layout": "tabs"}}, kind) == "tabs"
    assert siteconfig.detail_layout({}, kind) == "", "без ключа — прежний вид"
    assert siteconfig.detail_layout({f"{kind}_detail": {"layout": "quatsch"}}, kind) == ""


def test_detail_layout_survives_normalize():
    """Ключ переживает normalize (иначе Save билдера стирал бы выбор), но САМ
    `layout` не материализуется — golden-эталоны целы.

    Уточнение после сверки с эталонами: `service_detail`/`stay_detail`/`event_detail`
    материализуются нормализатором ВСЕГДА (`{"hidden": []}` в
    `golden/normalize_empty.json`), поэтому presence-minimal здесь относится к
    вложенному ключу раскладки, а не ко всей записи.
    """
    cfg = siteconfig.normalize({"service_detail": {"layout": "tabs"}})
    assert cfg["service_detail"]["layout"] == "tabs"
    assert "layout" not in siteconfig.normalize({})["service_detail"]


# ── 15c. Листинги: дефолт сортировки владельца ───────────────────────────────


@pytest.mark.parametrize("key", ["services_sort", "stays_sort", "events_sort"])
def test_listing_sort_default_is_configurable(key):
    """Дефолт сортировки листинга задаётся владельцем (у каталога он есть с UB2-2)."""
    cfg = siteconfig.normalize({key: "price_asc"})
    assert cfg[key] == "price_asc"
    assert key not in siteconfig.normalize({}), "presence-minimal: пустой конфиг пуст"


# ── Реестр Studio знает о новых настройках ───────────────────────────────────


def test_studio_registry_declares_the_new_settings():
    """Панель обязана предлагать их на СВОИХ типах страниц (правило STU-9).

    Принадлежность «настройка → тип страницы» живёт у ТИПА (`PageType.settings`),
    поэтому и проверяем оттуда: у самой настройки списка страниц нет.
    """
    by_page = {p.code: p.settings for p in studio_pages.PAGE_TYPES}
    assert "promo_detail_style" in studio_pages.SETTINGS, "нет настройки шаблона детали акции"
    assert "promo_detail_style" in by_page["promo"], "шаблон не предлагается на странице акции"
    for code, page in (
        ("service_detail_layout", "service"),
        ("stay_detail_layout", "stay"),
        ("event_detail_layout", "event"),
        ("services_sort", "services"),
        ("stays_sort", "stays"),
        ("events_sort", "events"),
    ):
        assert code in studio_pages.SETTINGS, f"настройка {code} не объявлена"
        assert code in by_page[page], f"{code} не предлагается на типе {page}"


def test_every_object_scoped_setting_has_its_own_value_set():
    """У КАЖДОЙ настройки с охватом «только здесь» — свой набор допустимых значений.

    Адверсариальный замок: пока валидатор Studio выбирал словарь по ВИДУ объекта,
    вторая настройка на той же модели (у акции — форма карточки и шаблон страницы)
    получала чужой реестр, и её законное значение отвергалось как мусор.
    """
    from apps.core import studio_scope

    for setting in studio_pages.SETTINGS.values():
        if not setting.has_object_scope:
            continue
        values = studio_scope._valid_values(setting)
        assert values, f"пустой набор значений у настройки {setting.code}"


# ── 15c. Дефолт сортировки действует на витрине ──────────────────────────────


@pytest.mark.parametrize(
    "key,kind",
    [("services_sort", "service"), ("stays_sort", "stay"), ("events_sort", "event")],
)
def test_listing_sort_values_come_from_the_facet_provider(key, kind):
    """Допустимые значения — те же, что предлагает тулбар листинга посетителю.

    Если бы список жил отдельной константой, кабинет мог бы предложить сортировку,
    которой у листинга нет (у номеров нет «Neueste», у событий тоже) — ровно тот
    класс «обещания без исполнения», который чинит правило STU-9.
    """
    from apps.core.facets import provider_for

    assert set(siteconfig.listing_sort_keys(key)) == set(provider_for(kind).sort_keys())
    assert "quatsch" not in siteconfig.listing_sort_keys(key)


def test_listing_sort_rejects_a_value_the_listing_cannot_do():
    """«Neueste» есть у услуг, но не у номеров — конфиг обязан это различать."""
    assert siteconfig.normalize({"services_sort": "newest"})["services_sort"] == "newest"
    assert "stays_sort" not in siteconfig.normalize({"stays_sort": "newest"})
