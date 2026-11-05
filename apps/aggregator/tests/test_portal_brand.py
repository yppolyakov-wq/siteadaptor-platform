"""PH-1: бренд «<Город>Markt» — сидер, вордмарк, заголовок страницы."""

import pytest

from apps.aggregator import branding
from apps.aggregator.models import AggregatorPortal

pytestmark = pytest.mark.django_db


def _legacy(city="Solingen", **kw):
    return AggregatorPortal.objects.create(
        host=f"{city.lower()}.test",
        kind=AggregatorPortal.KIND_CITY,
        city=city,
        title={"de": f"Angebote in {city}", "en": f"Offers in {city}"},
        **kw,
    )


def test_refresh_renames_legacy_portal_once():
    p = _legacy()
    assert branding.refresh_city_brand(p) is True
    p.refresh_from_db()
    assert p.title["de"] == p.title["en"] == "SolingenMarkt"
    assert p.primary_color == branding.BRAND_COLOR
    assert p.tagline["de"] == "Alles aus der Klingenstadt"
    assert branding.refresh_city_brand(p) is False  # идемпотентно


def test_refresh_keeps_operator_edits():
    p = _legacy(primary_color="#123456")
    assert branding.refresh_city_brand(p) is False
    q = AggregatorPortal.objects.create(
        host="x.test",
        kind=AggregatorPortal.KIND_CITY,
        city="Wuppertal",
        title={"de": "Mein Portal"},
    )
    assert branding.refresh_city_brand(q) is False
    q.refresh_from_db()
    assert q.title == {"de": "Mein Portal"}


@pytest.mark.parametrize(
    ("title", "city", "parts"),
    [
        ("SolingenMarkt", "Solingen", ("Solingen", "Markt")),
        ("BadHonnefMarkt", "Bad Honnef", ("BadHonnef", "Markt")),
        ("Gesund in Solingen", "Solingen", ("", "Gesund in Solingen")),
        ("Solingen", "Solingen", ("", "Solingen")),
        ("Markt", "", ("", "Markt")),
    ],
)
def test_wordmark(title, city, parts):
    assert branding.wordmark(title, city) == parts


def test_other_city_gets_generic_tagline():
    brand = branding.city_brand("Wuppertal")
    assert brand["title"]["de"] == "WuppertalMarkt"
    assert "Wuppertal" in brand["tagline"]["de"]
