"""FB-33 M3-4b: подписи форм карточки — по макету M0-2 и на всех экранах одни.

Подпись формы живёт ровно в одном месте — реестре `apps/core/card_forms.py` (msgid
английские, немецкий — msgstr de). Экраны (Design, товар, категория, услуга, акция,
панель списка, окно блока) берут её через `forms_for` / `label_for` / `CARD_FORMS`,
второго списка нет. Макет M0-2 переименовал четыре формы: Preisschild, Regal,
Kompakt mit Foto, Deal-Zeile — у товара и у акции одинаково.
"""

import re
from pathlib import Path

import polib
import pytest
from django.utils import translation

from apps.core import card_forms

ROOT = Path(__file__).resolve().parents[3]
LANGS = ("de", "en", "ru", "tr", "uk")

DE_PRODUCT = {
    "": "Standard",
    "overlay": "Text auf Foto",
    "compact": "Kompakt mit Foto",
    "etikett": "Preisschild",
    "regal": "Regal",
    "lookbook": "Lookbook",
    "deal": "Deal-Zeile",
}
DE_PROMO = {
    "": "Standard",
    "preis": "Preis zuerst",
    "regal": "Regal",
    "lookbook": "Lookbook",
    "deal": "Deal-Zeile",
    "coupon": "Coupon",
    "ring": "Countdown-Ring",
}

NEW_MSGIDS = {
    "Shelf": {"de": "Regal", "en": "Shelf", "ru": "Полка", "uk": "Полиця", "tr": "Raf"},
    "Compact with photo": {
        "de": "Kompakt mit Foto",
        "en": "Compact with photo",
        "ru": "Компактно с фото",
        "uk": "Компактно з фото",
        "tr": "Fotoğraflı kompakt",
    },
    "Deal row": {
        "de": "Deal-Zeile",
        "en": "Deal row",
        "ru": "Строка-предложение",
        "uk": "Рядок-пропозиція",
        "tr": "Fırsat satırı",
    },
}
OLD_MSGIDS = ("Shelf label", "Compact row", "Deal tile")
OLD_DE_NAMES = ("Preis-Etikett", "Regal-Preisschild", "Kompakte Zeile", "Deal-Kachel")


def _po(lang: str) -> polib.POFile:
    return polib.pofile(str(ROOT / "locale" / lang / "LC_MESSAGES" / "django.po"))


@pytest.mark.parametrize(
    ("kind", "expected"), [(card_forms.PRODUCT, DE_PRODUCT), (card_forms.PROMO, DE_PROMO)]
)
def test_german_labels_follow_mockup_m0_2(kind, expected):
    with translation.override("de"):
        got = {key: str(label) for key, label, _hint in card_forms.forms_for(kind)}
    assert got == expected


@pytest.mark.parametrize("lang", LANGS)
@pytest.mark.parametrize("kind", [card_forms.PRODUCT, card_forms.PROMO])
def test_labels_are_unique_within_kind(kind, lang):
    with translation.override(lang):
        labels = [str(label) for _key, label, _hint in card_forms.forms_for(kind)]
    assert len(labels) == len(set(labels)), labels


def test_label_for_reads_the_registry():
    with translation.override("de"):
        for kind, expected in ((card_forms.PRODUCT, DE_PRODUCT), (card_forms.PROMO, DE_PROMO)):
            for key, name in expected.items():
                assert str(card_forms.label_for(key, kind)) == name
        assert card_forms.label_for("coupon", card_forms.PRODUCT) == ""


def test_page_settings_and_list_panel_take_labels_from_registry():
    from apps.core import list_blocks, page_settings, studio_pages

    with translation.override("de"):
        for code, kind in (
            ("product_card_form", card_forms.PRODUCT),
            ("promo_card_form", card_forms.PROMO),
        ):
            setting = studio_pages.SETTINGS[code]
            got = {c.value: str(c.label) for c in page_settings.choices(setting)}
            assert got == {k: str(lab) for k, lab, _h in card_forms.forms_for(kind)}
        opts = {key: label for key, label, _srcs in list_blocks.card_options()}
    assert opts["deal"] == "Deal-Zeile" and opts["compact"] == "Kompakt mit Foto"


#: Экраны, показывающие подпись формы, — каждый зовёт реестр.
SCREENS = {
    "apps/catalog/forms.py": "forms_for(",
    "apps/catalog/views.py": "forms_for(",
    "apps/booking/views.py": "forms_for(",
    "apps/promotions/forms.py": "forms_for(",
    "apps/promotions/views.py": "forms_for(",
    "apps/core/page_settings.py": "forms_for(",
    "apps/core/design_page.py": "label_for(",
    "apps/core/list_blocks.py": "label_for(",
    "apps/core/block_card.py": "label_for(",
}


@pytest.mark.parametrize(("path", "call"), sorted(SCREENS.items()))
def test_every_screen_calls_the_registry(path, call):
    assert f"card_forms.{call}" in (ROOT / path).read_text(encoding="utf-8")


_TRANSLATED = re.compile(
    r"""(?:\b_|gettext(?:_lazy)?|\btrans|\bblocktrans)\s*\(?\s*["']([^"']+)["']"""
)


def _code_files():
    for base in ("apps", "templates"):
        for path in (ROOT / base).rglob("*"):
            if path.suffix in {".py", ".html"} and "tests" not in path.parts:
                yield path


def test_no_old_german_names_in_translatable_strings():
    """Старые имена не вернутся вторым списком: ни в `_("…")`/`{% trans %}` кода, ни в
    msgstr de записей реестра. Комментарии и «Kompakte Zeilen» (вид списка) — не в счёт."""
    old = re.compile(r"\b(?:" + "|".join(re.escape(n) for n in OLD_DE_NAMES) + r")\b")
    bad = []
    for path in _code_files():
        for msg in _TRANSLATED.findall(path.read_text(encoding="utf-8")):
            if old.search(msg) and not msg.startswith("Kompakte Zeilen"):
                bad.append(f"{path.relative_to(ROOT)}: {msg}")
    assert not bad, bad
    src = (ROOT / "apps/core/card_forms.py").read_text(encoding="utf-8")
    for msgid in OLD_MSGIDS:
        assert f'_("{msgid}")' not in src
    block = src.split("CARD_FORMS:", 1)[1].split("\n]\n", 1)[0]
    registry_ids = set(re.findall(r'\(\s*"[a-z]*",\s*_\("([^"]+)"\)', block))
    assert len(registry_ids) == len(card_forms.CARD_FORMS)
    de = _po("de")
    for entry in de:
        if entry.msgid in registry_ids and not entry.msgctxt:
            assert not old.search(entry.msgstr), (entry.msgid, entry.msgstr)


@pytest.mark.parametrize("lang", LANGS)
def test_new_msgids_are_translated_in_every_catalog(lang):
    po = _po(lang)
    entries = {e.msgid: e for e in po if not e.msgctxt and not e.obsolete}
    for msgid, tr in NEW_MSGIDS.items():
        assert msgid in entries, f"{lang}: нет {msgid!r}"
        assert entries[msgid].msgstr == tr[lang], (lang, msgid, entries[msgid].msgstr)
        assert "fuzzy" not in entries[msgid].flags
    for msgid in OLD_MSGIDS:
        assert msgid not in entries, f"{lang}: осталась старая запись {msgid!r}"
    if lang == "de":
        assert entries["Price tag"].msgstr == "Preisschild"
