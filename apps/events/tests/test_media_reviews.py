"""R13: медиа-отзывы — фото + рейтинг, истории «до/после», значки сертификации.

Всё курируется организатором в `Event.details` (лендинг). Схема расширена в
`details._SCHEMA`; `Event.landing_testimonials` отдаёт отзывы со звёздами для
шаблона. Старые 3-кортежные отзывы остаются валидными (photo/rating пустые).
"""

from datetime import timedelta

import pytest
from django.utils import timezone

from apps.events import details
from apps.events.models import Event

pytestmark = pytest.mark.django_db


def _event(**kw):
    defaults = {
        "title": "Yoga-Retreat",
        "starts_at": timezone.now() + timedelta(days=30),
        "status": Event.STATUS_PUBLISHED,
    }
    defaults.update(kw)
    return Event.objects.create(**defaults)


# --- схема details ------------------------------------------------------------


def test_normalize_testimonials_with_photo_and_rating():
    d = details.normalize({"testimonials": [["Anna", "Köln", "Toll!", "https://x/p.jpg", "5"]]})
    assert d["testimonials"] == [
        {"name": "Anna", "city": "Köln", "text": "Toll!", "photo": "https://x/p.jpg", "rating": "5"}
    ]


def test_testimonials_backward_compatible_triple():
    d = details.normalize({"testimonials": [["Bea", "Bonn", "Schön."]]})
    t = d["testimonials"][0]
    assert t["name"] == "Bea" and t["photo"] == "" and t["rating"] == ""


def test_normalize_before_after_and_certifications():
    d = details.normalize(
        {
            "before_after": [["https://x/v.jpg", "https://x/n.jpg", "Erholt"]],
            "certifications": [["RYT-500", "Yoga Alliance", "https://x/l.svg"]],
        }
    )
    assert d["before_after"][0] == {
        "before": "https://x/v.jpg",
        "after": "https://x/n.jpg",
        "text": "Erholt",
    }
    assert d["certifications"][0]["name"] == "RYT-500"


def test_is_rich_true_with_only_certifications():
    assert details.is_rich({"certifications": [["RYT-500", "Yoga Alliance", ""]]}) is True


# --- Event.landing_testimonials ----------------------------------------------


def test_landing_testimonials_adds_stars():
    event = _event(details={"testimonials": [["Anna", "Köln", "Toll!", "", "4"]]})
    t = event.landing_testimonials[0]
    assert t["rating"] == 4
    assert t["stars"] == "★★★★☆"


def test_landing_testimonials_clamps_and_defaults_rating():
    event = _event(
        details={
            "testimonials": [
                ["A", "", "x", "", "9"],  # > 5 → 5
                ["B", "", "y", "", "abc"],  # мусор → 0
                ["C", "", "z"],  # без оценки → 0
            ]
        }
    )
    out = event.landing_testimonials
    assert out[0]["rating"] == 5 and out[0]["stars"] == "★★★★★"
    assert out[1]["rating"] == 0 and out[1]["stars"] == "☆☆☆☆☆"
    assert out[2]["rating"] == 0


def test_form_roundtrips_media_review_fields():
    from apps.events.forms import EventForm

    form = EventForm(
        data={
            "title": "Retreat",
            "starts_at": "2099-01-01T10:00",
            "capacity": 20,
            "price_eur": "0",
            "testimonials_text": "Anna | Köln | Toll! | https://x/p.jpg | 5",
            "before_after_text": "https://x/v.jpg | https://x/n.jpg | Erholt",
            "certifications_text": "RYT-500 | Yoga Alliance | https://x/l.svg",
        }
    )
    assert form.is_valid(), form.errors
    event = form.save()
    assert event.landing["testimonials"][0]["photo"] == "https://x/p.jpg"
    assert event.landing["before_after"][0]["after"] == "https://x/n.jpg"
    assert event.landing["certifications"][0]["issuer"] == "Yoga Alliance"
    assert event.landing_testimonials[0]["stars"] == "★★★★★"
