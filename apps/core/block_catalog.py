"""FB-33 M2a: каталог блоков — какие блоки одна СЕМЬЯ и как они выглядят в библиотеке.

План — `docs/fb33-editor-model-2026-11-19.md` §«План M2» и вердикт architect. Каталог —
реестр ЧЛЕНСТВА, а не третий список блоков:

* семья → её члены (хранимые ключи) и где каждый живёт: фикс-секция главной
  (`siteconfig.SECTIONS`), повторяемый C-блок (`REPEATABLE_BLOCKS`) или ссылочный блок
  страниц (`PAGE_REF_BLOCKS`). Подписи членов — из тех же реестров (`CBLOCK_LABELS`,
  `SECTIONS`), у семьи своя только подпись семьи;
* библиотека C-/ссылочных блоков — иконка, подсказка, группа меню «+ Block» и показ в
  Студии. Раньше это были два литерала: `block_types` во вьюхе Студии и `_ADD_GROUPS`
  в `site_schema` (замок `test_fb33_m2a_block_catalog`).

Сведение семей — только в представлении: сохранение пишет прежний ключ выбранного вида,
рендер сайтов не меняется, данные не переносятся (решение владельца по K2).
Модуль не импортирует `siteconfig` на уровне модуля (тот импортирует `apps.core`).
"""

from __future__ import annotations

from typing import NamedTuple

from django.utils.translation import gettext_lazy as _

SECTION = "section"  # фикс-секция главной
CBLOCK = "cblock"  # повторяемый блок любой страницы
REF = "ref"  # ссылочный блок страниц (контент общий с главной)


class Family(NamedTuple):
    key: str
    label: object
    members: tuple[tuple[str, str], ...]  # (хранимый ключ, где живёт)


FAMILIES: tuple[Family, ...] = (
    Family("banner", _("Banner"), (("hero", SECTION), ("banner", CBLOCK))),
    Family("trust_bar", _("Trust bar"), (("usp_bar", SECTION),)),
    Family("finder", _("Finder"), (("finder", SECTION),)),
    Family("stay_search", _("Booking search (stays)"), (("stay_search", SECTION),)),
    Family(
        "list",
        _("Liste"),
        (
            ("list", CBLOCK),
            ("promotions", SECTION),
            ("products", SECTION),
            ("categories", SECTION),
            ("services", SECTION),
            ("stay_rooms", SECTION),
            ("events", SECTION),
            ("tours", SECTION),
            ("blog", SECTION),
        ),
    ),
    Family("promo", _("Promotion"), (("promo", CBLOCK),)),
    Family("archetypes", _("Our offerings"), (("archetypes", SECTION),)),
    Family(
        "text",
        _("Text"),
        (("text", CBLOCK), ("image_text", CBLOCK), ("textpage", CBLOCK), ("about", SECTION)),
    ),
    Family("image", _("Image"), (("image", CBLOCK),)),
    Family("cta", _("Call to action"), (("cta", SECTION), ("button", CBLOCK))),
    Family("process", _("How it works"), (("process", SECTION),)),
    Family("team", _("Team"), (("team", SECTION), ("team_ref", REF))),
    Family(
        "reviews",
        _("Customer reviews"),
        (("reviews", SECTION), ("testimonials", SECTION), ("testimonials_ref", REF)),
    ),
    Family("trust", _("Trust & credentials"), (("trust", SECTION),)),
    Family("faq", _("FAQ"), (("faq", SECTION), ("faq_ref", REF))),
    Family("gallery", _("Photo gallery"), (("gallery", SECTION), ("gallery_ref", REF))),
    Family("before_after", _("Before & after"), (("before_after", SECTION),)),
    Family("stats", _("Numbers"), (("stats", CBLOCK),)),
    Family("newsletter", _("Newsletter"), (("newsletter", CBLOCK),)),
    Family("spacer", _("Spacer"), (("spacer", CBLOCK),)),
    Family(
        "contact",
        _("Kontakt & Öffnungszeiten"),
        (("contact", SECTION), ("contact_card", CBLOCK)),
    ),
    Family("anfrage", _("Anfrage-Formular"), (("anfrage", SECTION), ("anfrage_ref", REF))),
    Family("message", _("Kontaktformular"), (("message_ref", REF),)),
)

#: Смена вида внутри семьи без потерь данных (поля у членов общие). Фикс-секция ↔
#: C-блок сюда не входит: это копирование, а не смена вида (замок).
VIEW_SWITCHES: frozenset[frozenset[str]] = frozenset(
    {
        frozenset({"text", "image_text"}),
        frozenset({"text", "textpage"}),
        frozenset({"image_text", "textpage"}),
    }
)


class LibraryEntry(NamedTuple):
    key: str
    icon: str
    hint: object
    group: str  # группа меню «+ Block» (`ADD_GROUPS`)
    studio: bool = True  # есть в библиотеке Студии
    page_only: bool = False  # только на страницах (ссылочные блоки — не на главной)


#: Группы меню «+ Block» (FB-27 R6, решение владельца): ключ → подпись.
ADD_GROUPS: tuple[tuple[str, object], ...] = (
    ("inhalt", _("Inhalt")),
    ("listen", _("Listen & Aktionen")),
    ("quellen", _("Von anderen Stellen")),
    ("formulare", _("Formulare")),
)

#: Библиотека C- и ссылочных блоков — в порядке карточек Студии.
LIBRARY: tuple[LibraryEntry, ...] = (
    LibraryEntry("text", "📝", _("Heading + paragraph"), "inhalt"),
    LibraryEntry("image", "🖼️", _("Photo with caption"), "inhalt"),
    LibraryEntry("image_text", "🏞️", _("Photo beside text"), "inhalt"),
    LibraryEntry("button", "🔘", _("Link button"), "inhalt"),
    LibraryEntry("spacer", "↕️", _("Vertical spacing"), "inhalt"),
    LibraryEntry("promo", "🏷️", _("Live promotion"), "listen"),  # UE1
    # LB-1 (вырос из PT-6 «Aktionen eines Typs»)
    LibraryEntry(
        "list",
        "🗂️",
        _("Aktionen oder Produkte — Auswahl und Ansicht wählen Sie selbst"),
        "listen",
    ),
    LibraryEntry("stats", "🔢", _("2–4 key figures with captions"), "inhalt"),  # GK-4
    LibraryEntry(
        "banner", "🏞️", _("Bild mit Text und Link — auf jeder Seite, mit Zeitraum"), "inhalt"
    ),  # FB-22b
    LibraryEntry("newsletter", "📧", _("Signup form with double opt-in"), "listen"),  # GK-8
    # UC2-3(b): ссылочные секции-справочники — ТОЛЬКО на страницах (контент общий с главной)
    LibraryEntry(
        "faq_ref",
        "❓",
        _("Der FAQ-Block der Startseite — auch auf dieser Seite"),
        "quellen",
        page_only=True,
    ),
    LibraryEntry(
        "team_ref",
        "👥",
        _("Der Team-Block der Startseite — auch auf dieser Seite"),
        "quellen",
        page_only=True,
    ),
    LibraryEntry(
        "gallery_ref",
        "🖼️",
        _("Die Galerie der Startseite — auch auf dieser Seite"),
        "quellen",
        page_only=True,
    ),
    LibraryEntry(
        "testimonials_ref",
        "💬",
        _("Kundenstimmen der Startseite — auch auf dieser Seite"),
        "quellen",
        page_only=True,
    ),
    # AF-2b: встраиваемые формы — на страницах; рендер гейтится модулем
    LibraryEntry(
        "anfrage_ref",
        "📝",
        _("Angebot-Anfrage direkt auf dieser Seite (Modul Aufträge)"),
        "formulare",
        page_only=True,
    ),
    LibraryEntry(
        "message_ref",
        "✉️",
        _("Frage-stellen-Formular direkt auf dieser Seite (Modul Nachrichten)"),
        "formulare",
        page_only=True,
    ),
    # FB-27 R6: только в «+ Block» Seitenaufbau (Студия правит лишь содержимое)
    LibraryEntry("textpage", "📄", "", "quellen", studio=False),
    LibraryEntry("contact_card", "📍", "", "quellen", studio=False),
)

_BY_KEY = {entry.key: entry for entry in LIBRARY}
_FAMILY_OF = {key: fam for fam in FAMILIES for key, _where in fam.members}


def family_of(key: str) -> Family | None:
    """Семья хранимого ключа блока (None — ключ не из каталога)."""
    return _FAMILY_OF.get(key)


def library_entry(key: str) -> LibraryEntry | None:
    return _BY_KEY.get(key)


def can_switch(old: str, new: str) -> bool:
    """Можно ли сменить вид блока `old` на `new` без потери данных."""
    return old == new or frozenset({old, new}) in VIEW_SWITCHES


def studio_block_types() -> list[dict]:
    """Карточки библиотеки блоков Студии (вставка даёт демо-данные `CBLOCK_DEMO_DATA`)."""
    from apps.tenants import siteconfig

    out = []
    for entry in LIBRARY:
        if not entry.studio:
            continue
        card = {
            "value": entry.key,
            "label": siteconfig.CBLOCK_LABELS[entry.key],
            "icon": entry.icon,
            "hint": entry.hint,
        }
        if entry.page_only:
            card["page_only"] = True
        out.append(card)
    return out


def add_group_keys() -> dict[str, tuple[str, ...]]:
    """Группа меню «+ Block» → её ключи в порядке библиотеки."""
    return {
        group: tuple(entry.key for entry in LIBRARY if entry.group == group)
        for group, _label in ADD_GROUPS
    }
