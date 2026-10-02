"""DL-24 (фидбэк владельца 2026-10-01 «ретро дизайн поплыл и markthalle»).

Форма фото витрины (DL-10, `site_defaults.media_shape`: «wide» ставят сборки Retro и
Markthalle, «round» — Frischmarkt) встретилась с горизонтальной формой карточки
«Ценник» (DL-19 regal), которую несёт кит дискаунтера.

Правила формы кадра писались под вертикальные карточки: `aspect-ratio` + `height:auto`.
У «Ценника» фото — боковая полоса во всю высоту карточки (`h-full min-h-[6rem]`), и
`aspect-ratio: 16/9` переносил минимальную высоту 96 px в минимальную ШИРИНУ 171 px:
фото вылезало из своей колонки (96/112 px) и закрывало цену и название. Круг давал
«пилюлю» 60×96 вместо круга. Замер стендом: из 7 форм товара и 7 форм акции × 3 форм
фото ломалась ровно эта пара (product+promo regal × wide), на обеих ширинах.

Замки уровня КЛАССА, а не одного шаблона: любое фото, высоту которого задаёт карточка
(`h-full`), обязано быть помечено боковым — тогда правила формы кадра считают его
миниатюрой по ширине колонки и не раздувают за её пределы.
"""

import pathlib
import re
from types import SimpleNamespace

from django.template.loader import render_to_string

TEMPLATES = pathlib.Path("templates")
BASE = TEMPLATES / "storefront" / "_base.html"
PHOTO_PARTIALS = ("storefront/cards/_photo.html", "storefront/cards/_promo_photo.html")


def _css_rule(css: str, selector: str) -> str:
    """Тело CSS-правила с ТОЧНО этим селектором (пустая строка — правила нет)."""
    m = re.search(re.escape(selector) + r"\s*\{([^}]*)\}", css)
    return m.group(1) if m else ""


def _stub(**extra):
    base = dict(
        pk=1,
        primary_image=None,
        images=[],
        in_stock=True,
        discount_style="",
        title_text="Butter",
    )
    base.update(extra)
    return SimpleNamespace(**base)


def test_photo_partials_mark_side_boxes():
    """Параметр `side` превращает маркер в `data-sf-media-box="side"`; без него — прежний
    голый атрибут байт-в-байт (все вертикальные карточки и паритет-замки целы)."""
    for tpl in PHOTO_PARTIALS:
        plain = render_to_string(tpl, {"p": _stub(), "ratio": "aspect-square"})
        side = render_to_string(tpl, {"p": _stub(), "ratio": "h-full", "side": True})
        assert 'data-sf-media-box="side"' in side, tpl
        assert "data-sf-media-box" in plain and 'data-sf-media-box="' not in plain, tpl


def test_every_card_height_photo_is_marked_side():
    """Класс дефекта: фото, высоту которого задаёт КАРТОЧКА (`h-full`), а не aspect-
    класс. Каждый такой include фото-партиала обязан передать `side=True` — иначе
    правила формы кадра снова раздуют его за пределы колонки (как у «Ценника»)."""
    offenders = []
    include_re = re.compile(r'\{%\s*include\s+"storefront/cards/_(?:promo_)?photo\.html"([^%]*)%\}')
    for path in (TEMPLATES / "storefront").rglob("*.html"):
        text = path.read_text(encoding="utf-8")
        for m in include_re.finditer(text):
            args = m.group(1)
            ratio = re.search(r'ratio="([^"]*)"', args)
            if ratio and "h-full" in ratio.group(1).split() and "side=True" not in args:
                offenders.append(f"{path}: {m.group(0)}")
    assert not offenders, offenders


def test_regal_forms_use_side_photos():
    """Обе формы «Ценник» (товар и акция) несут боковое фото."""
    for name in ("_product_regal.html", "_promo_regal.html"):
        text = (TEMPLATES / "storefront" / "cards" / name).read_text(encoding="utf-8")
        assert "side=True" in text, name


def test_shape_rules_keep_side_photo_inside_its_column():
    """CSS: под ЛЮБОЙ формой фото боковой бокс сбрасывает min-height (иначе aspect-ratio
    переносит её в ширину) и не шире своей колонки; wide — миниатюра 16:9 по ширине
    колонки, round — круг по центру (а не «пилюля» с верхним отступом)."""
    css = BASE.read_text(encoding="utf-8")
    any_shape = _css_rule(css, '[data-sf-media] [data-sf-media-box="side"]')
    assert re.search(r"min-height:\s*0", any_shape), any_shape
    assert re.search(r"max-width:\s*100%", any_shape), any_shape
    wide = _css_rule(css, '[data-sf-media="wide"] [data-sf-media-box="side"]')
    assert "width:" in wide, wide
    round_ = _css_rule(css, '[data-sf-media="round"] [data-sf-media-box="side"]')
    assert re.search(r"margin:\s*0 auto", round_), round_
    # Боковые правила идут ПОСЛЕ общих (равная специфичность → побеждает поздний).
    assert css.index('[data-sf-media="round"] [data-sf-media-box] {') < css.index(
        '[data-sf-media="round"] [data-sf-media-box="side"]'
    )
