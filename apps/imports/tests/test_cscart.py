"""M21.2: перенос магазина CS-Cart — разбор, запись, переадресации."""

import io
import re
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

    # M21.4: меню — деревом, подписи дословно (как в оригинале), без пунктов без ссылки
    # («Menü» — переключатель телефона) и чужих хостов.
    def tree(nodes):
        return [(n["label"], n["url"].replace(BASE, "/"), tree(n["children"])) for n in nodes]

    assert tree(home.menu) == [
        (
            "SCHWARZER",
            "/schwarzertee/",
            [
                (
                    "Klassisch",
                    "/schwarzertee/klassisch",
                    [
                        ("Assam", "/klassisch/assam/", []),
                        ("Assam CTC", "/schwarzertee/klassisch/assam/assam-ctc/", []),
                    ],
                ),
                ("Aromatisch", "/schwarzertee/aromatisch/", []),
            ],
        ),
        ("GRÜNER", "/grunertee/aromatisch", []),
        ("Newest", "/index.php?dispatch=products.newest", []),
        ("Bestsellers", "/index.php?dispatch=products.bestsellers", []),
        ("Sales", "/index.php?dispatch=products.on_sale", []),
    ]
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

    def nodes(items):
        return [(i["label"], i["type"], i["target"], nodes(i["children"])) for i in items]

    product_url = Product.objects.get(sku="HT105").get_absolute_url()
    assert nodes(cfg["menus"]["top"]["items"]) == [
        (
            "SCHWARZER",
            "category",
            "schwarzertee",
            [
                (
                    "Klassisch",
                    "category",
                    "klassisch",
                    [
                        # битая ссылка оригинала (без /schwarzertee/) — по хвосту пути
                        ("Assam", "category", "assam", []),
                        ("Assam CTC", "url", product_url, []),
                    ],
                ),
                ("Aromatisch", "category", "aromatisch", []),
            ],
        ),
        # как в оригинале: пункт ведёт прямо в подкатегорию, без подъёма к разделу
        ("GRÜNER", "category", "grunertee-aromatisch", []),
        ("Neuheiten", "url", "/sortiment/?sort=newest", []),
        ("Bestseller", "url", "/sortiment/", []),
        ("Angebote", "archetype", "promotions", []),
    ]
    # порядок разделов каталога — по меню оригинала
    roots = list(Category.objects.filter(parent=None).order_by("sort_order"))
    assert [c.slug for c in roots] == ["schwarzertee", "grunertee"]
    kids = Category.objects.filter(parent__slug="schwarzertee").order_by("sort_order")
    assert [c.slug for c in kids] == ["klassisch", "aromatisch"]
    # M21.6: Versand — своя страница (раньше текстовый блок на «Über uns»).
    from apps.core.models import ContentPage

    assert "page_blocks" not in cfg or not cfg["page_blocks"].get("info")
    assert ContentPage.objects.get(slug="versand").title == "Versand"
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
    cfg_raw = dict(tenant.site_config)
    cfg_raw["menus"] = {
        "top": {"items": [{"label": "Eigenes", "type": "url", "target": "/x/"}], "sticky": False},
        "bottom": {"enabled": True, "items": [{"label": "Fuß", "type": "url", "target": "/y/"}]},
    }
    tenant.site_config = cfg_raw
    tenant.save(update_fields=["site_config"])
    cscart.apply_design(tenant, site, options=options, fetch_image=fetch_image)
    tenant.refresh_from_db()
    assert siteconfig.normalize(tenant.site_config)["menus"]["top"]["items"][0]["label"] == (
        "Eigenes"
    )
    options.replace_menu = True
    cscart.apply_design(tenant, site, options=options, fetch_image=fetch_image)
    tenant.refresh_from_db()
    top = siteconfig.normalize(tenant.site_config)["menus"]["top"]["items"]
    assert top[0]["label"] == "SCHWARZER"
    menus = siteconfig.normalize(tenant.site_config)["menus"]
    # нижнее меню и «липкость» шапки — владельца, replace_menu их не трогает
    assert menus["bottom"]["items"][0]["label"] == "Fuß" and menus["top"]["sticky"] is False
    assert ContentPage.objects.filter(slug="versand").count() == 1


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


IMPRESSUM = (
    "Einzelunternehmen Schweizer Irina\nLuhnstrasse 90,\n42277 Wuppertal\nTelefon: 02129 54862\n"
    "Mail: shop@haanerteeladen.de\nUmsatzsteuer-Identifikationsnummer(n): DE365326787\n"
    "Verantwortlich gemäß § 18 MStV: Schweizer Irina\nhttps://ec.europa.eu/consumers/odr/"
)


def test_parse_impressum_fields():
    assert cscart.parse_impressum(IMPRESSUM) == {
        "vat_id": "DE365326787",
        "contact_email": "shop@haanerteeladen.de",
        "legal_responsible": "Schweizer Irina",
        "legal_form": "einzel",
    }


@pytest.mark.django_db
def test_apply_legal_keeps_shop_address_and_own_texts():
    from apps.tenants.tests.factories import TenantFactory

    tenant = TenantFactory(schema_name="public", vat_id="", contact_email="", address="Haan")
    site = cscart.ScrapedSite(
        base=BASE, pages={"impressum": "<p>" + IMPRESSUM.replace("\n", "<br>")}
    )
    notes = cscart.apply_legal(tenant, site)
    tenant.refresh_from_db()
    assert tenant.vat_id == "DE365326787" and tenant.legal_form == "einzel"
    assert tenant.address == "Haan"  # адрес лавки не перезаписан юридическим
    assert "Wuppertal" in LegalDoc.objects.get(kind="impressum", locale="de").text
    assert any("ODR" in n for n in notes)
    LegalDoc.objects.filter(kind="impressum").update(text="Eigenes Impressum")
    cscart.apply_legal(tenant, site)
    assert LegalDoc.objects.get(kind="impressum").text == "Eigenes Impressum"


@pytest.mark.django_db
def test_command_create_requires_owner_data_and_creates(monkeypatch):
    from django.core.management import call_command
    from django.core.management.base import CommandError

    from apps.tenants import services
    from apps.tenants.tests.factories import TenantFactory

    with pytest.raises(CommandError):
        call_command("import_cscart", schema="haanerteeladen", url=BASE, create=True)

    monkeypatch.setattr(cscart, "scrape", lambda *a, **k: cscart.ScrapedSite(base=BASE))
    created = {}

    def fake_create(**kw):
        created.update(kw)
        return TenantFactory(schema_name="haanerteeladen", slug=kw["slug"]), "https://x/login/"

    monkeypatch.setattr(services, "create_business", fake_create)
    monkeypatch.setattr("apps.imports.cscart.apply_design", lambda *a, **k: [])
    monkeypatch.setattr(
        "apps.imports.management.commands.import_cscart.schema_context",
        lambda _s: __import__("contextlib").nullcontext(),
    )
    call_command(
        "import_cscart",
        schema="haanerteeladen",
        url=BASE,
        create=True,
        apply=True,
        name="Haaner Teeladen",
        owner_email="shop@haanerteeladen.de",
        city="Haan",
    )
    assert created["slug"] == "haanerteeladen" and created["business_type"] == "online_shop"
    assert created["email"] == "shop@haanerteeladen.de" and len(created["password"]) > 20
    from apps.tenants.models import Tenant

    shop = Tenant.objects.get(schema_name="haanerteeladen")
    assert shop.enabled_locales == ["de"] and shop.default_locale == "de"


@pytest.mark.django_db
def test_command_rerun_passes_replace_menu_and_locales(monkeypatch):
    from django.core.management import call_command
    from django.core.management.base import CommandError

    from apps.tenants.tests.factories import TenantFactory

    TenantFactory(schema_name="teeladen", enabled_locales=["de", "en"], default_locale="de")
    monkeypatch.setattr(cscart, "scrape", lambda *a, **k: cscart.ScrapedSite(base=BASE))
    seen = {}
    monkeypatch.setattr(
        "apps.imports.cscart.apply_design",
        lambda *a, **k: seen.update(options=k["options"]) or [],
    )
    monkeypatch.setattr(
        "apps.imports.management.commands.import_cscart.schema_context",
        lambda _s: __import__("contextlib").nullcontext(),
    )
    with pytest.raises(CommandError):
        call_command("import_cscart", schema="teeladen", url=BASE, locales="de,xx")
    call_command(
        "import_cscart", schema="teeladen", url=BASE, apply=True, replace_menu=True, locales="de"
    )
    from apps.tenants.models import Tenant

    shop = Tenant.objects.get(schema_name="teeladen")
    assert seen["options"].replace_menu is True
    assert shop.enabled_locales == ["de"]


@pytest.mark.django_db
def test_apply_locales_sets_only_german():
    from apps.tenants.tests.factories import TenantFactory

    tenant = TenantFactory(schema_name="public", enabled_locales=["de", "en"], default_locale="en")
    cscart.apply_locales(tenant, ["de"])
    tenant.refresh_from_db()
    assert tenant.enabled_locales == ["de"] and tenant.default_locale == "de"
    with pytest.raises(ValueError):
        cscart.apply_locales(tenant, ["xx"])


@pytest.mark.django_db
def test_cleanup_removes_demo_and_website_import_duplicates_only():
    """M21.5: дубли второго импортёра (Г1) и демо уходят; перенос CS-Cart и чужие
    категории целы; без apply — только список."""
    from django.utils import timezone

    from apps.catalog.models import Category, Product
    from apps.imports.models import SiteImportItem, SiteImportRun
    from apps.tenants import demo
    from apps.tenants.tests.factories import TenantFactory

    tenant = TenantFactory(schema_name="public")
    g1_cat = Category.objects.create(name={"de": "Schwarzer Tee"}, slug="schwarzer-tee")
    dup = Product.objects.create(name={"de": "Chai"}, base_price="6.50", category=g1_cat)
    moved_cat = Category.objects.create(name={"de": "Schwarzertee"}, slug="schwarzertee")
    moved = Product.objects.create(
        name={"de": "Assam"},
        base_price="7.60",
        category=moved_cat,
        metadata={"cscart": {"url": "https://x/assam/"}},
    )
    run = SiteImportRun.objects.create(
        start_url="https://x/", host="x", consent_at=timezone.now(), consent_version="1"
    )
    for target in (dup, moved):  # даже связанный с Г1 товар переноса не трогаем
        SiteImportItem.objects.create(
            run=run,
            kind="product",
            fingerprint="f",
            identity_key=str(target.pk),
            target_kind="product",
            target_id=str(target.pk),
        )
    demo.load_demo(tenant)
    tenant.refresh_from_db()
    assert demo.has_demo(tenant)

    notes = cscart.cleanup_foreign(tenant)
    assert "demo content: remove" in notes and "website-import duplicate: Chai" in notes
    assert Product.objects.filter(pk=dup.pk).exists()  # dry-run ничего не удаляет

    cscart.cleanup_foreign(tenant, apply=True)
    tenant.refresh_from_db()
    assert not demo.has_demo(tenant)
    assert not Product.objects.filter(pk=dup.pk).exists()
    assert not Category.objects.filter(pk=g1_cat.pk).exists()
    assert Product.objects.filter(pk=moved.pk).exists()
    assert Category.objects.filter(pk=moved_cat.pk).exists()


@pytest.mark.django_db
def test_export_codes_report_missing():
    from apps.catalog.models import Product, ProductVariant

    codes = cscart.read_export_codes(
        '﻿Product code;Language\n"HT1";"de"\n"HT1.1";"de"\n"HT2";"de"\n'
    )
    assert codes == {"HT1", "HT1.1", "HT2"}
    p = Product.objects.create(name={"de": "Assam"}, base_price="7.00", sku="HT1")
    ProductVariant.objects.create(product=p, label="100 g", price="7.00", sku="HT1.1")
    assert cscart.missing_codes(codes) == ["HT2"]
    full = cscart.read_export_codes('Product code;Status;Price\n"HT3";"A";"1"\n"HT4";"D";"1"\n')
    assert full == {"HT3"}  # выключенный в старом магазине — не «недостающий»


@pytest.mark.django_db
def test_cleanup_keeps_sold_and_edited_website_import_products():
    """Ревью безопасности M21.5: проданный или правленный после импорта товар Г1 —
    не «дубль», cleanup его оставляет и называет отдельно."""
    from datetime import timedelta

    from django.utils import timezone

    from apps.catalog.models import Product
    from apps.catalog.tests.test_product_reviews import _buy
    from apps.imports.models import SiteImportItem, SiteImportRun
    from apps.tenants.tests.factories import TenantFactory

    tenant = TenantFactory(schema_name="public")
    sold = Product.objects.create(name={"de": "Verkauft"}, base_price="5.00")
    edited = Product.objects.create(name={"de": "Bearbeitet"}, base_price="5.00")
    run = SiteImportRun.objects.create(
        start_url="https://x/", host="x", consent_at=timezone.now(), consent_version="1"
    )
    long_ago = timezone.now() - timedelta(days=3)
    for p in (sold, edited):
        SiteImportItem.objects.create(
            run=run,
            kind="product",
            fingerprint="f",
            identity_key=str(p.pk),
            target_kind="product",
            target_id=str(p.pk),
            applied_at=long_ago,
        )
    SiteImportItem.objects.create(
        run=run,
        kind="product",
        fingerprint="f",
        identity_key="x",
        target_kind="product",
        target_id="not-a-uuid",
    )
    _buy(sold, "kunde@example.com", ref="O-M215")
    Product.objects.filter(pk=sold.pk).update(updated_at=long_ago)

    notes = cscart.cleanup_foreign(tenant, apply=True)
    assert "kept (has orders): Verkauft" in notes
    assert "kept (edited after import): Bearbeitet" in notes
    assert Product.objects.filter(pk__in=[sold.pk, edited.pk]).count() == 2


IMPRESSUM_FULL = (
    "Einzelunternehmen Schweizer Irina\nLuhnstrasse 90,\n42277 Wuppertal\nDeutschland\n"
    "Telefon: 02129 54862\nMail: shop@haanerteeladen.de\nGeschäftsführer: Schweizer Irina\n"
    "Umsatzsteuer-Identifikationsnummer(n): DE365326787\n"
    "Verantwortlich gemäß § 18 MStV: Schweizer Irina\nÖko-Kontrollstelle \n"
    "Die Europäische Kommission stellt eine Plattform zur Online-Streitbeilegung (OS) bereit, "
    "die Sie hier finden https://ec.europa.eu/consumers/odr/. Wir sind bereit, an einem "
    "außergerichtlichen Schlichtungsverfahren vor einer Verbraucherschlichtungsstelle "
    "teilzunehmen. Zuständig ist die Universalschlichtungsstelle des Bundes."
)


def test_clean_impressum_removes_odr_and_fixes_terms():
    text, notes = cscart.clean_impressum(
        IMPRESSUM_FULL,
        oeko_code="DE-ÖKO-006",
        renames=(("Schweizer Irina", "Irina Schweizer"),),
    )
    assert "ec.europa.eu" not in text and "Online-Streitbeilegung" not in text
    assert text.startswith("Einzelunternehmen Irina Schweizer")
    assert "Inhaber: Irina Schweizer" in text and "Geschäftsführer" not in text
    assert "Öko-Kontrollstelle: DE-ÖKO-006" in text
    # Schlichtung bleibt — die Teilnahmeerklärung ist eine Entscheidung des Händlers.
    assert text.endswith("Universalschlichtungsstelle des Bundes.")
    assert "Wir sind bereit" in text
    assert cscart.impressum_gaps(text) == []
    assert len(notes) == 4


def test_clean_impressum_without_code_drops_empty_line_and_says_so():
    text, notes = cscart.clean_impressum(IMPRESSUM_FULL)
    assert "Öko-Kontrollstelle" not in text
    assert any("--oeko-code" in n for n in notes)
    assert cscart.clean_impressum(text)[1] == []  # идемпотентно


def test_impressum_gaps_names_missing_items():
    gaps = cscart.impressum_gaps("Muster GmbH\nMusterweg 1")
    assert {"e-mail address", "register court and number"} <= set(gaps)


@pytest.mark.django_db
def test_fix_impressum_command(monkeypatch):
    from django.core.management import call_command
    from django.core.management.base import CommandError

    from apps.tenants.tests.factories import TenantFactory

    TenantFactory(schema_name="teeladen")
    monkeypatch.setattr(
        "apps.imports.management.commands.fix_impressum.schema_context",
        lambda _s: __import__("contextlib").nullcontext(),
    )
    LegalDoc.objects.update_or_create(
        kind="impressum", locale="de", defaults={"text": IMPRESSUM_FULL}
    )
    with pytest.raises(CommandError):
        call_command("fix_impressum", schema="teeladen", oeko_code="DE-123")
    out = io.StringIO()
    call_command("fix_impressum", schema="teeladen", stdout=out)
    assert "dry-run" in out.getvalue()
    assert "odr" in LegalDoc.objects.get(kind="impressum").text
    call_command(
        "fix_impressum",
        schema="teeladen",
        apply=True,
        oeko_code="DE-ÖKO-006",
        rename=["Schweizer Irina=Irina Schweizer"],
        stdout=io.StringIO(),
    )
    saved = LegalDoc.objects.get(kind="impressum").text
    assert "odr" not in saved and "Inhaber: Irina Schweizer" in saved


@pytest.mark.django_db
def test_apply_pages_creates_own_pages_with_rehosted_images_and_moves_old_blocks():
    from apps.core.models import ContentPage

    versand = (
        '<div class="span8"><p><br></p><figure><img src="/images/DHL.png?1"></figure>'
        "<p>Wir versenden mit DHL.</p></div>"
    )
    site = cscart.ScrapedSite(
        base=BASE,
        pages={
            "versand": versand,
            "versand_title": "Versand",
            "zahlung": "<p>PayPal <b>oder</b> bar.</p>",
            "zahlung_title": "Zahlungsarten",
            "about": '<p><img src="https://evil.example/x.png"> Tee ist gut.</p>',
        },
    )
    old_block = {
        "key": "text",
        "enabled": True,
        "data": {"title": "Versand", "body": cscart.strip_dangling(cscart.html_to_text(versand))},
    }
    own_block = {"key": "text", "enabled": True, "data": {"title": "Eigen", "body": "Mein Text"}}
    config = {"page_blocks": {"info": [old_block, own_block]}}
    seen = []

    def fetch(url):
        seen.append(url)
        return _jpeg()

    notes = cscart.apply_pages(site, config, fetch_image=fetch)
    pages = {p.slug: p for p in ContentPage.objects.all()}
    assert set(pages) == {"versand", "zahlung", "ueber-uns"}
    assert "https://shop.example/images/DHL.png?1" in seen
    assert "<img" in pages["versand"].body and "shop.example" not in pages["versand"].body
    assert "<p><br></p>" not in pages["versand"].body
    assert pages["zahlung"].body == "<p>PayPal <b>oder</b> bar.</p>"
    assert pages["ueber-uns"].title == "Über uns" and "Tee ist gut." in pages["ueber-uns"].body
    bodies = [b["data"].get("body") for b in config["page_blocks"]["info"]]
    assert bodies == ["Mein Text"]  # блок M21.3 снят, блок владельца на месте
    assert any("page created" in n for n in notes)

    from apps.core.models import LegacyRedirect

    rule = LegacyRedirect.objects.get(source_path="/versand-de")
    assert rule.target == "/seite/zahlung/"

    # повтор не перезаписывает правку владельца
    ContentPage.objects.filter(slug="zahlung").update(body="<p>Eigene Zahlung</p>")
    cscart.apply_pages(site, {}, fetch_image=fetch)
    assert ContentPage.objects.get(slug="zahlung").body == "<p>Eigene Zahlung</p>"


def test_split_versand_link_replaces_only_untouched_link():
    menus = {
        "footer": {
            "columns": [
                {
                    "label": "Kundendienst",
                    "items": [
                        {"label": "Versand & Zahlung", "type": "page", "target": "about"},
                        {"label": "Kontakt", "type": "page", "target": "contact"},
                    ],
                }
            ]
        }
    }
    assert cscart._split_versand_link(menus) is True
    items = menus["footer"]["columns"][0]["items"]
    assert [(i["type"], i["target"]) for i in items] == [
        ("cpage", "versand"),
        ("cpage", "zahlung"),
        ("page", "contact"),
    ]
    assert cscart._split_versand_link(menus) is False


def _png_rgba():
    buf = io.BytesIO()
    Image.new("RGBA", (40, 20), (0, 0, 0, 0)).save(buf, "PNG")
    return _Got(buf.getvalue())


@pytest.mark.django_db
def test_page_html_keeps_layout_centering_and_transparency(settings, tmp_path):
    settings.MEDIA_ROOT = str(tmp_path)
    raw = (
        '<div class="span8"><p><img src="/images/a.png" width="380"></p><p>DHL</p></div>'
        '<div class="span8 text-center"><p style="text-align: center;">Abholung</p></div>'
        '<div class="row" onclick="x"><p class="evil">t</p></div>'
    )
    body = cscart.page_html(raw, BASE, lambda url: _png_rgba())
    assert body.startswith('<div class="sf-grid">')
    assert '<div class="sf-col-8">' in body and '<div class="sf-col-8 sf-center">' in body
    assert '<p class="sf-center">Abholung</p>' in body
    assert 'width="380"' in body
    assert "onclick" not in body and "evil" not in body and "row" not in body
    from django.core.files.storage import default_storage
    from PIL import Image as PILImage

    src = re.search(r'src="([^"]+)"', body).group(1)
    with default_storage.open(src.split("/media/", 1)[1]) as fh, PILImage.open(fh) as img:
        assert img.mode == "RGBA"  # прозрачный логотип не получает чёрный фон


@pytest.mark.django_db
def test_refresh_pages_rebuilds_untouched_and_keeps_edited():
    from apps.core.models import ContentPage

    site = cscart.ScrapedSite(base=BASE, pages={"zahlung": "<p>Neu</p>", "about": "<p>Neu</p>"})
    ContentPage.objects.create(slug="zahlung", title="Zahlungsarten", body="<p>Alt</p>")
    edited = ContentPage.objects.create(slug="ueber-uns", title="Über uns", body="<p>Eigen</p>")
    ContentPage.objects.filter(pk=edited.pk).update(
        created_at=edited.created_at - __import__("datetime").timedelta(days=1)
    )
    notes = cscart.apply_pages(site, {}, refresh=True)
    assert ContentPage.objects.get(slug="zahlung").body == "<p>Neu</p>"
    assert ContentPage.objects.get(slug="ueber-uns").body == "<p>Eigen</p>"
    assert any("kept (edited" in n for n in notes)
