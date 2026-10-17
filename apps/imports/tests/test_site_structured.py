"""T-8.27b: разбор JSON-LD/OG без ИИ."""

from apps.imports.site import htmlparse, structured
from apps.imports.tests.site_fakes import html

URL = "https://laden.example/p/1"


def _extract(*pages):
    return structured.extract([htmlparse.parse(p, URL) for p in pages])


PRODUCT = {
    "@context": "https://schema.org",
    "@type": "Product",
    "name": "Bauernbrot <b>1 kg</b>",
    "description": "<p>Sauerteig &amp; Roggen</p>",
    "image": ["https://laden.example/brot.jpg"],
    "sku": "BB-1",
    "gtin13": "4006381333931",
    "offers": {"@type": "Offer", "price": "4.90", "priceCurrency": "EUR"},
}


def test_jsonld_product_offer_extracted():
    (item,) = _extract(html(jsonld=[PRODUCT]))["items"]
    assert item["name"] == "Bauernbrot 1 kg"
    assert item["description"] == "Sauerteig & Roggen"
    assert item["price"] == "4.90" and item["gtin"] == "4006381333931"
    assert item["image_url"] == "https://laden.example/brot.jpg"
    assert item["kind"] == "product" and item["method"] == "structured"


def test_jsonld_graph_and_itemlist():
    graph = {
        "@graph": [
            {"@type": "ItemList", "itemListElement": [{"@type": "ListItem", "item": PRODUCT}]},
            {"@type": "Service", "name": "Torte auf Bestellung", "offers": {"price": "35"}},
        ]
    }
    items = _extract(html(jsonld=[graph]))["items"]
    assert {i["kind"] for i in items} == {"product", "service"}


def test_aggregate_offer_lowprice_used():
    node = {
        **PRODUCT,
        "offers": {"@type": "AggregateOffer", "lowPrice": "12,50", "highPrice": "20"},
    }
    (item,) = _extract(html(jsonld=[node]))["items"]
    assert item["price"] == "12.50"


def test_foreign_currency_price_dropped():
    node = {**PRODUCT, "offers": {"price": "5", "priceCurrency": "USD"}}
    (item,) = _extract(html(jsonld=[node]))["items"]
    assert item["price"] is None


def test_localbusiness_hours_to_structured():
    biz = {
        "@type": "Bakery",
        "name": "Backhaus Krume",
        "telephone": "+49 212 123456",
        "address": {
            "streetAddress": "Hauptstr. 1",
            "postalCode": "42651",
            "addressLocality": "Solingen",
        },
        "openingHoursSpecification": [
            {
                "dayOfWeek": ["https://schema.org/Monday", "Tuesday"],
                "opens": "07:00",
                "closes": "18:00",
            },
        ],
    }
    profile = _extract(html(jsonld=[biz]))["profile"]
    assert profile["name"] == "Backhaus Krume"
    assert profile["address"] == "Hauptstr. 1, 42651 Solingen"
    assert profile["opening_hours_structured"] == {"0": ["07:00", "18:00"], "1": ["07:00", "18:00"]}


def test_og_fallback_when_no_jsonld():
    page = html(
        meta={"og:type": "product", "og:title": "Honig 500 g", "product:price:amount": "7.50"},
    )
    (item,) = _extract(page)["items"]
    assert item["name"] == "Honig 500 g" and item["price"] == "7.50"


def test_brochure_site_yields_profile_only():
    page = html(
        body="<p>Willkommen in unserer Bäckerei!</p><a href='tel:+492121234'>Anrufen</a>",
        meta={"og:site_name": "Backhaus", "description": "Brot seit 1920"},
    )
    out = _extract(page)
    assert out["items"] == []
    assert out["profile"]["name"] == "Backhaus" and out["profile"]["phone"] == "+492121234"


def test_no_old_price_or_percent_ever_in_candidate():
    """PAngV: импорт не переносит «statt»/процент — даже если сайт их публикует."""
    node = {
        **PRODUCT,
        "offers": {
            "price": "4.90",
            "priceSpecification": {
                "price": "6.90",
                "priceType": "https://schema.org/StrikethroughPrice",
            },
        },
    }
    (item,) = _extract(html(jsonld=[node]))["items"]
    assert item["price"] == "4.90"
    assert not {"list_price", "old_price", "discount", "percent", "badge"} & set(item)


def test_broken_jsonld_and_html_do_not_crash():
    page = '<html><script type="application/ld+json">{not json</script><p>ok'
    assert _extract(page) == {"profile": {}, "items": [], "lang": ""}


def test_duplicate_products_merged_by_gtin():
    items = _extract(html(jsonld=[PRODUCT, {**PRODUCT, "name": "Anders"}]))["items"]
    assert len(items) == 1
