"""FB-23b: вывод видов панели меню A list · B tiles · C mega · D columns · G strip,
иконки пунктов и мобильный аккордеон на 3 уровня (решение владельца 2026-11-07)."""

import re

import pytest
from django.template.loader import render_to_string


def _child(label, *grand, image="", icon=""):
    return {
        "label": label,
        "url": f"/{label.lower()}/",
        "icon": icon,
        "image": image,
        "desc": f"{label} Text",
        "children": [_child(g) for g in grand],
    }


def _item(layout, *children, image="", desc=""):
    return {
        "label": "Shop",
        "url": "/shop/",
        "icon": "🛍",
        "children": list(children),
        "has_images": False,
        "layout": layout,
        "image": image,
        "desc": desc,
    }


def _nav(item):
    return render_to_string("storefront/_header_nav.html", {"storefront_menu": [item]})


@pytest.mark.parametrize("layout", ["list", "tiles", "mega", "columns"])
def test_each_panel_layout_has_its_own_markup(layout):
    html = _nav(_item(layout, _child("Brot", "Roggen"), _child("Kuchen")))
    assert f'data-menu-layout="{layout}"' in html
    assert "🛍" in html  # иконка пункта наконец рисуется


def test_mega_shows_third_level_of_the_first_section_and_switches_by_js():
    html = _nav(_item("mega", _child("Brot", "Roggen", "Dinkel"), _child("Kuchen", "Torte")))
    panes = re.findall(r'<div data-mega-pane="(\d)"([^>]*)>', html)
    assert [p[0] for p in panes] == ["0", "1"]
    assert "hidden" not in panes[0][1] and "hidden" in panes[1][1]  # без JS — первый
    assert "Roggen" in html and "Alles in Brot" in html
    base = open("templates/storefront/_base.html", encoding="utf-8").read()
    assert "data-mega-row" in base and "megaShow" in base


def test_columns_cap_links_and_show_the_banner_of_the_item():
    many = _child("Brot", *[f"S{i}" for i in range(10)])
    html = _nav(_item("columns", many, image="/media/sale.webp", desc="Sale −30 %"))
    assert len(re.findall(r'href="/s\d/"', html)) == 8  # ≤ 8 ссылок + «Alle anzeigen»
    assert "Alle anzeigen" in html
    assert "data-menu-banner" in html and "Sale −30 %" in html


def test_strip_item_is_a_plain_link_and_children_go_to_the_strip():
    item = _item("strip", _child("Brot", image="/b.webp"), _child("Kaffee", icon="☕"))
    nav = _nav(item)
    assert "data-nav-panel" not in nav.split('id="sf-nav-more"')[0]  # без выпадашки
    strip = render_to_string("storefront/menu/_strip.html", {"storefront_menu": [item]})
    assert 'data-menu-layout="strip"' in strip and "/b.webp" in strip and "☕" in strip


def test_mobile_menu_is_a_three_level_accordion():
    base = open("templates/storefront/_base.html", encoding="utf-8").read()
    mobile = base[base.index('id="sf-nav-mobile"') : base.index("</header>")]
    assert mobile.count("<details") == 2 and "data-menu-acc" in mobile
    assert "storefront/menu/_strip.html" in base


def test_footer_columns_render_above_the_legal_row():
    base = open("templates/storefront/_base.html", encoding="utf-8").read()
    footer = base[base.index("<footer") : base.index("</footer>")]
    assert footer.index("data-footer-columns") < footer.index("storefront-impressum")
    ctx = open("apps/core/context.py", encoding="utf-8").read()
    assert '"storefront_footer_menu": storefront_footer_menu' in ctx
