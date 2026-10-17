"""T-8.27d: визитка «Nur Eintrag» — листинги каталога города ведут на сайт владельца."""

from decimal import Decimal
from unittest import mock

import pytest

from apps.aggregator import tasks
from apps.aggregator.models import AggregatorListing
from apps.catalog.models import Product
from apps.core import storefront_profile
from apps.tenants.models import Tenant

pytestmark = pytest.mark.django_db
SITE = "https://laden.example"


@pytest.fixture
def tenant(db):
    from apps.imports.tests.site_fakes import verified_run
    from apps.tenants.tests.factories import TenantFactory

    verified_run("laden.example")
    return TenantFactory(
        schema_name="public",
        slug="laden",
        website_url=SITE + "/",
        site_config={"profile": "eintrag"},
        in_city_catalog=True,
        email_pending=False,
    )


def _product(external_url=""):
    return Product.objects.create(
        name={"de": "Brot"},
        base_price=Decimal("3.10"),
        external_url=external_url,
        images=[{"url": "/media/brot.webp", "is_primary": True}],
    )


def _sync(product):
    with (
        mock.patch.object(tasks, "_withheld", return_value=False),
        mock.patch.object(tasks, "_image_ok", return_value=True),
    ):
        return tasks.sync_product_listing("public", product.pk)


def test_profiles_registry():
    assert storefront_profile.is_aktionen({"profile": "eintrag"})  # каталог скрыт
    assert storefront_profile.is_eintrag({"profile": "eintrag"})
    assert not storefront_profile.is_eintrag({"profile": "aktionen"})


def test_product_listing_kept_with_external_url(tenant):
    product = _product(SITE + "/p/brot")
    assert _sync(product) == "upserted"
    listing = AggregatorListing.objects.get(source_ref=str(product.pk))
    assert listing.detail_url == SITE + "/p/brot"


def test_www_variant_of_owner_site_accepted(tenant):
    product = _product("https://www.laden.example/p/brot")
    assert _sync(product) == "upserted"


def test_external_url_other_host_removed(tenant):
    product = _product("https://fremd.example/p/brot")
    assert _sync(product) == "removed"
    assert not AggregatorListing.objects.filter(source_ref=str(product.pk)).exists()


def test_http_external_url_rejected(tenant):
    product = _product("http://laden.example/p/brot")
    assert _sync(product) == "removed"


def test_eintrag_without_external_url_removed(tenant):
    assert _sync(_product("")) == "removed"


def test_aktionen_still_removes_products(tenant):
    Tenant.objects.filter(pk=tenant.pk).update(site_config={"profile": "aktionen"})
    assert _sync(_product(SITE + "/p/brot")) == "removed"


def test_with_channel_external_only_ch(settings):
    settings.TENANT_DOMAIN_BASE = "siteadaptor.de"
    listing = AggregatorListing(pk=7, detail_url=SITE + "/p/brot")
    with mock.patch("apps.tenants.hosts.known_hosts", return_value={"laden.siteadaptor.de"}):
        url = listing.with_channel("portal", lang="en", listing_ref=True)
    assert url == SITE + "/p/brot?ch=portal"


def test_with_channel_own_host_keeps_lang_and_listing(settings):
    settings.TENANT_DOMAIN_BASE = "siteadaptor.de"
    listing = AggregatorListing(pk=7, detail_url="https://laden.siteadaptor.de/sortiment/p/brot/")
    with mock.patch("apps.tenants.hosts.known_hosts", return_value={"laden.siteadaptor.de"}):
        url = listing.with_channel("portal", lang="en", listing_ref=True)
    assert "hl=en" in url and "cl=7" in url


def test_with_channel_custom_domain_is_ours(settings):
    settings.TENANT_DOMAIN_BASE = "siteadaptor.de"
    listing = AggregatorListing(pk=7, detail_url="https://baeckerei-krume.de/sortiment/")
    with mock.patch("apps.tenants.hosts.known_hosts", return_value={"baeckerei-krume.de"}):
        assert "cl=7" in listing.with_channel("portal", lang="", listing_ref=True)


def test_external_site_button_only_for_eintrag_https():
    from apps.core.business_card import external_site
    from apps.imports.tests.site_fakes import verified_run
    from apps.tenants.tests.factories import TenantFactory

    t = TenantFactory.build(
        schema_name="public", website_url=SITE, site_config={"profile": "eintrag"}
    )
    assert external_site(t) == ""  # сайт не подтверждён — кнопки нет (ревью Г1)
    verified_run("laden.example")
    t = TenantFactory.build(
        schema_name="public", website_url=SITE, site_config={"profile": "eintrag"}
    )
    assert external_site(t) == SITE
    t.website_url = "http://laden.example"
    assert external_site(t) == ""
    t.website_url, t.site_config = SITE, {}
    assert external_site(t) == ""
