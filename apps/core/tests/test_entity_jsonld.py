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


def test_entity_jsonld_tag_autorepair_for_kfz_service():
    # A9: услуга Kfz-Werkstatt (site_config.jobs_vehicle) → @type AutoRepair
    request = RequestFactory().get("/leistung/abc/")
    request.tenant = SimpleNamespace(site_config={"jobs_vehicle": True})
    out = entity_jsonld({"request": request}, _sellable("service", detail_url="/leistung/abc/"))
    assert '"@type":"AutoRepair"' in out


def test_entity_jsonld_tag_service_stays_service_without_kfz():
    request = RequestFactory().get("/leistung/abc/")
    request.tenant = SimpleNamespace(site_config={})
    out = entity_jsonld({"request": request}, _sellable("service", detail_url="/leistung/abc/"))
    assert '"@type":"Service"' in out


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
    # UC4-2: тег эмитит НЕСКОЛЬКО блоков (entity + BreadcrumbList) — проверяем каждый.
    import re

    blocks = re.findall(r'<script type="application/ld\+json">(.*?)</script>', out, re.S)
    assert blocks  # как минимум entity-блок
    for inner in blocks:
        assert "</script>" not in inner and "<script>" not in inner  # не вырваться из блока
    assert json.loads(blocks[0])["name"] == payload_name  # JSON валиден (декод обратно)


# --- UC4-2: Offer + ld_extra + BreadcrumbList --------------------------------
def test_entity_ld_offer_from_price_value():
    from decimal import Decimal

    s = _sellable("product")
    s.price_value = Decimal("3.50")
    s.price_currency = "EUR"
    s.ld_extra = {"offer": {"availability": "https://schema.org/InStock"}}
    data = json.loads(entity_ld(s, url="https://x.test/p/"))
    offer = data["offers"]
    assert offer["@type"] == "Offer"
    assert offer["price"] == "3.50" and offer["priceCurrency"] == "EUR"
    assert offer["availability"] == "https://schema.org/InStock"
    assert offer["url"] == "https://x.test/p/"


def test_entity_ld_no_offer_without_price_value():
    data = json.loads(entity_ld(_sellable("service"), url="https://x.test/"))
    assert "offers" not in data


def test_entity_ld_event_extra_startdate_location():
    s = _sellable("event")
    s.ld_extra = {
        "startDate": "2026-08-01T18:00:00+02:00",
        "location": {"@type": "Place", "name": "Stadthalle"},
    }
    data = json.loads(entity_ld(s, url="https://x.test/e/"))
    assert data["startDate"] == "2026-08-01T18:00:00+02:00"
    assert data["location"]["name"] == "Stadthalle"
    assert not hasattr(s.ld_extra, "offer")  # контракт не мутируем
    assert "offer" not in data  # вложенный ключ не утёк top-level


def test_entity_jsonld_tag_emits_breadcrumbs():
    import re

    request = RequestFactory().get("/sortiment/abc/")
    out = entity_jsonld({"request": request}, _sellable("product"))
    blocks = [json.loads(b) for b in re.findall(r"json\">(.*?)</script>", out, re.S)]
    bc = next(b for b in blocks if b["@type"] == "BreadcrumbList")
    names = [el["name"] for el in bc["itemListElement"]]
    assert names == ["Start", "Sortiment", "Bio-Brot"]
    assert [el["position"] for el in bc["itemListElement"]] == [1, 2, 3]
    assert "item" not in bc["itemListElement"][-1]  # текущая крошка без item
