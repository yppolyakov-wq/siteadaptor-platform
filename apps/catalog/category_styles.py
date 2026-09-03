"""KAT-1: реестр шаблонов СТРАНИЦЫ категории /sortiment/<slug>/.

Шаблон выбирает владелец per-категория (Category.page_style, select в форме);
"" = Standard — прежний вид фильтра байт-в-байт (замки характеризации целы).
Каждый шаблон собирается из ЖИВЫХ данных категории и деградирует сам: нет фото —
шапка текстовая, нет комбо — полосы нет (fail-soft, страница не пустеет).
Прецедент механики — catalog/option_styles.py (Product.variant_style).
"""

from django.utils.translation import gettext_lazy as _

# (код, метка, подсказка). Порядок = порядок в select'е формы.
CATEGORY_PAGE_STYLES = [
    ("", _("Standard (Raster)"), _("Wie bisher: Filter, Unterkategorien, Produktraster.")),
    (
        "kopfbild",
        _("Mit Kopfbild"),
        _("Hero mit Foto und Beschreibung, Unterkategorien als Foto-Kacheln."),
    ),
    (
        "sets",
        _("Sets & Menüs zuerst"),
        _("Menü-Sets dieser Kategorie als Karten über dem Raster."),
    ),
    (
        "preisliste",
        _("Preisliste"),
        _("Produkte dieser Kategorie als Preisliste statt Raster."),
    ),
    # DL-16.5 (K2/K3): направления с подкатегориями — «полки» лентами или табы.
    (
        "regale",
        _("Regale (Unterkategorien als Leisten)"),
        _("Jede Unterkategorie als horizontale Leiste mit Pfeilen — alles auf einen Blick."),
    ),
    (
        "tabs",
        _("Tabs (Unterkategorien als Reiter)"),
        _("Unterkategorien als Reiter über dem Raster — Wechsel ohne Neuladen."),
    ),
    # DL-20 (канвас «Kategorie-Vorlagen» 2026-09-03): пять композиций сверх
    # существующих. Каждая отличается НАБОРОМ или ПОРЯДКОМ блоков, а не только
    # классами (урок DL-9: иначе получается пятый переключатель с тем же видом).
    (
        "schaufenster",
        _("Showcase"),
        _("The first product as a wide card with text and button, the rest as a grid."),
    ),
    (
        "navigator",
        _("Navigator"),
        _("Subcategories and filters in a side column, products on the right."),
    ),
    (
        "magazin",
        _("Magazine"),
        _("Cover image, then two large cards per row with a description."),
    ),
    (
        "mosaik",
        _("Mosaic"),
        _("Tiles of different sizes — needs strong photos."),
    ),
    (
        "kompakt",
        _("Compact"),
        _("Subcategory index in columns and a dense grid — for large ranges."),
    ),
]
VALID_PAGE_STYLES = frozenset(code for code, _l, _h in CATEGORY_PAGE_STYLES)


def page_style(category, site_default: str = "") -> str:
    """Эффективный шаблон страницы категории.

    DL-20 (запрос владельца «наследование через общие настройки»): два слоя и то же
    правило приоритета, что у форм карточки (`core.card_forms.card_form`) —

    * своё значение категории (`Category.page_style`) ПОБЕЖДАЕТ;
    * иначе действует дефолт сайта (`site_defaults["category_page_style"]`);
    * мусор в любом слое → "" (Standard), а не 500.

    До DL-20 второго слоя не было вовсе: владелец обязан был выставлять шаблон
    в каждой категории вручную.
    """
    code = (getattr(category, "page_style", "") or "").strip()
    if code in VALID_PAGE_STYLES and code:
        return code
    site_default = (site_default or "").strip()
    return site_default if site_default in VALID_PAGE_STYLES else ""
