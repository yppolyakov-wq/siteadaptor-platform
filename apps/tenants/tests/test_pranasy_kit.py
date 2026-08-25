"""Pranasy — полноценная двуязычная демо-витрина (PR-D…H).

Restaurant (меню + «Bald geöffnet», покупка вкл.) и Shop (подкатегории) — две
отдельные сущности; ретриты (события), кетеринг (jobs), лояльность, «О нас».
Контент двуязычный (DE+EN): товары/категории/события + оверлей site_config.
"""

import pytest
from django.contrib.messages.middleware import MessageMiddleware
from django.contrib.sessions.middleware import SessionMiddleware
from django.test import RequestFactory
from django.utils import translation

from apps.catalog.models import Category, Product
from apps.events.models import Event
from apps.promotions import public_views
from apps.tenants import demo_kits, menu, siteconfig
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db


def _req(tenant, path="/"):
    request = RequestFactory().get(path)
    SessionMiddleware(lambda r: None).process_request(request)
    MessageMiddleware(lambda r: None).process_request(request)
    request.tenant = tenant
    return request


def _tenant():
    return TenantFactory(
        schema_name="public", slug="pranasy", name="Pranasy", business_type="restaurant"
    )


def test_pranasy_applies_full_bilingual_site():
    tenant = _tenant()
    assert demo_kits.apply_kit(tenant, "pranasy") is True

    # Restaurant — отдельная верхнеуровневая категория, 8 блюд, покупка включена.
    restaurant = Category.objects.get(slug="restaurant")
    assert restaurant.parent_id is None
    dishes = Product.objects.filter(category=restaurant)
    assert dishes.count() == 8
    assert all(p.is_active for p in dishes)  # «купить сразу» — товары активны

    # Shop — отдельная верхнеуровневая категория с тремя подкатегориями.
    shop = Category.objects.get(slug="shop")
    assert shop.parent_id is None
    subs = Category.objects.filter(parent=shop)
    assert subs.count() == 3
    by_slug = {c.slug: c for c in subs}
    assert Product.objects.filter(category=by_slug["wuerstchen"]).count() == 3
    assert Product.objects.filter(category=by_slug["aufschnitt"]).count() == 3
    assert Product.objects.filter(category=by_slug["suesses"]).count() == 6


def test_pranasy_products_are_bilingual():
    tenant = _tenant()
    demo_kits.apply_kit(tenant, "pranasy")
    # каждая категория и каждый товар несут DE и EN.
    cats = Category.objects.all()
    assert cats.exists()
    assert all(c.name.get("de") and c.name.get("en") for c in cats)
    prods = Product.objects.all()
    assert all(p.name.get("de") and p.name.get("en") for p in prods)


def test_pranasy_has_six_bilingual_retreats():
    tenant = _tenant()
    demo_kits.apply_kit(tenant, "pranasy")
    events = Event.objects.all()
    assert events.count() == 6
    # двуязычные заголовки: EN-локаль даёт английский title_text.
    sample = events.first()
    with translation.override("en"):
        assert sample.title_text == sample.title_i18n.get("en", sample.title)
    assert all(e.title_i18n.get("en") for e in events)


def test_pranasy_site_config_localizes():
    tenant = _tenant()
    demo_kits.apply_kit(tenant, "pranasy")
    cfg = tenant.site_config
    assert cfg["i18n"]["en"]  # оверлей переводов есть
    de = siteconfig.localize(cfg, "de")
    en = siteconfig.localize(cfg, "en")
    assert de["hero_title"] and en["hero_title"]
    assert "i18n" not in en  # служебный ключ не утекает
    # heroes-слайдер: «Bald geöffnet» для ресторана → EN отличается.
    assert de["heroes"] and en["heroes"]


def test_pranasy_menu_has_separate_restaurant_and_shop():
    tenant = _tenant()
    demo_kits.apply_kit(tenant, "pranasy")
    with translation.override("de"):
        top = menu.resolve_menu(tenant, "top")
    labels = [i["label"] for i in top]
    # Restaurant и Shop — отдельные пункты меню.
    assert "Restaurant" in labels
    assert "Shop" in labels
    # EN-локаль: «Über uns» → «About us».
    with translation.override("en"):
        top_en = menu.resolve_menu(tenant, "top")
    labels_en = [i["label"] for i in top_en]
    assert "About us" in labels_en


def test_pranasy_enables_modules_and_loyalty():
    tenant = _tenant()
    demo_kits.apply_kit(tenant, "pranasy")
    for mod in ("orders", "events", "jobs", "loyalty"):
        assert tenant.is_module_active(mod)


def test_pranasy_storefront_renders_de_and_en(settings):
    """Render-smoke: главная витрина pranasy отдаётся 200 на DE и EN без падений."""
    settings.ROOT_URLCONF = "config.urls_tenant"
    tenant = _tenant()
    demo_kits.apply_kit(tenant, "pranasy")
    with translation.override("de"):
        resp_de = public_views.storefront_home(_req(tenant))
    assert resp_de.status_code == 200
    body_de = resp_de.content.decode()
    assert "Bald geöffnet" in body_de  # hero-слайд ресторана
    with translation.override("en"):
        resp_en = public_views.storefront_home(_req(tenant))
    assert resp_en.status_code == 200
    # EN-локаль: оверлей перевёл hero-заголовок (отличается от DE).
    assert resp_en.content.decode() != body_de


# --- Catering-Bereich (Karte des Betreibers, 2026-08-25) ---------------------


def _catering_tenant():
    tenant = _tenant()
    demo_kits.apply_kit(tenant, "pranasy")
    return tenant


def test_pranasy_seeds_the_full_catering_menu():
    """49 Gerichte der PDF-Karte in sechs Gängen unter EINEM Bereich «Catering»."""
    _catering_tenant()
    catering = Category.objects.get(slug="catering")
    assert catering.parent_id is None
    assert catering.page_style == "sets"  # Menü-Pakete über dem Raster

    subs = {c.slug: c for c in Category.objects.filter(parent=catering)}
    assert set(subs) == {"suppen", "beilagen", "ragouts", "saucen", "vorspeisen", "salate"}

    dishes = Product.objects.filter(category__parent=catering)
    assert dishes.count() == 49
    # Bereich selbst trägt keine eigenen Produkte — er ist ein Container.
    assert not Product.objects.filter(category=catering).exists()
    # Jedes Gericht bringt Zutaten (LMIV) und einen Gang (Menü-Konfigurator).
    assert all(p.ingredients for p in dishes)
    assert all(p.course for p in dishes)
    # Ehrliche Kennzeichnung: Gerichte mit Sahne/Paneer/Joghurt sind vegetarisch,
    # nicht vegan (der Betrieb wirbt sonst falsch).
    borschtsch = dishes.get(name__de="Borschtsch")
    assert "vegan" not in borschtsch.diets and "vegetarisch" in borschtsch.diets
    assert "milch" in borschtsch.allergens


def test_pranasy_catering_menu_packages():
    """Drei Modi des Menü-Pakets wie beim Catering-Archetyp: fest, nach Wahl, frei."""
    from apps.catalog import combos as combos_mod
    from apps.catalog.models import Combo

    _catering_tenant()
    catering = Category.objects.get(slug="catering")
    sets = list(Combo.objects.filter(is_active=True).order_by("sort_order"))
    assert [c.name for c in sets] == [
        "Menü Klassik",
        "Menü nach Wahl",
        "Ayurveda-Thali",
        "Freie Auswahl",
    ]
    assert all(c.category_id == catering.pk and c.price_per_person for c in sets)
    assert all(c.min_persons >= 10 for c in sets)

    fixed, choice, thali, free = sets
    # Fest zusammengestellt: jede Gruppe «included», nichts zu wählen.
    assert [g.label for g in fixed.groups_active] == ["Suppe", "Hauptgang", "Beilage", "Salat"]
    assert all(g.included for g in fixed.groups_active)
    # Nach Wahl: Aufpreise stehen an den Optionen, nicht im Grundpreis.
    hauptgang = choice.groups.get(label="Hauptgang")
    assert hauptgang.min_select == 1 and hauptgang.max_select == 1
    assert hauptgang.options.count() == 4
    assert any(o.price_delta > 0 for o in hauptgang.options.all())
    assert all(not g.included for g in choice.groups_active)
    assert thali.groups_active and all(g.included for g in thali.groups_active)

    # Freie Auswahl: Pool = alle Gerichte der Unterkategorien (KAT-1-Semantik).
    assert free.free_pool is True
    pool = combos_mod.pool_products(free)
    assert len(pool) == 49
    assert {p.course for p in pool} == {"suppe", "beilage", "hauptgang", "vorspeise"}


def test_pranasy_catering_pages_render(settings):
    """Speisekarte und Menü-Pakete sind über die Storefront erreichbar."""
    from apps.orders import public_views as orders_views

    settings.ROOT_URLCONF = "config.urls_tenant"
    tenant = _catering_tenant()

    with translation.override("de"):
        page = public_views.product_list(_req(tenant, "/sortiment/catering/"), slug="catering")
    assert page.status_code == 200
    body = page.content.decode()
    assert "Menü Klassik" in body  # Set-Karten über dem Raster (page_style «sets»)
    assert "Suppen" in body and "Salate" in body  # Gänge als Unterkategorien
    # Der Container zeigt die Gerichte seiner Unterkategorien (KAT-1).
    assert "/sortiment/salate/sommersalat/" in body

    # Detailseite eines Gerichts: Zutaten und Kennzeichnung sind da.
    borschtsch = Product.objects.get(name__de="Borschtsch")
    with translation.override("de"):
        detail = public_views.product_detail(
            _req(tenant, borschtsch.get_absolute_url()),
            cslug=borschtsch.category.slug,
            pslug=borschtsch.slug,
        )
    assert detail.status_code == 200
    detail_body = detail.content.decode()
    assert "Rote Bete" in detail_body  # Zutatenliste aus der Karte

    with translation.override("de"):
        combos_page = orders_views.combo_list_public(_req(tenant, "/kombi/"))
    assert combos_page.status_code == 200
    assert "Freie Auswahl" in combos_page.content.decode()


def test_pranasy_catering_is_reachable_from_the_menu():
    """Der Bereich muss aus der Kopfzeile erreichbar sein — sonst findet ihn niemand."""
    tenant = _catering_tenant()
    with translation.override("de"):
        top = menu.resolve_menu(tenant, "top")
    catering = next(i for i in top if i["label"] == "Catering")
    children = {c["label"]: c["url"] for c in catering["children"]}
    assert set(children) == {"Speisekarte", "Menüs & Pakete", "Anfrage"}
    assert children["Speisekarte"].endswith("/sortiment/catering/")
    assert "/kombi/" in children["Menüs & Pakete"]


def test_pranasy_dishes_are_translated_into_every_demo_locale():
    """Klasse «Übersetzung liegt tot im Wörterbuch»: Name, Beschreibung und
    Zutaten jedes Gerichts müssen auf allen Demo-Locales ankommen."""
    _catering_tenant()
    missing = []
    for product in Product.objects.filter(category__parent__slug="catering"):
        for loc in ("en", "ru", "uk", "tr"):
            if not product.name.get(loc):
                missing.append((product.name["de"], loc, "name"))
            if not product.description.get(loc):
                missing.append((product.name["de"], loc, "description"))
            if not (product.ingredients_i18n or {}).get(loc):
                missing.append((product.name["de"], loc, "ingredients"))
    assert not missing, f"ohne Übersetzung: {missing[:12]} (insgesamt {len(missing)})"
