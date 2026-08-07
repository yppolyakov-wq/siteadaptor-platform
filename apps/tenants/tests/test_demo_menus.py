"""Структурные инварианты меню демо-китов (аудит 2026-08-06).

Меню кита — данные, а не код: узел с опечаткой или с целью, которой нет в
реестре, НЕ падает — он молча выпадает из шапки (`menu._resolve` отбрасывает
узел без ссылки). Именно так у демо годами жили дыры: у ресторана меню вообще
не было, у ретрита из шапки нельзя было попасть в размещение, у отеля «Buchen»
вёл на несуществующий якорь, а у туров «Kontakt» ссылался на страницу, которой
нет в `_PAGE_URL_NAMES`.

Эти замки проверяют кит как данные — без БД: каждая цель обязана быть
резолвимой, а каждый якорь — существовать на главной этого кита.
"""

import pytest

from apps.tenants import demo_kits, menu
from apps.tenants.templatetags import siteui


def _nodes(kit):
    """Плоский список всех узлов меню кита (обе стороны, вместе с детьми)."""
    out = []

    def walk(items):
        for item in items:
            out.append(item)
            walk(item.get("children") or [])

    for side in ("top", "bottom"):
        walk((kit.menus or {}).get(side, {}).get("items", []))
    return out


def _kit_ids():
    return sorted(demo_kits.KITS)


def _active_modules(kit) -> set:
    """Модули, активные у тенанта этого кита.

    Активность — «всё, кроме выключенного»: онбординг гасит нерелевантные типу
    бизнеса (`default_disabled_for`), а `enable_modules` кита возвращает нужные
    обратно (см. apply_kit). Список `enable_modules` — НЕ полный набор активного.
    """
    from apps.core import modules

    disabled = set(modules.default_disabled_for(kit.business_type or "")) - set(kit.enable_modules)
    return {spec.key for spec in modules.REGISTRY if spec.key not in disabled}


@pytest.mark.parametrize("key", _kit_ids())
def test_page_targets_are_resolvable(key):
    """Цель типа `page` обязана быть в реестре — иначе пункт молча исчезает."""
    kit = demo_kits.KITS[key]
    unknown = [
        n["target"]
        for n in _nodes(kit)
        if n.get("type") == "page" and n.get("target") not in menu._PAGE_URL_NAMES
    ]
    assert not unknown, f"{key}: неизвестные страницы в меню — {unknown}"


@pytest.mark.parametrize("key", _kit_ids())
def test_archetype_targets_are_active_modules(key):
    """Цель типа `archetype` гаснет при выключенном модуле — значит в демо-меню
    должны стоять только модули, которые кит действительно включает."""
    kit = demo_kits.KITS[key]
    active = _active_modules(kit)
    bad = [
        n["target"]
        for n in _nodes(kit)
        if n.get("type") == "archetype" and n.get("target") not in active
    ]
    assert not bad, f"{key}: в меню модули, которых у кита нет — {bad}"


@pytest.mark.parametrize("key", _kit_ids())
def test_anchors_point_at_sections_present_on_home(key):
    """Якорь `/#foo` прокручивает главную к `id="foo"`. Этот id рендерится
    ТОЛЬКО если соответствующая секция включена у кита (см. `_kit_sections`) —
    иначе клик по пункту меню не делает ничего."""
    kit = demo_kits.KITS[key]
    anchor_to_section = {v: k for k, v in siteui._BLOCK_ANCHOR_ID.items()}
    enabled = {row["key"] for row in demo_kits._kit_sections(kit) if row.get("enabled")}

    dead = []
    for node in _nodes(kit):
        if node.get("type") != "anchor":
            continue
        target = (node.get("target") or "").lstrip("/").lstrip("#")
        section = anchor_to_section.get(target)
        if section is None or section not in enabled:
            dead.append(node.get("target"))
    assert not dead, f"{key}: якоря ведут в никуда — {dead}"


@pytest.mark.parametrize("key", _kit_ids())
def test_content_sections_have_a_page_in_menu(key):
    """ST-8 (запрос владельца «отдельные страницы, а не разделы главной»): если
    у кита есть галерея / команда / отзывы, до них должен вести пункт меню.

    Исключение — retreat: у него учителя живут на собственной странице
    `/lehrer/` (R3), «Unser Team» был бы её дублем."""
    kit = demo_kits.KITS[key]
    pages = {n.get("target") for n in _nodes(kit) if n.get("type") == "page"}
    urls = {n.get("target") for n in _nodes(kit) if n.get("type") == "url"}

    missing = []
    if kit.gallery_kw and "gallery" not in pages:
        missing.append("gallery")
    if kit.team and "team" not in pages and "/lehrer/" not in urls:
        missing.append("team")
    if (kit.reviews_seed or kit.testimonials) and "reviews" not in pages:
        missing.append("reviews")
    assert not missing, f"{key}: контент есть, а страницы в меню нет — {missing}"


@pytest.mark.parametrize("key", _kit_ids())
def test_every_kit_has_its_own_menu(key):
    """Без своего меню шапка выводится из легаси-`nav` (плоский список модулей) —
    так у ресторана не было ни галереи, ни отзывов, ни команды."""
    assert (kit := demo_kits.KITS[key]).menus, f"{key}: кит без собственного меню"
    assert kit.menus.get("top", {}).get("items"), f"{key}: пустое верхнее меню"


@pytest.mark.parametrize("key", _kit_ids())
def test_primary_sellable_modules_are_reachable(key):
    """Модуль, у которого есть публичная страница-«главная» архетипа и который
    кит наполняет, обязан быть достижим из меню (архетип-узлом, категорией или
    прямой ссылкой) — иначе посетитель не найдёт то, что мы продаём."""
    kit = demo_kits.KITS[key]
    nodes = _nodes(kit)
    reached = {n.get("target") for n in nodes if n.get("type") == "archetype"}
    # Каталог достижим и через узлы-категории, акции — через группы акций.
    has_category_node = any(n.get("type") == "category" for n in nodes)
    if any(n.get("type") == "promo_group" for n in nodes):
        reached.add("promotions")

    filled = set()
    if kit.categories:
        filled.add("catalog")
    if kit.services:
        filled.add("booking")
    if kit.stay_units:
        filled.add("stays")
    if kit.events:
        filled.add("events")
    if kit.promotions_spec:
        filled.add("promotions")

    missing = sorted(
        m for m in filled if m not in reached and not (m == "catalog" and has_category_node)
    )
    assert not missing, f"{key}: наполнено, но не выведено в меню — {missing}"
