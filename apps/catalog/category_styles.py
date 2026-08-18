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
]
VALID_PAGE_STYLES = frozenset(code for code, _l, _h in CATEGORY_PAGE_STYLES)


def page_style(category) -> str:
    """Эффективный шаблон страницы категории (мусор в БД → Standard)."""
    code = getattr(category, "page_style", "") or ""
    return code if code in VALID_PAGE_STYLES else ""
