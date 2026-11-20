"""FB-33 M2b-2a: виды блока FAQ — ЕДИНСТВЕННЫЙ список видов FAQ на всех страницах.

Решение владельца (2026-11-20): одно имя вида на всех страницах — «Akkordeon» (пустой ключ:
прежний вид, старые конфиги байт-в-байт), «Liste», «Zwei Spalten», «Karten», «Nummeriert».
На главной и прочих страницах — пять видов, на детальных (товар, услуга, номер, событие и тур)
— три (`detail`). На детальной общий FAQ не выводит FAQPage: вопросы там не об объекте.

Читают: `siteconfig.SECTION_STYLES["faq"]` (валидность сохранённого вида), панель блока
(`site_schema._style_options`), рендер (`siteui.render_block`), окно «Wie anordnen» M3-3
(`views(host)` → key, label, hint).

Модуль без зависимостей от siteconfig (цикл импортов: siteconfig читает отсюда при загрузке) —
замок `test_fb33_m2b2a_faq_views`.
"""

from __future__ import annotations

from typing import NamedTuple

from django.utils.translation import gettext_lazy as _


class FaqView(NamedTuple):
    key: str  # "" — Akkordeon (вид по умолчанию, ключ не хранится)
    label: str
    hint: str
    detail: bool  # есть среди видов детальной страницы


VIEWS: tuple[FaqView, ...] = (
    FaqView("", _("Akkordeon"), _("Antwort beim Antippen"), True),
    FaqView("list", _("Liste"), _("alles offen"), True),
    FaqView("twocol", _("Zwei Spalten"), _("Fragen nebeneinander"), True),
    FaqView("cards", _("Karten"), _("Fragen als Kacheln"), False),
    FaqView("numbered", _("Nummeriert"), _("Fragen mit Nummern"), False),
)
#: сохраняемые ключи вида (без пустого) — `SECTION_STYLES["faq"]`
STYLE_KEYS: tuple[str, ...] = tuple(v.key for v in VIEWS if v.key)
#: общие хосты детальных страниц (свои хосты объекта R8 сводятся к ним `shared_host`; тур —
#: к `event_detail`). Акция, комбо и запись блога — не детальные: пять видов и FAQPage.
DETAIL_HOSTS = frozenset({"product_detail", "service_detail", "stay_detail", "event_detail"})


def is_detail_host(host) -> bool:
    """Хост блоков — детальная страница (общий `*_detail` или свой хост объекта R8)."""
    if not isinstance(host, str) or not host:
        return False
    from apps.core.detail_parts import shared_host

    return shared_host(host) in DETAIL_HOSTS


def views(host) -> tuple[FaqView, ...]:
    """Виды FAQ, которые предлагает страница `host` (детальная — три, прочие — пять)."""
    if is_detail_host(host):
        return tuple(v for v in VIEWS if v.detail)
    return VIEWS


def choices(host) -> list[tuple[str, str]]:
    """Пункты селекта «Darstellung» блока FAQ на странице `host`."""
    return [(v.key, str(v.label)) for v in views(host)]


def label(key: str) -> str:
    """Имя вида по ключу (чужой ключ — как есть)."""
    return next((str(v.label) for v in VIEWS if v.key == (key or "")), key)


def emits_ld(host) -> bool:
    """Выводит ли блок FAQ на этой странице FAQPage (на детальной — нет)."""
    return not is_detail_host(host)
