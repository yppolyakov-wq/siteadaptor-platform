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


# --- аудит 2026-08-06: переводы демо не должны лежать мёртвым грузом ----------

# Ключ site_config → поле кита, которое его наполняет. Имя ключа КОНФИГА, а не
# поля кита: обход переводов ходит по конфигу (полоса преимуществ — `usp_bar`,
# хотя у кита поле называется `usp`; промах на этом имени и был дефектом).
_TEXT_CONFIG_SOURCES = {
    "usp_bar": lambda k: k.usp,
    "team": lambda k: k.team,
    "faq": lambda k: k.faq,
    "testimonials": lambda k: k.testimonials,
    "trust": lambda k: k.trust,
    "process": lambda k: k.process,
    "cta": lambda k: k.cta,
    "heroes": lambda k: k.heroes,
}


def test_all_text_keys_kits_fill_are_translated():
    """Класс дефектов «перевод есть в словаре, но не доезжает до витрины».

    Обход демо-переводов идёт по СПИСКУ ключей (`_TRANSLATABLE_CONFIG_KEYS`).
    Ключ, который кит заполняет текстом, но которого нет в списке, молча
    остаётся немецким на всех локалях — так было с `usp_bar` (полоса
    преимуществ) и `team` (роли), хотя переводы для них в словарях лежали.
    """
    from apps.tenants import demo_i18n
    from apps.tenants.demo_kits import KITS

    covered = set(demo_i18n._TRANSLATABLE_CONFIG_KEYS)
    missing = sorted(
        key
        for key, getter in _TEXT_CONFIG_SOURCES.items()
        if key not in covered and any(getter(kit) for kit in KITS.values())
    )
    assert not missing, f"киты заполняют, а обход переводов не знает: {missing}"


def test_demo_dictionary_translates_usp_and_roles():
    """Обратная сторона: ключ в обходе есть, а переводов в словаре нет — витрина
    всё равно останется немецкой. Проверяем на реальных строках китов."""
    from apps.tenants import demo_i18n
    from apps.tenants.demo_kits import KITS

    strings = set()
    for kit in KITS.values():
        # GK-5: usp-кортежи теперь (icon, label[, text]) — тексты столпов тоже в замке.
        strings.update(u[1] for u in (kit.usp or []))
        strings.update(u[2] for u in (kit.usp or []) if len(u) > 2 and u[2])
        strings.update(role for _name, role, *_rest in (kit.team or []) if role)
    assert strings, "у китов нет ни usp, ни ролей — проверять нечего"

    untranslated = sorted(s for s in strings if demo_i18n.t(s, "en") is None)
    assert len(untranslated) < len(strings) * 0.4, (
        f"не переведено {len(untranslated)} из {len(strings)}: {untranslated[:8]}"
    )


# --- фидбэк 2026-08-07: строка меню не должна переполняться -------------------


@pytest.mark.parametrize("key", _kit_ids())
def test_top_menu_fits_one_row(key):
    """«Mehr ▾» появляется, когда пункты не влезают в ~788 px (контейнер шапки
    max-w-7xl, ширина не растёт даже на 1920 px). Владелец резонно считает эту
    кнопку лишней: разделы прячет автоматика, а не замысел. Поэтому меню кита
    обязано укладываться в строку — второстепенное сворачивается под «Über uns»."""
    kit = demo_kits.KITS[key]
    items = (demo_kits._compact_menu(kit.menus) or {}).get("top", {}).get("items", [])
    width = demo_kits._menu_row_width(i.get("label", "") for i in items)
    # 788 px — измеренная ширина строки на широком экране. Бюджет сворачивания
    # (620) строже: он держит запас и для ноутбучных 1024 px. Здесь проверяем
    # именно жёсткий предел: за ним «Mehr» появляется гарантированно.
    assert width <= 788, f"{key}: строка меню ≈{width:.0f} px — хвост уедет в «Mehr»"


@pytest.mark.parametrize("key", _kit_ids())
def test_compacting_loses_no_menu_entries(key):
    """Сворачивание ПЕРЕМЕЩАЕТ пункты в подменю, а не выбрасывает их: иначе
    разделы исчезли бы из навигации совсем."""
    kit = demo_kits.KITS[key]

    def targets(menus):
        out = []

        def walk(items):
            for i in items:
                out.append((i.get("type"), i.get("target")))
                walk(i.get("children") or [])

        walk((menus or {}).get("top", {}).get("items", []))
        return sorted(out)

    assert targets(demo_kits._compact_menu(kit.menus)) == targets(kit.menus)


def test_compacting_keeps_selling_entries_in_the_row():
    """В подменю уезжают только разделы «о нас». То, что бизнес продаёт
    (каталог/бронь/акции/события), обязано остаться в строке.

    Сравниваем ДО и ПОСЛЕ: часть китов кладёт архетипы в подменю осознанно
    (у pranasy `loyalty` — ребёнок группы «Treue & Aktionen»), и это не наше дело.
    Наше — не утащить туда ничего сверх того."""
    for key, kit in demo_kits.KITS.items():

        def row_targets(menus):
            items = (menus or {}).get("top", {}).get("items", [])
            return {i.get("target") for i in items if i.get("type") in ("archetype", "category")}

        before = row_targets(kit.menus)
        after = row_targets(demo_kits._compact_menu(kit.menus))
        assert before <= after, (
            f"{key}: продающий раздел уехал из строки — {sorted(before - after)}"
        )


def test_kits_with_menu_sets_link_them_in_navigation():
    """MEN-13 (фидбэк владельца «где посмотреть варианты блюд в комплекте»):
    наборы меню были засеяны, но в шапку кита не выведены — до /kombi/ нельзя
    было дойти навигацией. Тот же класс, что «наполненный модуль без пункта
    меню»: контент есть, пути к нему нет."""

    def menu_paths(menus):
        """(цели узлов, есть ли подменю с плитками наборов)."""
        targets, tiles = set(), False

        def walk(items):
            nonlocal tiles
            for item in items or []:
                targets.add(item.get("target"))
                if item.get("with_combos"):
                    tiles = True
                walk(item.get("children"))

        walk((menus or {}).get("top", {}).get("items", []))
        walk((menus or {}).get("bottom", {}).get("items", []))
        return targets, tiles

    for key, kit in demo_kits.KITS.items():
        if not kit.combos:
            continue
        targets, tiles = menu_paths(kit.menus)
        # Путь к наборам — любой из трёх: отдельный пункт «Kombi/Menüs»,
        # подменю с ПЛИТКАМИ наборов (фидбэк владельца 2026-08-26: «оставить
        # меню картинками по наборам и категориям» — прямая ссылка на каждый
        # набор вместо общего пункта), или кит вовсе без своего меню (шапку
        # выводит авто-резолвер, и combos попадает туда по гейту).
        assert kit.menus is None or "combos" in targets or tiles, (
            f"{key}: у кита {len(kit.combos)} набор(ов) меню, но в навигации на них нет пути"
        )


@pytest.mark.parametrize("key", _kit_ids())
def test_categories_node_requires_catalog_module(key):
    """MEN-15: узел «Kategorien» строит подменю из каталога — у кита без
    активного catalog он молча выродится в одинокую ссылку на /sortiment/."""
    kit = demo_kits.KITS[key]
    if not any(n.get("type") == "categories" for n in _nodes(kit)):
        pytest.skip("кит не использует авто-подменю категорий")
    assert "catalog" in _active_modules(kit), f"{key}: узел категорий без модуля catalog"
    # и категории в ките должны быть — иначе подменю пустое
    assert kit.categories, f"{key}: узел категорий, но кит не засевает категории"
