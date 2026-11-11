"""M21.11 (решение владельца): своя страница по короткому адресу /zahlung/."""

import pytest
from django.urls import resolve, reverse

from apps.core import content_page_views as views
from apps.core import content_pages
from apps.core.models import ContentPage
from apps.core.tests.test_m21_10_text_pages_hub import _req

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _urlconf(settings):
    settings.ROOT_URLCONF = "config.urls_tenant"


def test_short_url_serves_the_page():
    ContentPage.objects.create(slug="zahlung", title="Zahlung", body="<p>x</p>", is_published=True)
    assert reverse("storefront-content-page", args=["zahlung"]) == "/zahlung/"
    assert resolve("/zahlung/").url_name == "storefront-content-page"
    resp = views.storefront_page(_req("/zahlung/"), "zahlung")
    assert resp.status_code == 200
    assert content_pages.content_url("zahlung") == "/zahlung/"


def test_short_route_is_last_and_never_shadows_storefront_routes():
    for path, name in (
        ("/sortiment/", "storefront-products"),
        ("/aktionen/", "storefront-aktionen"),
        ("/impressum/", "storefront-impressum"),
        ("/versand/", "storefront-shipping"),
        ("/ueber-uns/", "storefront-about"),
    ):
        assert resolve(path).url_name == name, path


def test_legacy_address_redirects_permanently():
    ContentPage.objects.create(slug="zahlung", title="Zahlung", is_published=True)
    resp = views.storefront_page_legacy(_req("/seite/zahlung/"), "zahlung")
    assert resp.status_code == 301 and resp["Location"] == "/zahlung/"


def test_shadowed_slug_keeps_working_under_seite():
    """Страница, созданная до коротких адресов с адресом системной (например «agb»),
    не теряется: её ссылка и страница остаются на /seite/agb/."""
    ContentPage.objects.create(slug="sortiment", title="Alt", body="<p>alt</p>", is_published=True)
    assert content_pages.content_url("sortiment") == "/seite/sortiment/"
    resp = views.storefront_page_legacy(_req("/seite/sortiment/"), "sortiment")
    assert resp.status_code == 200


def test_new_page_cannot_take_a_storefront_address():
    for slug in ("sortiment", "aktionen", "impressum", "warenkorb"):
        with pytest.raises(content_pages.PageError):
            content_pages.save_page(ContentPage(), title="X", slug=slug, body="", is_published=True)
    page = content_pages.save_page(
        ContentPage(), title="Zahlung", slug="zahlung", body="", is_published=True
    )
    assert page.slug == "zahlung"


def test_unknown_short_path_is_404():
    from django.http import Http404

    with pytest.raises(Http404):
        views.storefront_page(_req("/gibt-es-nicht/"), "gibt-es-nicht")
