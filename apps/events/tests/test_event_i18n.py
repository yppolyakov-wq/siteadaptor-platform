"""PR-B: двуязычные Event.title/description (витрина читает *_text).

Платформенный механизм (любой тенант); переводы сидятся демо-китом. Фолбэк на
плоские поля — одноязычные события не ломаются. Property читают поля в памяти
(get_i18n по getattr) — БД не нужна.
"""

from django.utils import translation

from apps.events.models import Event


def test_title_text_falls_back_to_flat_title():
    ev = Event(title="Yoga Retreat")
    assert ev.title_text == "Yoga Retreat"
    assert ev.description_text == ""


def test_title_text_uses_locale_overlay():
    ev = Event(
        title="Veganer Kochkurs",
        title_i18n={"de": "Veganer Kochkurs", "en": "Vegan Cooking Class"},
        description="Lecker",
        description_i18n={"de": "Lecker", "en": "Tasty"},
    )
    with translation.override("en"):
        assert ev.title_text == "Vegan Cooking Class"
        assert ev.description_text == "Tasty"
    with translation.override("de"):
        assert ev.title_text == "Veganer Kochkurs"
        assert ev.description_text == "Lecker"


def test_unknown_locale_falls_back_to_de():
    ev = Event(title="X", title_i18n={"de": "Deutsch", "en": "English"})
    with translation.override("fr"):
        assert ev.title_text == "Deutsch"  # фолбэк de


def test_partial_i18n_falls_back_to_flat_field():
    # i18n задан только для title; description берётся из плоского поля.
    ev = Event(title="X", title_i18n={"en": "Only EN"}, description="Beschreibung")
    with translation.override("en"):
        assert ev.title_text == "Only EN"
        assert ev.description_text == "Beschreibung"
