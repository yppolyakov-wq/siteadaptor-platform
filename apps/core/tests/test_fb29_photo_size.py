"""FB-29.6: фото в редакторе страниц — ширина в процентах ИЛИ пикселях, высота с замком
пропорций, «Zuschneiden» на самом фото и вверху окна (макет C)."""

import pathlib

from apps.core import richtext

EDITOR = pathlib.Path("templates/catalog/_richtext_editor.html")
CSS = pathlib.Path("static/src/app.css")


def _fig(cls, img=""):
    return f'<figure class="{cls}"><img src="/media/p/a.png" alt=""{img}></figure>'


def test_pixel_width_survives_the_sanitizer():
    out = richtext.sanitize_page(_fig("sf-w-px sf-center", ' width="640"'))
    assert "sf-w-px" in out and 'width="640"' in out


def test_pixel_and_percent_width_exclude_each_other():
    assert 'class="sf-w-px"' in richtext.sanitize_page(_fig("sf-w-50 sf-w-px", ' width="300"'))
    assert 'class="sf-w-50"' in richtext.sanitize_page(_fig("sf-w-px sf-w-50"))


def test_pixel_width_takes_only_plain_numbers():
    out = richtext.sanitize_page(_fig("sf-w-px", ' width="640px;position:fixed"'))
    assert "position" not in out and "640px" not in out
    assert "style" not in richtext.sanitize_page(
        '<figure class="sf-w-px" style="width:9999px"><img src="/media/p/a.png" alt=""></figure>'
    )


def test_old_photos_look_as_before():
    """Правило «фото во всю ширину рамки» не действует только у фото с шириной в пикселях."""
    css = CSS.read_text()
    assert ".sf-page-body figure:not(.sf-w-px) img" in css
    assert ".sf-page-body figure.sf-w-px" in css and "max-width: 100%" in css
    html = _fig("sf-w-45")
    assert richtext.sanitize_page(html) == html


def test_editor_offers_units_lock_and_crop_on_the_photo():
    src = EDITOR.read_text()
    for marker in (
        "data-rte-unit",  # переключатель Prozent / Pixel
        "data-rte-lock",  # замок «Seitenverhältnis halten»
        "data-rte-height",  # поле высоты
        "rte-figbar",  # кнопки «Zuschneiden» и «Ersetzen» прямо на фото
        "data-rte-size",  # значок «640 × 210 px»
        "sf-w-px",
    ):
        assert marker in src, marker
    # служебные кнопки на фото не попадают в сохранённую разметку
    clean = src[src.index("function cleanClone") : src.index("function value(")]
    assert "rte-figbar" in clean


def test_editor_rules_know_the_pixel_class():
    import re

    assert re.fullmatch(richtext.editor_rules()["cls"], "sf-w-px")
