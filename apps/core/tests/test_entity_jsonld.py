"""UA4-4b: per-entity JSON-LD (schema.org @type + AggregateRating из отзывов)."""

import json
from types import SimpleNamespace

from django.test import RequestFactory

from apps.core.seo import entity_ld
from apps.core.templatetags.seo import entity_jsonld


def _sellable(kind="product", **kw):
    return SimpleNamespace(
        kind=kind,
        name=kw.get("name", "Bio-Brot"),
        description=kw.get("description", "Frisch gebacken."),
        image_url=kw.get("image_url", "https://cdn.test/x.jpg"),
        detail_url=kw.get("detail_url", "/sortiment/abc/"),
    )


def test_entity_ld_none_is_empty():
    assert entity_ld(None, url="https://x.test/") == ""


def test_entity_ld_product_shape():
    data = json.loads(entity_ld(_sellable("product"), url="https://x.test/p/"))
    assert data["@type"] == "Product"
    assert data["name"] == "Bio-Brot"
    assert data["description"] == "Frisch gebacken."
    assert data["image"] == "https://cdn.test/x.jpg"
    assert data["url"] == "https://x.test/p/"
    assert "aggregateRating" not in data  # без отзывов — нет рейтинга


def test_entity_ld_schema_type_per_kind():
    kinds = {
        "product": "Product",
        "service": "Service",
        "stay": "LodgingBusiness",
        "event": "Event",
    }
    for kind, expected in kinds.items():
        data = json.loads(entity_ld(_sellable(kind), url="https://x.test/"))
        assert data["@type"] == expected, kind


def test_entity_ld_unknown_kind_defaults_to_product():
    data = json.loads(entity_ld(_sellable("combo"), url="https://x.test/"))
    assert data["@type"] == "Product"


def test_entity_ld_aggregate_rating_from_summary():
    data = json.loads(
        entity_ld(
            _sellable("service"),
            url="https://x.test/",
            review_summary={"avg": 4.5, "count": 3},
        )
    )
    ar = data["aggregateRating"]
    assert ar["@type"] == "AggregateRating"
    assert ar["ratingValue"] == "4.5"
    assert ar["reviewCount"] == 3
    assert ar["bestRating"] == "5" and ar["worstRating"] == "1"


def test_entity_ld_no_rating_when_count_zero():
    data = json.loads(
        entity_ld(_sellable(), url="https://x.test/", review_summary={"avg": None, "count": 0})
    )
    assert "aggregateRating" not in data


# --- шаблонный тег ----------------------------------------------------------
def test_entity_jsonld_tag_renders_script():
    request = RequestFactory().get("/sortiment/abc/")
    out = entity_jsonld({"request": request}, _sellable("product"))
    assert out.startswith('<script type="application/ld+json">')
    assert '"@type":"Product"' in out
    assert "http://testserver/sortiment/abc/" in out  # абсолютный URL из detail_url


def test_entity_jsonld_tag_empty_without_sellable():
    request = RequestFactory().get("/")
    assert entity_jsonld({"request": request}, None) == ""


def test_entity_jsonld_tag_empty_without_request():
    assert entity_jsonld({}, _sellable()) == ""


def test_entity_jsonld_escapes_script_breakout():
    """XSS: имя/описание тенанта с `</script>` не должно вырывать из JSON-LD блока."""
    request = RequestFactory().get("/x/")
    payload_name = "Brot</script><script>alert(1)</script>"
    out = entity_jsonld({"request": request}, _sellable("product", name=payload_name))
    prefix = '<script type="application/ld+json">'
    assert out.startswith(prefix) and out.endswith("</script>")
    inner = out[len(prefix) : -len("</script>")]
    assert "</script>" not in inner and "<script>" not in inner  # не вырваться из блока
    assert json.loads(inner)["name"] == payload_name  # но JSON остаётся валидным (декод обратно)
