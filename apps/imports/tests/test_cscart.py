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
    assert legacy_redirects.match("/blog/afraid-of-zombies/", "").status == 410
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


def _prod(path, variants, **kw):
    return cscart.CsProduct(
        url=BASE + path + "/",
        path=path,
        name=kw.pop("name", "Tee"),
        sku=kw.pop("sku", "HT1"),
        variants=variants,
        **kw,
    )


def _v(sku, price, label="", stock=True):
    return cscart.CsVariant(
        sku=sku,
        price=Decimal(price),
        url=BASE,
        label=label,
        grams=cscart.grams_of(label),
        in_stock=stock,
    )


@pytest.mark.django_db
def test_zero_price_variant_skipped_and_single_offer_out_of_stock():
    p = _prod("tee/a", [_v("A", "5", "100g"), _v("A.1", "12", "250g"), _v("A.2", "0", "1kg")])
    q = _prod("tee/b", [_v("B", "4", stock=False)], sku="B")
    stats = cscart.apply_site(cscart.ScrapedSite(base=BASE, products=[p, q]), with_images=False)
    a = Product.objects.get(sku="HT1")
    assert sorted(a.variants.values_list("sku", flat=True)) == ["A", "A.1"]
    assert any("without price" in n for n in stats.notes)
    assert Product.objects.get(sku="B").stock_quantity == 0


@pytest.mark.django_db
def test_rerun_keeps_owner_stock_visibility_and_category():
    p = _prod("tee/a", [_v("A", "5", "100g"), _v("A.1", "12", "250g")])
    site = cscart.ScrapedSite(base=BASE, products=[p])
    cscart.apply_site(site, with_images=False)
    product = Product.objects.get()
    other = Category.objects.create(name={"de": "Neu"}, slug="neu")
    Product.objects.filter(pk=product.pk).update(category=other, vat_rate=Decimal("19"))
    product.variants.filter(sku="A.1").update(stock_quantity=7, is_active=False, label="Groß")
    p.variants[1].price = Decimal("13.50")
    cscart.apply_site(site, with_images=False)
    product.refresh_from_db()
    v = product.variants.get(sku="A.1")
    assert (v.stock_quantity, v.is_active, v.label, v.price) == (7, False, "Groß", Decimal("13.50"))
    assert product.category == other and product.vat_rate == Decimal("19.00")


@pytest.mark.django_db
def test_variants_without_sku_do_not_collapse():
    p = _prod("tee/a", [_v("", "5", "100g"), _v("", "12", "250g")])
    cscart.apply_site(cscart.ScrapedSite(base=BASE, products=[p]), with_images=False)
    assert Product.objects.get().variants.count() == 2


@pytest.mark.django_db
def test_import_does_not_override_manual_rule():
    legacy_redirects.upsert("/blog/", "/ueber-uns/")
    cscart.apply_site(cscart.ScrapedSite(base=BASE), with_images=False)
    rule = LegacyRedirect.objects.get(source_path="/blog")
    assert rule.origin == "manual" and rule.target == "/ueber-uns/"


def test_variant_image_prefers_longest_id():
    images = {"53000806": "u806", "53000006": "u6"}
    assert cscart._variant_image(images, "806", {"6", "806"}) == "u806"
    assert cscart._variant_image(images, "6", {"6", "806"}) == "u6"


# --- M21.3: главная, меню, логотип, контакты ---------------------------------------


def test_parse_home_banners_tiles_menu_logo_footer():
    home = cscart.parse_home(_read("home.html"), BASE)
    assert home.banners == [
        BASE + "images/promo/9/b1.jpg",
        BASE + "images/promo/9/b2.jpg",
        BASE + "images/promo/9/b3.jpg",
    ]
    assert home.tiles == [
        ("schwarzertee", BASE + "images/promo/9/black.png"),
        ("grunertee", BASE + "images/promo/9/green.png"),
    ]
    assert [label for label, _u in home.menu] == ["Schwarzer", "Grüner", "Assam", "Newest", "Sales"]
    assert home.logo_url == BASE + "images/logos/8/Logo.jpg"
    assert "Marktpassage 2" in home.footer_text


def test_hours_contacts_and_dangling_text():
    text = cscart.parse_home(_read("home.html"), BASE).footer_text
    assert cscart.parse_hours(text) == {
        **{str(d): ["10:00", "18:00"] for d in range(5)},
        "5": ["10:00", "14:00"],
    }
    assert cscart.parse_contacts(text) == {
        "address": "Marktpassage 2, 42781 Haan",
        "city": "Haan",
        "phone": "02129 54862",
    }
    body = cscart.html_to_text(cscart.page_body(_read("versand.html")))
    assert (
        cscart.strip_dangling(body) == "Wir versenden mit DHL.\n\nAbholung in der Filiale möglich."
    )


def test_dominant_color_ignores_white_background():
    buf = io.BytesIO()
    img = Image.new("RGB", (60, 30), (255, 255, 255))
    for x in range(20, 50):
        for y in range(5, 25):
            img.putpixel((x, y), (40, 50, 140))
    img.save(buf, "PNG")
    assert cscart.dominant_color(buf.getvalue()) == "#28328c"


def _site_with_home():
    site = cscart.scrape("https://shop.example", fetch=_fake_fetch_home, pause=0)
    return site


def _fake_fetch_home(url):
    if url == BASE:
        return _Got(_read("home.html").encode())
    if url.endswith("/versand/"):
        return _Got(_read("versand.html").encode())
    return _fake_fetch(url)


def _logo_png():
    buf = io.BytesIO()
    Image.new("RGB", (60, 30), (40, 50, 140)).save(buf, "PNG")
    return _Got(buf.getvalue())


@pytest.mark.django_db
def test_apply_design_like_old_site_and_keeps_owner_edits_on_rerun():
    from apps.tenants import siteconfig
    from apps.tenants.tests.factories import TenantFactory

    site = _site_with_home()
    assert site.pages["versand_title"] == "Versand"

    def fetch_image(url):
        return _logo_png() if "logos" in url else _jpeg()

    cscart.apply_site(site, fetch_image=fetch_image)
    tenant = TenantFactory(
        schema_name="public", address="", contact_phone="", opening_hours_structured={}
    )
    tenant.site_config, tenant.logo_url = {}, ""
    options = cscart.DesignOptions(
        hero_title="Die wunderbare Welt des Tees",
        hero_button_label="Lass mich verzaubern",
        skip_banners=(3,),
    )
    notes = cscart.apply_design(tenant, site, options=options, fetch_image=fetch_image)
    tenant.refresh_from_db()
    cfg = siteconfig.normalize(tenant.site_config)

    heroes = cfg["heroes"]
    assert len(heroes) == 2 and heroes[0]["title"] == "Die wunderbare Welt des Tees"
    assert heroes[0]["button_url"] == "/sortiment/"
    order = [s["key"] for s in cfg["sections"] if s.get("enabled")][:4]
    assert order == ["hero", "categories", "products", "about"]
    assert Category.objects.get(slug="schwarzertee").images
    items = cfg["menus"]["top"]["items"]
    assert [(i["label"], i["type"], i["target"]) for i in items] == [
        ("Schwarzer", "categories", "schwarzertee"),
        ("Grüner", "categories", "grunertee"),
        ("Neu", "url", "/sortiment/?sort=newest"),
    ]
    info = cfg["page_blocks"]["info"]
    assert info[0]["data"]["title"] == "Versand"
    assert "wie folgt" not in info[0]["data"]["body"]
    assert tenant.logo_url and tenant.primary_color == "#28328c"
    assert tenant.address == "Marktpassage 2, 42781 Haan" and tenant.contact_phone == "02129 54862"
    assert tenant.opening_hours_structured["5"] == ["10:00", "14:00"]
    assert any("brand color" in n for n in notes)

    # Владелец поменял слайд и цвет — повторный прогон их не трогает и не дублирует блоки.
    cfg_raw = dict(tenant.site_config)
    cfg_raw["heroes"] = [{"image": "/own.jpg", "title": "Eigener"}]
    tenant.site_config, tenant.primary_color = cfg_raw, "#123456"
    tenant.save(update_fields=["site_config", "primary_color"])
    cscart.apply_design(tenant, site, options=options, fetch_image=fetch_image)
    tenant.refresh_from_db()
    cfg = siteconfig.normalize(tenant.site_config)
    assert cfg["heroes"][0]["title"] == "Eigener" and tenant.primary_color == "#123456"
    assert len(cfg["page_blocks"]["info"]) == 1


def test_save_image_crop_keeps_middle_band(monkeypatch):
    saved = {}

    def fake_save(upload, **kw):
        with Image.open(upload) as img:
            saved["size"] = img.size
        return {"url": "/x.webp"}

    monkeypatch.setattr("apps.catalog.images.save_product_image", fake_save)
    buf = io.BytesIO()
    Image.new("RGB", (90, 125), (10, 120, 40)).save(buf, "JPEG")
    assert cscart._save_image("u", lambda _u: _Got(buf.getvalue()), crop=(0.3, 0.72))
    assert saved["size"] == (90, 53)  # 37..90 px
