"""Волна L / L3 — i18n на booking.Service (overlay-семантика).

Базовая локаль живёт в плоском `name`/`description` (source of truth, без дрейфа),
переводы неосновных локалей — в оверлее `name_i18n`/`description_i18n`. Аксессоры
`*_localized` / `*_i18n_full` — единый вид для адаптера SellableEntity (U-A).
"""

from apps.booking.models import Service


def test_localized_falls_back_to_plain_when_no_overlay():
    s = Service(name="Ölwechsel", description="Öl + Filter")
    assert s.name_localized() == "Ölwechsel"
    assert s.name_localized("en") == "Ölwechsel"  # нет перевода → база (без потерь)
    assert s.description_localized("fr") == "Öl + Filter"


def test_localized_returns_overlay_for_non_base_locale():
    s = Service(
        name="Ölwechsel",
        description="Öl + Filter",
        name_i18n={"en": "Oil change"},
        description_i18n={"en": "Oil + filter"},
    )
    assert s.name_localized("en") == "Oil change"
    assert s.description_localized("en") == "Oil + filter"


def test_base_locale_always_reads_plain_field_not_overlay():
    """Инвариант «без дрейфа»: для базовой локали (de) берём ПЛОСКОЕ поле, даже если
    в оверлее случайно оказалась запись 'de'."""
    s = Service(name="Ölwechsel", name_i18n={"de": "STALE", "en": "Oil change"})
    assert s.name_localized("de") == "Ölwechsel"  # плоское поле, не оверлей
    assert s.name_localized("en") == "Oil change"


def test_missing_non_base_translation_falls_back_to_plain():
    s = Service(name="Ölwechsel", name_i18n={"en": "Oil change"})
    assert s.name_localized("fr") == "Ölwechsel"  # fr нет → база


def test_i18n_full_merges_base_and_overlay():
    s = Service(name="Ölwechsel", name_i18n={"en": "Oil change", "fr": "Vidange"})
    assert s.name_i18n_full == {"de": "Ölwechsel", "en": "Oil change", "fr": "Vidange"}


def test_i18n_full_base_wins_over_stray_overlay_entry():
    s = Service(name="Ölwechsel", name_i18n={"de": "STALE"})
    assert s.name_i18n_full == {"de": "Ölwechsel"}  # база из плоского поля


def test_non_dict_overlay_is_safe():
    s = Service(name="Ölwechsel", name_i18n=None)
    assert s.name_localized("en") == "Ölwechsel"
    assert s.name_i18n_full == {"de": "Ölwechsel"}


def test_empty_overlay_values_ignored_in_full():
    s = Service(name="Ölwechsel", name_i18n={"en": ""})
    assert s.name_localized("en") == "Ölwechsel"  # пустой перевод → база
    assert s.name_i18n_full == {"de": "Ölwechsel"}  # пустое не попадает в full
