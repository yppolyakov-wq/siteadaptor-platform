"""FB-32 S5a: один реестр видов блока «Kategorien» для главной и каталога (решение владельца
2026-11-17, `docs/fb32-unified-blocks-plan-2026-11-17.md`).

Обе панели «Seitenaufbau» показывают ОДИН список видов со схемами. Вид, который на этой
странице пока не рисуется, виден недоступным с причиной: «Reiter» и «Seitenspalte» управляют
списком товаров и бывают только на страницах каталога (решение владельца); «Regale», «Index»
и «Wegweiser» на главной — следующий шаг (S5b); формы плиток главной в каталоге — тоже позже.
Хранение прежнее: главная — `style` строки секции, каталог — вид его строки категорий.
"""

from __future__ import annotations

from dataclasses import dataclass

from django.utils.translation import gettext_lazy as _

HOME = "home"
CATALOG = "catalog"


@dataclass(frozen=True)
class View:
    key: str
    label: object
    home: str | None  # значение на главной (`style` секции) или None — здесь нет
    catalog: str | None  # значение в каталоге (вид строки категорий) или None
    thumb_style: str = ""  # схема главной (`_style_thumb.html`)
    thumb_page: str = ""  # схема каталога (`_pagelayout_thumb.html`)
    #: вид бывает ТОЛЬКО в каталоге (управляет там списком товаров), не «пока»
    home_only_catalog: bool = False


CATEGORY_VIEWS: tuple[View, ...] = (
    View("standard", _("Standard"), "", "auto", thumb_style=""),
    View("square", _("Quadratisch"), "square", None, thumb_style="square"),
    View("tall", _("Hochformat"), "tall", None, thumb_style="tall"),
    View("wide", _("Breitbild"), "wide", None, thumb_style="wide"),
    View("compact", _("Kompakt"), "compact", None, thumb_style="compact"),
    # FB-32 S5b: и на главной — тот же построитель (`apps/catalog/category_views.py`)
    View("regale", _("Regale"), "regale", "regale", thumb_style="regale", thumb_page="regale"),
    View("index", _("Index"), "index", "index", thumb_style="index", thumb_page="kompakt"),
    View(
        "wegweiser",
        _("Wegweiser"),
        "wegweiser",
        "wegweiser",
        thumb_style="wegweiser",
        thumb_page="wegweiser",
    ),
    View("tabs", _("Reiter"), None, "tabs", thumb_page="tabs", home_only_catalog=True),
    View("side", _("Seitenspalte"), None, "side", thumb_page="navigator", home_only_catalog=True),
)


def reason(view: View, where: str) -> str:
    """Почему вид недоступен на странице `where` (пусто — доступен)."""
    if where == HOME and view.home is None:
        if view.home_only_catalog:
            return str(_("Nur auf Katalogseiten – steuert dort die Produktliste."))
        return str(_("Vorerst nur auf Katalogseiten."))
    if where == CATALOG and view.catalog is None:
        return str(_("Vorerst nur auf der Startseite."))
    return ""


def unavailable(where: str) -> list[dict]:
    """Виды реестра, недоступные на `where`: [{key, label, reason, thumb_style, thumb_page}]."""
    return [
        {
            "key": v.key,
            "label": str(v.label),
            "reason": reason(v, where),
            "thumb_style": v.thumb_style,
            "thumb_page": v.thumb_page,
        }
        for v in CATEGORY_VIEWS
        if reason(v, where)
    ]
