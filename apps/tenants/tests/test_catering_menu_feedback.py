"""Фидбэк владельца 2026-08-26 (вечер) по витрине pranasy и кита catering.

«Наборы и просто блюда сливаются… наборы 4 в ряд на десктопе и убрать вид…
в меню сайта в пранаси сделай с картинками… нижнее меню кетринг ведёт на запрос,
а должно вести на страницу с кейтерингом… убери пункт меню — меню и пакеты;
оставить меню картинками по наборам и категориям, отправить запрос, наша работа.»
"""

from decimal import Decimal
from pathlib import Path

import pytest

from apps.tenants import demo_kits

TEMPLATES = Path(__file__).resolve().parents[3] / "templates"


def _read(name):
    return (TEMPLATES / name).read_text(encoding="utf-8")


def _walk(items):
    for item in items or []:
        yield item
        yield from _walk(item.get("children"))


@pytest.mark.parametrize("key", ["pranasy", "catering"])
def test_menu_offers_tiles_instead_of_a_packages_entry(key):
    """Пункт «Menüs & Pakete» убран, наборы едут плитками в подменю."""
    menus = demo_kits.KITS[key].menus
    nodes = list(_walk(menus["top"]["items"]))

    assert not any(n["label"] == "Menüs & Pakete" for n in nodes)
    assert any(n.get("with_combos") for n in nodes)


def test_pranasy_bottom_menu_opens_the_catering_page_not_the_form():
    bottom = demo_kits.KITS["pranasy"].menus["bottom"]["items"]
    catering = next(i for i in bottom if i["label"] == "Catering")

    assert catering["type"] == "category"
    assert catering["target"] == "catering"


def test_pranasy_catering_submenu_keeps_request_and_our_work():
    top = demo_kits.KITS["pranasy"].menus["top"]["items"]
    catering = next(i for i in top if i["label"] == "Catering")
    labels = [c["label"] for c in catering["children"]]

    assert "Anfrage" in labels  # отправить запрос
    assert "Unsere Arbeit" in labels  # наша работа


@pytest.mark.django_db
def test_combo_children_are_tiles_with_photo_and_own_url():
    """Плитки наборов несут ссылку и фото — иначе подменю выродится в текст."""
    from apps.catalog.models import Category, Combo
    from apps.tenants.menu import _combo_children
    from apps.tenants.tests.factories import TenantFactory

    tenant = TenantFactory.build()
    category = Category.objects.create(name="Catering", slug="catering")
    combo = Combo.objects.create(
        name="Menü Klassik",
        price=Decimal("19.50"),
        category=category,
        images=[{"url": "/media/combo.webp"}],
    )

    tiles = _combo_children(tenant, "catering")

    assert [t["url"] for t in tiles] == [f"/kombi/{combo.pk}/"]
    assert tiles[0]["image"] == "/media/combo.webp"
    # У набора имя — плоское поле с оверлеем переводов: через get_i18n подпись
    # приходила ПУСТОЙ, и плитка выглядела безымянной (поймано на стенде).
    assert tiles[0]["label"] == "Menü Klassik"


def test_with_combos_survives_config_normalisation():
    """normalize выбрасывает неизвестные ключи — флаг обязан быть в whitelist."""
    from apps.tenants import siteconfig

    cfg = siteconfig.normalize(
        {
            "menus": {
                "top": {
                    "items": [
                        {
                            "label": "Catering",
                            "type": "categories",
                            "target": "catering",
                            "with_combos": True,
                        }
                    ]
                }
            }
        }
    )

    assert cfg["menus"]["top"]["items"][0]["with_combos"] is True


def test_sets_and_dishes_are_visually_separated():
    html = _read("storefront/products.html")

    assert "data-category-sets" in html
    assert "data-category-dishes" in html  # свой заголовок у сетки блюд
    assert "Einzelne Gerichte" in html


def test_combo_grid_is_four_across_and_has_no_view_toggle():
    grid = _read("storefront/_combo_grid.html")

    assert "lg:grid-cols-4" in grid
    for page in ("storefront/products.html", "storefront/combos.html"):
        assert "_combo_view_toggle.html" not in _read(page), page


def test_dish_popup_is_fullscreen_on_phones():
    html = _read("storefront/_dish_info.html")
    box = html.split("data-dish-info", 1)[0].rsplit("<div", 1)[1]

    assert "h-full" in box  # на телефоне окно во весь экран
    assert "sm:h-auto" in box  # на десктопе прежний диалог
    assert "max-h-none" in box


def test_single_dish_does_not_stretch_across_the_row():
    """auto-fill растягивал ЕДИНСТВЕННОЕ блюдо на всю ширину группы."""
    for name in ("storefront/_combo_groups.html", "storefront/_combo_pool.html"):
        html = _read(name)
        assert "auto-fill,minmax(220px" not in html, name
        assert "sm:grid-cols-2" in html, name


# --- Фидбэк владельца 2026-08-27 -------------------------------------------
# «Сделай в пранаси по умолчанию на главной категории по 3 в ряд. А блюда по 6
# и над ними перенести фильтр и переключатель видов».


def test_toolbar_stands_directly_above_the_dishes():
    """Тулбар каркаса управляет блюдами: наборы выше, заголовок блюд — при нём."""
    html = _read("storefront/products.html")
    skeleton = _read("storefront/listing.html")

    # каркас: шапка → фасеты → тулбар → сетка
    assert (
        skeleton.index("{% block listing_header %}")
        < skeleton.index("{% block listing_toolbar %}")
        < skeleton.index("{% block listing_grid %}")
    )

    # секция наборов — в ШАПКЕ листинга (то есть над тулбаром)
    header = html.split("{% block listing_header %}", 1)[1].split("{% block listing_facets %}", 1)[
        0
    ]
    assert "data-category-sets" in header

    # заголовок блюд — в тулбаре, вплотную к своей сетке (не в шапке: между ними
    # встали бы плитки подкатегорий и панель фильтров)
    assert "data-category-dishes" not in header
    toolbar = html.split("{% block listing_toolbar %}", 1)[1].split("{% endblock %}", 1)[0]
    assert "data-category-dishes" in toolbar
    assert "{{ block.super }}" in toolbar
    grid = html.split("{% block listing_grid %}", 1)[1].split("{% endblock %}", 1)[0]
    assert "data-category-dishes" not in grid


def test_subcategory_grid_follows_the_categories_layout():
    """Число колонок подкатегорий было захардкожено — теперь это настройка."""
    from apps.tenants import siteconfig

    html = _read("storefront/products.html")
    assert "{{ subcategory_grid }}" in html
    assert "sm:grid-cols-3 lg:grid-cols-4 gap-3 mb-6" not in html  # прежний хардкод
    # верхний список звал {% grid_classes site … %}, но `site` вьюха не кладёт —
    # тег молча брал дефолт секции вместо настройки владельца
    assert "{{ categories_grid }}" in html
    assert "grid_classes site 'categories'" not in html

    def grid(cfg):
        return siteconfig.grid_class_string(
            {**siteconfig.section_layout(cfg, "categories"), "gap": "sm"}
        )

    # дефолт — байт-в-байт прежняя строка классов (без визуальной регрессии)
    assert grid({}) == "grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 gap-3"
    cfg = siteconfig.normalize(
        {"sections": [{"key": "categories", "enabled": False, "layout": {"preset": "cols3"}}]}
    )
    assert grid(cfg).endswith("lg:grid-cols-3 gap-3")


def test_pranasy_shows_three_categories_and_six_dishes_per_row():
    kit = demo_kits.KITS["pranasy"]

    assert kit.section_layouts["categories"]["preset"] == "cols3"
    assert kit.page_layouts["catalog"] == "cols6"


def test_kit_section_layout_reaches_the_config():
    """Раскладка секции обязана пережить normalize — иначе кит настроит впустую."""
    from apps.tenants import siteconfig
    from apps.tenants.demo_kits import _kit_sections

    kit = demo_kits.KITS["pranasy"]
    cfg = siteconfig.normalize({"sections": _kit_sections(kit)})

    assert siteconfig.section_layout(cfg, "categories")["cols"] == 3
