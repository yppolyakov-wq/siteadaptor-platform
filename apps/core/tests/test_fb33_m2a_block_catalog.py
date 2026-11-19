"""FB-33 M2a: каталог блоков — семьи (членство) и библиотека — один источник.

Раньше библиотека была двумя литералами: карточки Студии (`block_types` во вьюхе) и
группы меню «+ Block» (`site_schema._ADD_GROUPS`). Каталог их заменил; состав и порядок
пунктов — как были (характеризация ниже).
"""

import inspect
import pathlib

import pytest
from django.utils import translation

from apps.core import block_catalog, site_schema
from apps.tenants import siteconfig

SECTION_KEYS = [key for key, _label, _on in siteconfig.SECTIONS]


def test_every_block_key_is_in_exactly_one_family():
    keys = [k for fam in block_catalog.FAMILIES for k, _where in fam.members]
    assert len(keys) == len(set(keys)), "ключ в двух семьях"
    known = set(SECTION_KEYS) | set(siteconfig.REPEATABLE_BLOCKS) | set(siteconfig.PAGE_REF_BLOCKS)
    assert set(keys) == known  # обе стороны: ничего не потеряно и ничего лишнего


def test_member_kind_matches_the_registry_it_lives_in():
    where = {
        block_catalog.SECTION: set(SECTION_KEYS),
        block_catalog.CBLOCK: set(siteconfig.REPEATABLE_BLOCKS),
        block_catalog.REF: set(siteconfig.PAGE_REF_BLOCKS),
    }
    for fam in block_catalog.FAMILIES:
        for key, kind in fam.members:
            assert key in where[kind], (fam.key, key, kind)


def test_library_covers_every_insertable_block_once():
    keys = [e.key for e in block_catalog.LIBRARY]
    assert len(keys) == len(set(keys))
    assert set(keys) == set(siteconfig.REPEATABLE_BLOCKS) | set(siteconfig.PAGE_REF_BLOCKS)
    groups = {g for g, _label in block_catalog.ADD_GROUPS}
    assert {e.group for e in block_catalog.LIBRARY} <= groups
    # ссылочные блоки — только на страницах
    for e in block_catalog.LIBRARY:
        assert e.page_only == (e.key in siteconfig.PAGE_REF_BLOCKS), e.key


def test_view_switch_never_crosses_section_and_block():
    kinds = {k: w for fam in block_catalog.FAMILIES for k, w in fam.members}
    for pair in block_catalog.VIEW_SWITCHES:
        a, b = sorted(pair)
        assert block_catalog.family_of(a) is block_catalog.family_of(b)
        assert block_catalog.SECTION not in {kinds[a], kinds[b]}
    assert not block_catalog.can_switch("about", "text")
    assert block_catalog.can_switch("text", "image_text")


def test_catalog_does_not_import_siteconfig_at_module_level():
    head = inspect.getsource(block_catalog).split("def family_of")[0]
    assert "siteconfig" not in head.split('"""', 2)[-1]


def test_no_block_list_literals_left():
    views = pathlib.Path("apps/core/views.py").read_text(encoding="utf-8")
    assert '"value": "faq_ref"' not in views
    assert "_ADD_GROUPS" not in inspect.getsource(site_schema)


STUDIO_BEFORE = [
    ("text", "📝", "Heading + paragraph", False),
    ("image", "🖼️", "Photo with caption", False),
    ("image_text", "🏞️", "Photo beside text", False),
    ("button", "🔘", "Link button", False),
    ("spacer", "↕️", "Vertical spacing", False),
    ("promo", "🏷️", "Live promotion", False),
    ("list", "🗂️", "Aktionen oder Produkte — Auswahl und Ansicht wählen Sie selbst", False),
    ("stats", "🔢", "2–4 key figures with captions", False),
    ("banner", "🏞️", "Bild mit Text und Link — auf jeder Seite, mit Zeitraum", False),
    ("newsletter", "📧", "Signup form with double opt-in", False),
    ("faq_ref", "❓", "Der FAQ-Block der Startseite — auch auf dieser Seite", True),
    ("team_ref", "👥", "Der Team-Block der Startseite — auch auf dieser Seite", True),
    ("gallery_ref", "🖼️", "Die Galerie der Startseite — auch auf dieser Seite", True),
    ("testimonials_ref", "💬", "Kundenstimmen der Startseite — auch auf dieser Seite", True),
    ("anfrage_ref", "📝", "Angebot-Anfrage direkt auf dieser Seite (Modul Aufträge)", True),
    (
        "message_ref",
        "✉️",
        "Frage-stellen-Formular direkt auf dieser Seite (Modul Nachrichten)",
        True,
    ),
]


def test_studio_library_is_unchanged():
    translation.deactivate_all()  # msgid как есть — без перевода
    try:
        got = [
            (c["value"], c["icon"], str(c["hint"]), c.get("page_only", False))
            for c in block_catalog.studio_block_types()
        ]
        labels = {c["value"]: c["label"] for c in block_catalog.studio_block_types()}
    finally:
        translation.activate("de")
    assert got == STUDIO_BEFORE
    assert all(labels[k] is siteconfig.CBLOCK_LABELS[k] for k in labels)  # подписи — из реестра


@pytest.mark.parametrize(
    ("code", "expected"),
    (
        (
            "home",
            [
                ("inhalt", ["text", "image", "image_text", "button", "spacer", "stats", "banner"]),
                ("listen", ["promo", "list", "newsletter"]),
                ("quellen", ["textpage", "contact_card"]),
            ],
        ),
        (
            "services",
            [
                ("inhalt", ["text", "image", "image_text", "button", "spacer", "stats", "banner"]),
                ("listen", ["promo", "list", "newsletter"]),
                (
                    "quellen",
                    [
                        "textpage",
                        "contact_card",
                        "faq_ref",
                        "team_ref",
                        "gallery_ref",
                        "testimonials_ref",
                    ],
                ),
                ("formulare", ["anfrage_ref", "message_ref"]),
            ],
        ),
    ),
)
def test_add_menu_groups_are_unchanged(code, expected):
    got = [(g["key"], [k for k, _ in g["options"]]) for g in site_schema.add_groups(code)]
    assert got == expected


def test_contact_styles_are_one_tuple():
    assert siteconfig.SECTION_STYLES["contact"] is siteconfig.CONTACT_STYLES
