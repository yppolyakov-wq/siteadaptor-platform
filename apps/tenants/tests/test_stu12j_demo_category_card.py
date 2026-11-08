"""STU-12j демо: форма карточки у ОДНОЙ полки показана в ките одежды.

Функция «Kartenform nur für diese Kategorie» была в продукте, но ни одно демо её не
показывало. Замок: слаг существует в дереве кита, форма — из реестра товарных форм и
отличается от формы сайта (иначе разницу не увидеть)."""

from apps.core import card_forms
from apps.tenants.demo_kits import CLOTHING


def _slugs(categories):
    for entry in categories:
        yield entry[1]
        extra = entry[3] if len(entry) > 3 else []
        if isinstance(extra, list):
            yield from _slugs(extra)


def test_clothing_kit_has_one_shelf_with_its_own_card_form():
    styles = CLOTHING.category_card_styles
    assert styles, "демо должно показывать форму карточки у полки"
    slugs = set(_slugs(CLOTHING.categories))
    allowed = card_forms.keys_for(card_forms.PRODUCT)
    for slug, style in styles.items():
        assert slug in slugs
        assert style in allowed and style != CLOTHING.card_style


def test_category_layer_beats_site_default():
    from types import SimpleNamespace

    product = SimpleNamespace(card_style="", category=SimpleNamespace(card_style="regal"))
    assert card_forms.card_form(product, "lookbook") == "regal"
