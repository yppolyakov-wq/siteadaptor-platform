"""Немецкий кабинет/витрина показывали английское имя события: оверлей без ключа «de»
(перевод только неосновных локалей), а `get_i18n` при отсутствии de падал на «en»."""

import pytest
from django.utils import timezone, translation

from apps.core import sellable
from apps.events.models import Event

pytestmark = pytest.mark.django_db


def _event():
    return Event.objects.create(
        title="Wein-Tasting mit Sommelier",
        title_i18n={"en": "Wine tasting with a sommelier"},
        description="Fünf Weine",
        description_i18n={"en": "Five wines"},
        starts_at=timezone.now(),
    )


def test_german_shows_base_field_not_english_overlay():
    ev = _event()
    with translation.override("de"):
        assert ev.title_text == "Wein-Tasting mit Sommelier"
        assert ev.description_text == "Fünf Weine"
    assert sellable.display_fields("event", ev, "de")["name"] == "Wein-Tasting mit Sommelier"


def test_english_still_gets_translation():
    ev = _event()
    with translation.override("en"):
        assert ev.title_text == "Wine tasting with a sommelier"
    assert sellable.display_fields("event", ev, "en")["name"] == "Wine tasting with a sommelier"
