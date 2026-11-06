"""AIS A-4c: «покажи товары списком / 4 в ряд / шаблон Kompakt» — пункт пакета для настройки
страницы (шаблон, сетка, форма карточки, сортировка).

План — docs/ais-a4-ki-actions-plan-2026-11-06.md §12. Единственный исполнитель — `page_settings`
(STU-19: тот же писатель и тот же список вариантов, что экран «Seitenvorlage»; второго списка
шаблонов здесь нет). Без ИИ: слово типа страницы на пяти языках + подпись варианта из схемы
(на языке кабинета и по-немецки) или «N pro Reihe». Применяет и откатывает `assistant_actions`.
"""

from __future__ import annotations

import logging
import re

from django.utils import translation
from django.utils.translation import gettext as _

logger = logging.getLogger(__name__)

TEXT_MAX = 400
ACTION = "page.setting"

#: тип страницы → основы слов, которыми его называет владелец (5 языков кабинета)
TYPE_WORDS: dict[str, tuple[str, ...]] = {
    "catalog": (
        "sortiment",
        "katalog",
        "produkte",
        "artikel",
        "catalog",
        "catalogue",
        "products",
        "каталог",
        "товар",
        "ассортимент",
        "асортимент",
        "ürün",
        "urun",
    ),
    "promos": (
        "aktionen",
        "rabatte",
        "promotions",
        "deals",
        "акци",
        "акці",
        "скидк",
        "знижк",
        "kampanya",
        "indirim",
    ),
    "services": ("leistungen", "dienstleistungen", "services", "услуг", "послуг", "hizmet"),
    "stays": ("zimmer", "unterkunft", "rooms", "номер", "кімнат", "oda"),
    "events": ("veranstaltungen", "events", "событи", "мероприят", "поді", "etkinlik"),
    "home": ("startseite", "homepage", "главн", "головн", "anasayfa", "ana sayfa"),
}
#: что владелец хочет поменять ВИД (не создать и не спросить)
_DISPLAY = re.compile(
    r"(?<!\w)(?:zeig\w*|anzeig\w*|darstell\w*|ansicht|vorlage|layout|raster|als|show|display\w*|"
    r"template|grid|kartenform|показ\w*|выв\w*|шаблон\w*|вид|сетк\w*|відобра\w*|вигляд|сітк\w*|"
    r"göster\w*|görünüm|şablon|ızgara)(?!\w)",
    re.IGNORECASE,
)
#: «4 pro Reihe / 4 в ряд / 4 per row» — предлог обязателен: «in 2 Reihen» (две СТРОКИ),
#: «Reihenfolge», «Reihenhäuser» колонками не считаются
_PER_ROW = re.compile(
    r"(?<!\d)([1-6])\s*(?:pro|je|per|в|у|на)\s+"
    r"(?:reihe|zeile|row|ряд|рядок|рядку|satıra|satırda)(?!\w)",
    re.IGNORECASE,
)
_SUPPORTED_KINDS = ("choice", "layout")
PER_ROW_SCORE = 100


def _types_in(text: str) -> list[str]:
    low = text.casefold()
    out = []
    for code, stems in TYPE_WORDS.items():
        for stem in stems:
            if re.search(r"(?<!\w)" + re.escape(stem), low):
                out.append(code)
                break
    return out


def _labels(label) -> set[str]:
    """Подпись варианта на языке кабинета и по-немецки (владелец пишет на любом)."""
    out = {str(label).strip().casefold()}
    with translation.override("de"):
        out.add(str(label).strip().casefold())
    return {s for s in out if len(s) >= 4}


def _schema(tenant, type_code: str):
    from apps.core import page_settings

    for ts in page_settings.schema(tenant, types=(type_code,)):
        if ts.code == type_code:
            return ts
    return None


def _candidates(text: str, ts) -> list[tuple[int, object, object]]:
    """[(сила совпадения, SettingState, Choice)] — варианты, названные во фразе."""
    low = text.casefold()
    out = []
    per_row = _PER_ROW.search(text)
    for st in ts.settings:
        if st.kind not in _SUPPORTED_KINDS:
            continue
        for choice in st.choices:
            if not choice.available or not choice.value:
                continue
            if per_row and st.kind == "layout" and choice.value == f"cols{per_row.group(1)}":
                out.append((PER_ROW_SCORE, st, choice))
                continue
            for label in _labels(choice.label):
                if re.search(r"(?<!\w)" + re.escape(label) + r"(?!\w)", low):
                    out.append((len(label), st, choice))
                    break
    return out


def _find(tenant, user, text: str):
    """(ts, candidates) или None — общий разбор intent и build."""
    from apps.core import assistant_changes
    from apps.core.permissions import has_perm

    text = (text or "").strip()[:TEXT_MAX]
    if len(text) < 4 or assistant_changes._CREATE.search(text):
        return None
    if assistant_changes._looks_like_question(text):
        return None
    if not (_DISPLAY.search(text) or _PER_ROW.search(text)):
        return None
    # без права видеть сайт детектор молчит (право САМОГО изменения — в allowed())
    if user is None or not has_perm(user, "website.view"):
        return None
    types = _types_in(text)
    if len(types) != 1:
        return None
    ts = _schema(tenant, types[0])
    if ts is None:
        return None
    found = _candidates(text, ts)
    return (ts, found) if found else None


def intent(tenant, user, text: str) -> bool:
    try:
        return _find(tenant, user, text) is not None
    except Exception:  # noqa: BLE001 — fail closed: обычный вопрос
        logger.warning("assistant pages: intent failed", exc_info=True)
        return False


def current(tenant, code: str) -> str:
    from apps.core import page_settings, studio_pages

    value, _set = page_settings.current_value(tenant.site_config or {}, studio_pages.SETTINGS[code])
    return str(value)


def options(tenant, code: str) -> list[tuple[str, str]]:
    """Доступные варианты настройки для селекта предпросмотра (как на экране кабинета)."""
    from apps.core import page_settings, studio_pages

    setting = studio_pages.SETTINGS.get(code)
    if setting is None:
        return []
    try:
        gate = page_settings.composition_gate(tenant.site_config or {})
        # только то, что примет page_settings.validate: «Standard» — если он есть в схеме
        return [
            (choice.value, str(choice.label or _("Standard")))
            for choice in page_settings.choices(setting, gate)
            if choice.available
        ]
    except page_settings.PageSettingError:  # настройку убрали из реестра — нечего предлагать
        return []


def value_label(tenant, code: str, value: str) -> str:
    for v, label in options(tenant, code):
        if v == value:
            return label
    return str(_("Standard")) if not value else value


def build(tenant, user, text: str) -> list[dict]:
    """Один пункт пакета: настройка страницы → значение (или [] — не наше)."""
    got = _find(tenant, user, text)
    if got is None:
        return []
    ts, found = got
    best = max(score for score, _st, _ch in found)
    top = {(st.code, ch.value): (st, ch) for score, st, ch in found if score == best}
    st, choice = next(iter(top.values()))
    item = {
        "action": ACTION,
        "target": {"kind": "page", "pk": st.code},
        "values": {
            "name": f"{ts.label} · {st.label}",
            "value": choice.value,
            "type": ts.code,
        },
        "before": str(st.value or ""),
        # ключа не было — откат его уберёт (presence-minimal), а не запишет явное значение
        "before_set": bool(st.is_set),
        "note": "",
        "blocked": "",
    }
    # «als Liste, 4 pro Reihe» — и подпись, и «N pro Reihe»: не выбираем молча одно из двух
    both = best == PER_ROW_SCORE and any(score < PER_ROW_SCORE for score, _st, _ch in found)
    if len(top) > 1 or both:
        item["blocked"] = _("Das passt zu mehreren Einstellungen — bitte genauer sagen.")
    elif choice.value == item["before"]:
        item["blocked"] = _("Ist schon so eingestellt.")
    return [item]
