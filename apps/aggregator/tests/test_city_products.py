"""T-8.11: товары, услуги и предприятия в каталоге города.

План — docs/t8-11-city-products-plan-2026-10-10.md §2.
"""

from decimal import Decimal

import pytest
from django.core.cache import cache
from django.test import RequestFactory, override_settings

from apps.aggregator import portal_views, tasks, views
from apps.aggregator.models import AggregatorListing, AggregatorPortal
from apps.booking.models import Service
from apps.catalog.models import Category, Product, ProductVariant
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db

PHOTO = [{"url": "/media/demo/jacke.webp", "is_primary": True}]


@pytest.fixture(autouse=True)
def _clear():
    cache.clear()
    yield
    cache.clear()


def _tenant(**kw):
    kw.setdefault("business_type", "clothing")
    return TenantFactory(
        schema_name="public", slug="walder", name="Walder Faden", city="Solingen", **kw
    )


def _product(**kw):
    kw.setdefault("name", {"de": "Winterjacke", "ru": "Зимняя куртка"})
    kw.setdefault("base_price", Decimal("89.00"))
    kw.setdefault("images", PHOTO)
    return Product.objects.create(**kw)


def _row(kind, ref):
    return AggregatorListing.objects.get(listing_kind=kind, source_ref=str(ref))


# --- товар ---------------------------------------------------------------------------


def test_product_with_photo_and_price_is_listed_with_mapped_category():
    _tenant()
    cat = Category.objects.create(name={"de": "Herbst"}, slug="herbst", city_category="damenmode")
    product = _product(category=cat, list_price=Decimal("120.00"), slug="winterjacke")
    assert tasks.sync_product_listing("public", product.pk) == "upserted"
    row = _row("product", product.pk)
    assert row.detail_url == "https://walder.siteadaptor.de/sortiment/herbst/winterjacke/"
    assert row.city_category == "damenmode"
    assert row.new_price == Decimal("89.00") and row.old_price == Decimal("120.00")
    assert row.discount_percent == 26
    assert row.title["ru"] == "Зимняя куртка"


@pytest.mark.parametrize(
    "kw",
    [
        {"images": []},
        {"base_price": Decimal("0")},
        {"is_active": False},
        {"hide_in_city": True},
    ],
)
def test_product_not_fit_for_display_is_not_listed(kw):
    _tenant()
    product = _product(**kw)
    assert tasks.sync_product_listing("public", product.pk) == "removed"
    assert not AggregatorListing.objects.filter(listing_kind="product").exists()


def test_hidden_parent_category_hides_whole_branch():
    _tenant()
    parent = Category.objects.create(name={"de": "Lager"}, slug="lager", hide_in_city=True)
    child = Category.objects.create(name={"de": "Reste"}, slug="reste", parent=parent)
    product = _product(category=child)
    assert tasks.sync_product_listing("public", product.pk) == "removed"


def test_soft_deleted_product_removes_listing():
    _tenant()
    product = _product()
    tasks.sync_product_listing("public", product.pk)
    product.delete()  # мягкое удаление (SoftDeleteMixin)
    assert tasks.sync_product_listing("public", product.pk) == "removed"


def test_availability_on_request_sold_out_and_untracked():
    _tenant()
    on_request = _product(primary_action="request")
    sold_out = _product(name={"de": "Schal"}, stock_quantity=0)
    plain = _product(name={"de": "Mütze"})
    for p in (on_request, sold_out, plain):
        tasks.sync_product_listing("public", p.pk)
    assert _row("product", on_request.pk).availability == "on_request"
    assert _row("product", sold_out.pk).availability == "sold_out"
    assert _row("product", plain.pk).availability == ""


def test_variants_give_from_price_and_new_badge():
    _tenant()
    product = _product(badge="neu")
    ProductVariant.objects.create(product=product, label="S", price=Decimal("79.00"))
    tasks.sync_product_listing("public", product.pk)
    row = _row("product", product.pk)
    assert row.new_price == Decimal("79.00") and row.is_new is True


def test_aktionen_profile_lists_no_products_but_the_business():
    _tenant(site_config={"profile": "aktionen"})
    product = _product()
    assert tasks.sync_product_listing("public", product.pk) == "removed"
    assert tasks.sync_business_listing("public") == "upserted"


def test_withheld_business_lists_nothing_new():
    _tenant(in_city_catalog=False)
    product = _product()
    assert tasks.sync_product_listing("public", product.pk) == "removed"
    assert tasks.sync_business_listing("public") == "removed"


# --- услуга и предприятие -------------------------------------------------------------


def test_service_listing_needs_booking_module():
    tenant = _tenant(business_type="friseur")
    service = Service.objects.create(name="Haarschnitt", duration_minutes=30, price_cents=3500)
    assert tasks.sync_service_listing("public", service.pk) == "upserted"
    row = _row("service", service.pk)
    assert row.new_price == Decimal("35.00")
    assert row.detail_url.endswith(f"/leistung/{service.pk}/")
    assert row.city_category == "friseur"
    tenant.disabled_modules = ["booking"]
    tenant.save()
    assert tasks.sync_service_listing("public", service.pk) == "removed"


def test_business_card_links_to_the_site_home():
    _tenant(site_config={"about_text": "Mode aus Solingen-Wald."})
    assert tasks.sync_business_listing("public") == "upserted"
    row = _row("business", "business")
    assert row.detail_url == "https://walder.siteadaptor.de/"
    assert row.teaser == {"de": "Mode aus Solingen-Wald."}


def test_reconcile_creates_and_cleans_new_kinds():
    _tenant()
    keep = _product()
    stale = AggregatorListing.objects.create(
        tenant_schema="public",
        tenant_slug="walder",
        business_name="Walder Faden",
        listing_kind="product",
        source_ref="00000000-0000-0000-0000-000000000000",
        title={"de": "Alt"},
        detail_url="https://walder.siteadaptor.de/x/",
    )
    tasks.reconcile_schema("public")
    refs = set(
        AggregatorListing.objects.filter(listing_kind="product").values_list(
            "source_ref", flat=True
        )
    )
    assert refs == {str(keep.pk)}
    assert not AggregatorListing.objects.filter(pk=stale.pk).exists()
    assert AggregatorListing.objects.filter(listing_kind="business").count() == 1


def test_product_save_queues_sync(django_capture_on_commit_callbacks, monkeypatch):
    calls = []
    monkeypatch.setattr(tasks.sync_aggregator_product, "delay", lambda **kw: calls.append(kw))
    with django_capture_on_commit_callbacks(execute=True):
        product = _product()
    assert calls and calls[-1]["product_id"] == str(product.pk)


# --- показ ---------------------------------------------------------------------------


def _listing(kind, title, **kw):
    return AggregatorListing.objects.create(
        tenant_schema="t1",
        tenant_slug="x",
        business_name="X",
        city="Solingen",
        listing_kind=kind,
        source_ref=title,
        title={"de": title},
        detail_url="https://x.siteadaptor.de/",
        **kw,
    )


@override_settings(ROOT_URLCONF="config.urls_portal")
def test_portal_feed_stays_offers_and_kind_chips_switch():
    portal = AggregatorPortal.objects.create(
        host="solingen.siteadaptor.de",
        kind="city",
        city="Solingen",
        title={"de": "Angebote in Solingen"},
        is_active=True,
    )
    _listing("promotion", "Herbstrabatt")
    _listing("product", "Winterjacke", availability="sold_out")
    # T-8.19: корень — главная с блоками; распроданное на главной не продвигаем,
    # лента предложений — вкладка «Angebote», переключение видов — вкладки.
    req = RequestFactory().get("/")
    req.portal = portal
    html = portal_views.portal_home(req).content.decode()
    assert "Herbstrabatt" in html and "Winterjacke" not in html
    assert 'data-portal-tab="product"' in html
    req = RequestFactory().get("/?kind=angebote")
    req.portal = portal
    html = portal_views.portal_home(req).content.decode()
    assert "Herbstrabatt" in html and "Winterjacke" not in html
    req = RequestFactory().get("/?kind=product")
    req.portal = portal
    html = portal_views.portal_home(req).content.decode()
    assert "Winterjacke" in html and "Herbstrabatt" not in html
    assert 'data-availability="sold_out"' in html


@pytest.mark.urls("config.urls_public")
def test_entdecken_search_finds_products():
    _listing("product", "Winterjacke")
    html = views.discover_index(RequestFactory().get("/entdecken/?q=winterjacke")).content.decode()
    assert "Winterjacke" in html and 'data-kind-badge="product"' in html


def test_business_own_category_beats_type_suggestion():
    _tenant(business_type="other", city_category="fitness")
    service = Service.objects.create(name="Yoga", duration_minutes=60, price_cents=1600)
    tasks.sync_service_listing("public", service.pk)
    tasks.sync_business_listing("public")
    assert _row("service", service.pk).city_category == "fitness"
    assert _row("business", "business").city_category == "fitness"


def test_settings_form_offers_city_category():
    from apps.tenants.forms import BusinessSettingsForm

    tenant = _tenant(business_type="other")
    field = BusinessSettingsForm(instance=tenant).fields["city_category"]
    assert field.choices[0][0] == "" and "Automatisch" in str(field.choices[0][1])


# --- T-8.26 S2: Category.is_active + пересинк при правке категории ---------------


def test_inactive_parent_category_hides_whole_branch():
    _tenant()
    parent = Category.objects.create(name={"de": "Archiv"}, slug="archiv", is_active=False)
    child = Category.objects.create(name={"de": "Alt"}, slug="alt", parent=parent)
    product = _product(category=child)
    assert tasks.sync_product_listing("public", product.pk) == "removed"


def _capture_category_reconcile(monkeypatch):
    calls = []
    monkeypatch.setattr(
        tasks.reconcile_city_catalog,
        "apply_async",
        lambda kwargs=None, countdown=None, **kw: calls.append((kwargs, countdown)),
    )
    return calls


def test_category_visibility_change_queues_one_reconcile_per_window(
    django_capture_on_commit_callbacks, monkeypatch
):
    _tenant()
    calls = _capture_category_reconcile(monkeypatch)
    with django_capture_on_commit_callbacks(execute=True):
        a = Category.objects.create(name={"de": "Jacken"}, slug="jacken")
        b = Category.objects.create(name={"de": "Hosen"}, slug="hosen")
    assert calls == []  # новая категория товаров не имеет — реконсилировать нечего
    with django_capture_on_commit_callbacks(execute=True):
        a.hide_in_city = True
        a.save()
        b.is_active = False
        b.save()
    assert len(calls) == 2
    kwargs, countdown = calls[0]
    assert kwargs["tenant_schema"] == "public" and kwargs["dedupe_key"].startswith(
        "agg-category-reconcile:public:"
    )
    # одно окно → один dedupe-ключ → idempotent_task выполнит ровно одну реконсиляцию,
    # и она стартует после закрытия окна (все правки уже закоммичены)
    assert calls[0][0]["dedupe_key"] == calls[1][0]["dedupe_key"]
    assert countdown == tasks._CATEGORY_RECONCILE_BUCKET


def test_category_cosmetic_save_does_not_queue_reconcile(
    django_capture_on_commit_callbacks, monkeypatch
):
    _tenant()
    category = Category.objects.create(name={"de": "Jacken"}, slug="jacken")
    calls = _capture_category_reconcile(monkeypatch)
    with django_capture_on_commit_callbacks(execute=True):
        category.sort_order = 5
        category.save(update_fields=["sort_order"])
    assert calls == []


def test_category_hard_delete_queues_reconcile_even_after_recent_save(
    django_capture_on_commit_callbacks, monkeypatch
):
    """Ревью: ключ от `updated_at` делал удаление дублем последнего сохранения."""
    _tenant()
    category = Category.objects.create(name={"de": "Jacken"}, slug="jacken")
    calls = _capture_category_reconcile(monkeypatch)
    with django_capture_on_commit_callbacks(execute=True):
        category.hide_in_city = True
        category.save()
        category.hard_delete()
    assert len(calls) == 2 and all(c[0]["tenant_schema"] == "public" for c in calls)


def test_reconcile_city_catalog_removes_branch_and_restores_it():
    _tenant()
    parent = Category.objects.create(name={"de": "Lager"}, slug="lager")
    product = _product(category=parent)
    assert tasks.sync_product_listing("public", product.pk) == "upserted"
    parent.is_active = False
    parent.save()
    tasks.reconcile_city_catalog(tenant_schema="public")
    assert not AggregatorListing.objects.filter(
        listing_kind="product", source_ref=str(product.pk)
    ).exists()
    parent.is_active = True
    parent.save()
    tasks.reconcile_city_catalog(tenant_schema="public")
    assert AggregatorListing.objects.filter(
        listing_kind="product", source_ref=str(product.pk)
    ).exists()


def test_settings_main_category_offers_only_types_sections():
    """Категории привязаны к типу бизнеса; сохранённая чужая — остаётся в списке."""
    from apps.tenants.forms import BusinessSettingsForm

    def keys(tenant):
        field = BusinessSettingsForm(instance=tenant).fields["city_category"]
        return {k for _g, items in field.choices[1:] for k, _l in items}

    bakery = _tenant(business_type="bakery")
    assert "brot-backwaren" in keys(bakery) and "schuhe" not in keys(bakery)
    bakery.city_category = "schuhe"
    assert "schuhe" in keys(bakery)
