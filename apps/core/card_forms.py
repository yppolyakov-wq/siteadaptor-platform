"""DL-19: реестр ФОРМ карточки товара и акции (план
`docs/dl19-card-forms-plan-2026-09-03.md`).

Форма карточки задаётся в двух местах и по одному правилу приоритета:

* «на весь сайт» — `site_config["site_defaults"]["card_style"]` (товар) и
  `["promo_card"]` (акция), Studio → область «Design»;
* «только для этой позиции» — поле `card_style` у самого товара/акции.

Своё значение объекта ПОБЕЖДАЕТ дефолт сайта (запрос владельца 2026-09-03).
Неизвестное значение в любом слое → `""` (прежняя форма), а не 500 — то же
правило, что у `option_styles.variant_style`.

До этой волны список допустимых значений был захардкожен в четырёх местах
(`siteconfig.normalize_site_defaults`, `demo_kits`, `sitetemplates.apply_preview_bundle`,
`<option>` шаблона Studio) — реестр становится единственным источником.
"""

from __future__ import annotations

from django.utils.translation import gettext_lazy as _

PRODUCT = "product"
PROMO = "promo"

# (ключ, подпись, подсказка «когда уместно», виды сущностей)
CARD_FORMS: list[tuple[str, object, object, tuple[str, ...]]] = [
    ("", _("Standard"), _("Photo, name, price — the usual card."), (PRODUCT, PROMO)),
    (
        "overlay",
        _("Text on photo"),
        _("Name and price over the photo — for strong images."),
        (PRODUCT,),
    ),
    ("compact", _("Compact row"), _("Row with a small photo — for long menus."), (PRODUCT,)),
    ("etikett", _("Price tag"), _("Price on a plate in the corner of the photo."), (PRODUCT,)),
    ("preis", _("Price first"), _("Price block above the photo — discounter style."), (PROMO,)),
    # DL-19 (макеты канваса «Kartenformen» 2026-09-02)
    (
        "regal",
        _("Shelf label"),
        _("Big price on a plate, small photo — reads like a shelf tag."),
        (PRODUCT, PROMO),
    ),
    (
        "lookbook",
        _("Lookbook"),
        _("Tall photo 3:4 and a quiet caption — fashion and interior."),
        (PRODUCT, PROMO),
    ),
    (
        "deal",
        _("Deal tile"),
        _("Wide row: price, saving, condition and button at a glance."),
        (PRODUCT, PROMO),
    ),
    ("coupon", _("Coupon"), _("Dashed cut-out with the value — like a voucher."), (PROMO,)),
    ("ring", _("Countdown ring"), _("Remaining time as a ring on the photo."), (PROMO,)),
]


def forms_for(kind: str = PRODUCT) -> list[tuple[str, object, object]]:
    """Формы, применимые к виду сущности — для форм кабинета и плиток Studio."""
    return [(key, label, hint) for key, label, hint, kinds in CARD_FORMS if kind in kinds]


def keys_for(kind: str = PRODUCT) -> frozenset[str]:
    """Допустимые НЕ-пустые ключи вида (пустой = прежняя форма, ключа в конфиге нет)."""
    return frozenset(key for key, _label, _hint, kinds in CARD_FORMS if key and kind in kinds)


def label_for(key: str, kind: str = PRODUCT) -> object:
    for k, label, _hint, kinds in CARD_FORMS:
        if k == key and kind in kinds:
            return label
    return ""


def card_form(entity, site_default: str = "", kind: str = PRODUCT) -> str:
    """Действующая форма карточки: своя у объекта → дефолт сайта → прежняя ("").

    `entity` может быть чем угодно (в секциях главной карточки рендерятся
    стабами-SimpleNamespace) — читаем через getattr с фолбэком.
    """
    allowed = keys_for(kind)
    own = (getattr(entity, "card_style", "") or "").strip()
    if own in allowed:
        return own
    site_default = (site_default or "").strip()
    return site_default if site_default in allowed else ""
