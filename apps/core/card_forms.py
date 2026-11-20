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
    ("compact", _("Compact with photo"), _("Row with a small photo — for long menus."), (PRODUCT,)),
    ("etikett", _("Price tag"), _("Price on a plate in the corner of the photo."), (PRODUCT,)),
    ("preis", _("Price first"), _("Price block above the photo — discounter style."), (PROMO,)),
    # DL-19 (макеты канваса «Kartenformen» 2026-09-02)
    (
        "regal",
        _("Shelf"),
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
        _("Deal row"),
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
    # STU-12j (F9): слой КАТЕГОРИИ между товаром и сайтом — «эта полка выглядит иначе».
    # Мусор в любом слое проваливается в следующий, а не роняет страницу; у стабов
    # секций главной категории нет вовсе (SimpleNamespace) — getattr с фолбэком.
    cat = getattr(entity, "category", None)
    cat_style = (getattr(cat, "card_style", "") or "").strip() if cat is not None else ""
    if cat_style in allowed and cat_style:
        return cat_style
    site_default = (site_default or "").strip()
    return site_default if site_default in allowed else ""


# ─────────────── FB-33 M1: какие формы карточки допустимы у вида списка ───────────────
#
# План — `docs/fb33-editor-model-2026-11-19.md` §«План M1». Вид списка решает, какие
# формы карточки у него есть: у сетки и ленты — плитки и строки, у прайс-листа и у
# строк акций («процент первым») своей карточки нет вовсе (строку рисует сам вид), и
# поле «Kartenform» там ничего бы не меняло. Решение владельца 2026-11-19: у ленты,
# Spotlight и баннера строки (Kompakt, Deal) остаются разрешены.
#
# Ключ вида — значение `style` блока «Liste» / секции (пусто = сетка или лента).
# Модуль не импортирует `siteconfig` (тот импортирует этот модуль); полноту
# классификации видов держит замок `test_fb33_m1_card_views`.

SHAPE_TILE = "tile"
SHAPE_ROW = "row"
_BOTH = frozenset({SHAPE_TILE, SHAPE_ROW})
_NONE: frozenset[str] = frozenset()

#: Формы-строки (широкая полоса «фото · текст · цена»); остальные — плитки.
ROW_FORMS = frozenset({"compact", "deal"})

#: Геометрии карточки по виду. Вид, которого здесь нет, — сетка/лента (обе).
VIEW_SHAPES: dict[str, frozenset[str]] = {
    "": _BOTH,
    "spotlight": _BOTH,
    "banner": _BOTH,
    "rows": _NONE,
    "preisliste": _NONE,
    "preisliste_foto": _NONE,
    "preisliste_kompakt": _NONE,
    "preisliste_2sp": _NONE,
    "preisliste_foto_2sp": _NONE,
    "preisliste_foto_3sp": _NONE,
    "preisliste_karte": _NONE,
    "preisliste_buch": _NONE,
}


def shape_of(key: str) -> str:
    """Геометрия формы: строка или плитка (пустой ключ — обычная плитка)."""
    return SHAPE_ROW if key in ROW_FORMS else SHAPE_TILE


def view_shapes(style: str | None) -> frozenset[str]:
    return VIEW_SHAPES.get(style or "", _BOTH)


def view_has_card(style: str | None) -> bool:
    """Есть ли у вида карточка (а значит, поле «Kartenform»)."""
    return bool(view_shapes(style))


def forms_for_view(style: str | None, kind: str = PRODUCT) -> list[tuple[str, object, object]]:
    """Формы сущности `kind`, допустимые у вида — подмножество `forms_for(kind)`."""
    shapes = view_shapes(style)
    return [form for form in forms_for(kind) if shape_of(form[0]) in shapes]


def normalize_for_view(style: str | None, kind: str, card: str) -> str:
    """Форма, которую вид примет: подходящая остаётся, иначе — обычная ("").

    Вид побеждает: у вида без карточки формы нет, а форма чужой геометрии
    сбрасывается на обычную (у всех видов с карточкой есть плитки).
    """
    card = (card or "").strip()
    shapes = view_shapes(style)
    if not shapes or card not in keys_for(kind) or shape_of(card) not in shapes:
        return ""
    return card


# ─────────────── FB-33 M3-4: вкладка «Karte» окна блока (макет M0-2) ───────────────
#
# План — `docs/fb33-editor-model-2026-11-19.md` §«План M3», срез M3-4. Один предикат
# «у этого списка форма карточки действует» — его зовут и запись (`siteconfig` выбрасывает
# форму, которой вид не примет), и панель (поле «Kartenform»), и окно блока (вкладка
# «Karte» есть только тогда). `kind` — вид карточки источника
# (`siteconfig.LIST_SOURCES[source]["card"]`; у категорий, отзывов, блога — None).


def card_applies(kind: str | None, style: str | None) -> bool:
    """Действует ли форма карточки у списка источника вида `kind` в виде `style`."""
    return bool(kind) and view_has_card(style)


def own_form(entity, kind: str = PRODUCT, via_category: bool = False) -> str:
    """Своя форма объекта, которая на сайте побеждает форму блока ("" — своей нет).

    Читает только поля (сырой `card_style`), без запросов: слой категории — лишь при
    `via_category` (товары; выборка блока уже тянет категорию `select_related`). У акции
    категорию не трогаем — её форма своя или типа/сайта, а `category` — лишний запрос."""
    allowed = keys_for(kind)
    own = (getattr(entity, "card_style", "") or "").strip()
    if own in allowed:
        return own
    if via_category:
        cat = getattr(entity, "category", None)
        cat_style = (getattr(cat, "card_style", "") or "").strip() if cat is not None else ""
        if cat_style in allowed:
            return cat_style
    return ""
