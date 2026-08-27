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
