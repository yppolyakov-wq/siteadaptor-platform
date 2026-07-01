"""Волна L / L3 — i18n на stays.StayUnit (overlay-семантика, зеркало Service).

База — в плоских `name`/`description`; переводы неосновных локалей — в оверлее
`name_i18n`/`description_i18n`. Аксессоры `*_localized`/`*_i18n_full` — для U-A.
"""

from apps.stays.models import StayUnit


def test_localized_falls_back_to_plain_when_no_overlay():
    u = StayUnit(name="Doppelzimmer", description="Mit Balkon")
    assert u.name_localized() == "Doppelzimmer"
    assert u.name_localized("en") == "Doppelzimmer"
    assert u.description_localized("en") == "Mit Balkon"


def test_localized_returns_overlay_for_non_base_locale():
    u = StayUnit(
        name="Doppelzimmer",
        description="Mit Balkon",
        name_i18n={"en": "Double room"},
        description_i18n={"en": "With balcony"},
    )
    assert u.name_localized("en") == "Double room"
    assert u.description_localized("en") == "With balcony"
    assert u.name_localized("de") == "Doppelzimmer"  # база — плоское поле


def test_i18n_full_merges_base_and_overlay():
    u = StayUnit(name="Doppelzimmer", name_i18n={"en": "Double room"})
    assert u.name_i18n_full == {"de": "Doppelzimmer", "en": "Double room"}


def test_non_dict_overlay_is_safe():
    u = StayUnit(name="Doppelzimmer", description_i18n="broken")
    assert u.description_localized("en") == ""  # база пуста → ''
    assert u.name_localized("en") == "Doppelzimmer"
