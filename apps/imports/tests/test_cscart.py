"""M21.2: перенос магазина CS-Cart — разбор, запись, переадресации."""

import io
from decimal import Decimal
from pathlib import Path

import pytest
from PIL import Image

from apps.catalog.models import Category, Product
from apps.core import legacy_redirects
from apps.core.models import LegacyRedirect, LegalDoc
from apps.imports import cscart

FIX = Path(__file__).parent / "fixtures" / "cscart"
BASE = "https://shop.example/"


def _read(name):
    return (FIX / name).read_text(encoding="utf-8")


class _Got:
    def __init__(self, body, status=200):
        self.status, self.body = status, body

    @property
    def ok(self):
        return 200 <= self.status < 300

    def text(self):
        return self.body.decode()


def _jpeg():
    buf = io.BytesIO()
    Image.new("RGB", (40, 30), (120, 80, 40)).save(buf, "JPEG")
    return _Got(buf.getvalue())


# --- разбор ---------------------------------------------------------------------


def test_parse_sitemap_tree_names_and_host_filter():
    cats = cscart.parse_sitemap(_read("sitemap.html"), BASE)
    paths = [c.path for c in cats]
    assert paths == [
        "schwarzertee",
        "schwarzertee/aromatisch",
        "schwarzertee/klassisch",
        "schwarzertee/klassisch/assam",
        "grunertee",
        "grunertee/aromatisch",
    ]
    assert cats[0].name == "Schwarzertee"
    assert cats[1].name == "Aromatisch SCHWARZERTEE"  # смешанный регистр не трогаем
    assert cats[3].parent_path == "schwarzertee/klassisch"


def test_parse_listing_only_products_of_known_categories():
    known = {c.path for c in cscart.parse_sitemap(_read("sitemap.html"), BASE)}
    found, has_next = cscart.parse_listing(_read("listing.html"), BASE, known)
    assert found == {
        "https://shop.example/schwarzertee/klassisch/assam/assam-ctc/",
        "https://shop.example/schwarzertee/klassisch/assam/assam-fop/",
    }
    assert has_next is True


def test_parse_product_variants_labels_images():
    url = "https://shop.example/schwarzertee/klassisch/assam/assam-ctc/"
    p = cscart.parse_product(_read("product.html"), url)
    assert p.name == "Assam CTC" and p.sku == "HT105" and p.product_id == "800"
    assert p.category_path == "schwarzertee/klassisch/assam"
    assert [(v.sku, v.label, v.grams, v.price) for v in p.variants] == [
        ("HT105", "100 g", Decimal("100"), Decimal("5.99")),
        ("HT105.1", "250 g", Decimal("250"), Decimal("14.25")),
        ("HT105.2", "500 g", Decimal("500"), Decimal("27.7")),
        ("HT105.3", "1 kg", Decimal("1000"), Decimal("53.91")),
    ]
    assert p.variants[2].in_stock is False
    assert p.variants[1].image_url == "https://shop.example/images/detailed/9/HT105_250.jpg"
    assert p.image_urls == ["https://shop.example/images/detailed/9/HT105_main.jpg"]
    assert "kräftiger" in p.description_html
    assert sorted(p.variation_ids) == ["800", "804", "805", "806"]


def test_parse_product_without_json_ld_is_none():
    assert cscart.parse_product("<html></html>", BASE + "x/y/") is None


def test_grams_and_labels():
    assert cscart.grams_of("1,5 kg") == Decimal("1500")
    assert cscart.grams_of("Dose") is None
    assert cscart.nice_label("250G") == "250 g"


def test_html_to_text_keeps_paragraphs():
    text = cscart.html_to_text(cscart.page_body(_read("agb.html")))
    assert text.splitlines()[0] == "1. Geltungsbereich"
    assert "Für alle Bestellungen\ngilt dies." in text
    assert "Fuss" not in text


# --- обход + запись -----------------------------------------------------------------


def _fake_fetch(url):
    if url.endswith("/sitemap/"):
        return _Got(_read("sitemap.html").encode())
    if "?items_per_page" in url:
        if url.startswith(BASE + "schwarzertee/klassisch/assam/?") and "page=1" in url:
            return _Got(_read("listing.html").encode())
        return _Got(b"<html></html>")
    if url.endswith("/assam-ctc/"):
        return _Got(_read("product.html").encode())
    if url.endswith("/allgemeine-geschaftsbedienungen/"):
        return _Got(_read("agb.html").encode())
    return _Got(b"", status=404)


def _scrape():
    return cscart.scrape("https://shop.example", fetch=_fake_fetch, pause=0)


def test_scrape_collects_categories_products_and_errors():
    site = _scrape()
    assert len(site.categories) == 6
    assert [p.sku for p in site.products] == ["HT105"]
    assert any("assam-fop" in e for e in site.errors)  # 404 — в отчёт, не падение
    assert "agb" in site.pages


@pytest.mark.django_db
def test_apply_creates_catalog_redirects_and_is_idempotent():
    site = _scrape()
    calls = []

    def fetch_image(url):
        calls.append(url)
        return _jpeg()

    stats = cscart.apply_site(site, fetch_image=fetch_image)
    assert stats.categories_created == 6 and stats.products_created == 1
    # одинаковый сегмент «aromatisch» у двух родителей → второй с префиксом родителя
    assert Category.objects.filter(slug="aromatisch").exists()
    assert Category.objects.filter(slug="grunertee-aromatisch").exists()
    assam = Category.objects.get(slug="assam")
    assert assam.parent.slug == "klassisch" and assam.parent.parent.slug == "schwarzertee"

    product = Product.objects.get()
    assert product.slug == "assam-ctc" and product.category == assam
    assert product.base_price == Decimal("5.99") and product.vat_rate == Decimal("7.00")
    assert product.unit == "g" and product.content_amount == Decimal("100")
    assert "<script>" not in product.description["de"]
    assert product.images and product.metadata["cscart"]["product_id"] == "800"
    variants = list(product.variants.order_by("sort_order"))
    assert [v.label for v in variants] == ["100 g", "250 g", "500 g", "1 kg"]
    assert variants[2].stock_quantity == 0 and variants[0].stock_quantity is None
    assert variants[1].images and variants[3].images

    target = product.get_absolute_url()
    assert legacy_redirects.match("/schwarzertee/klassisch/assam/assam-ctc/", "").target == target
    assert (
        legacy_redirects.match("/index.php", "dispatch=products.view&product_id=805&sl=de").target
        == target
    )
    assert legacy_redirects.match("/schwarzertee/klassisch/assam/", "").target == (
        "/sortiment/assam/"
    )
    assert legacy_redirects.match("/blog/", "").status == LegacyRedirect.STATUS_GONE
    assert legacy_redirects.match("/allgemeine-geschaftsbedienungen/", "").target == "/agb/"
    assert LegalDoc.objects.get(kind="agb", locale="de").text.startswith("1. Geltungsbereich")

    # повторный прогон: без дублей, фото не перекачиваются, правка владельца AGB цела
    LegalDoc.objects.filter(kind="agb").update(text="Eigene AGB")
    n_calls, n_rules = len(calls), LegacyRedirect.objects.count()
    again = cscart.apply_site(site, fetch_image=fetch_image)
    assert again.categories_created == 0 and again.products_updated == 1
    assert Category.objects.count() == 6 and Product.objects.count() == 1
    assert product.variants.count() == 4
    assert LegacyRedirect.objects.count() == n_rules
    assert len(calls) == n_calls
    assert LegalDoc.objects.get(kind="agb").text == "Eigene AGB"


@pytest.mark.django_db
def test_apply_about_only_fills_empty_profile():
    from apps.tenants.tests.factories import TenantFactory

    site = cscart.ScrapedSite(base=BASE, pages={"about": "<p>Wir lieben Tee.</p>"})
    tenant = TenantFactory(schema_name="public")
    tenant.site_config = {}
    assert cscart.apply_about(tenant, site) is True
    assert tenant.site_config["about_text"] == "Wir lieben Tee."
    tenant.site_config = {"about_text": "Eigener Text"}
    assert cscart.apply_about(tenant, site) is False


@pytest.mark.django_db
def test_product_without_price_is_hidden_and_weight_from_name():
    p = cscart.CsProduct(
        url=BASE + "krautertee/monokrauter/kamille/",
        path="krautertee/monokrauter/kamille",
        name="Kamillenblüten ganz, 100g",
        sku="HT90059",
        variants=[cscart.CsVariant(sku="", price=Decimal("0"), url=BASE)],
    )
    stats = cscart.apply_site(cscart.ScrapedSite(base=BASE, products=[p]), with_images=False)
    product = Product.objects.get()
    assert product.is_active is False and product.primary_action == "request"
    assert product.content_amount == Decimal("100") and product.unit == "g"
    assert any("HT90059" in n for n in stats.notes)


@pytest.mark.django_db
def test_same_slug_in_two_categories_gets_category_suffix():
    def prod(path):
        return cscart.CsProduct(
            url=BASE + path + "/",
            path=path,
            name="Chai",
            sku=path,
            variants=[cscart.CsVariant(sku=path, price=Decimal("4"), url=BASE)],
        )

    cscart.apply_site(
        cscart.ScrapedSite(base=BASE, products=[prod("rooibos/chai"), prod("schwarzertee/chai")]),
        with_images=False,
    )
    assert set(Product.objects.values_list("slug", flat=True)) == {"chai", "chai-schwarzertee"}
