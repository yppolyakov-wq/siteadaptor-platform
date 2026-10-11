"""T-8.25 «Основной адрес»: свой домен бизнеса — основной (план t8-23 §7.1)."""

from unittest import mock

import pytest
from django.contrib.auth.models import AnonymousUser
from django.core.cache import cache
from django.http import HttpResponse
from django.template import Context, Template
from django.test import RequestFactory, override_settings

from apps.tenants import hosts
from apps.tenants.middleware import PrimaryDomainRedirectMiddleware
from apps.tenants.models import CustomDomain, Domain
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _clean():
    cache.clear()
    yield
    cache.clear()


def _tenant(slug="baecker", custom=True):
    t = TenantFactory(schema_name=slug, slug=slug, name="Bäcker")
    if custom:
        CustomDomain.objects.create(
            domain="www.baecker-test.de", tenant=t, status=CustomDomain.ACTIVE
        )
        Domain.objects.create(domain="www.baecker-test.de", tenant=t, is_primary=False)
    return t


def _mw(tenant, path, host="baecker.siteadaptor.de", method="get", user=None, **extra):
    rf = RequestFactory()
    req = getattr(rf, method)(path, HTTP_HOST=host, **extra)
    req.tenant = tenant
    req.user = user or AnonymousUser()
    return PrimaryDomainRedirectMiddleware(lambda r: HttpResponse("ok"))(req)


@override_settings(TENANT_DOMAIN_BASE="siteadaptor.de", ALLOWED_HOSTS=["*"], DEBUG=False)
def test_storefront_on_subdomain_redirects_301_to_own_domain():
    t = _tenant()
    resp = _mw(t, "/aktionen/?gruppe=neu")
    assert resp.status_code == 301
    assert resp.url == "https://www.baecker-test.de/aktionen/?gruppe=neu"


@override_settings(TENANT_DOMAIN_BASE="siteadaptor.de", ALLOWED_HOSTS=["*"], DEBUG=False)
def test_no_redirect_for_cabinet_login_preview_post_owner_or_without_domain():
    t = _tenant()
    for path in ("/dashboard/", "/promotions/", "/accounts/login/", "/start/x/", "/static/a.css"):
        assert _mw(t, path).status_code == 200, path
    assert _mw(t, "/?preview=1").status_code == 200  # канва Studio — same-origin
    assert _mw(t, "/", method="post").status_code == 200
    owner = mock.Mock(is_authenticated=True)
    assert _mw(t, "/", user=owner).status_code == 200
    assert _mw(t, "/", host="www.baecker-test.de").status_code == 200  # уже на своём
    plain = _tenant("ohne", custom=False)
    assert _mw(plain, "/", host="ohne.siteadaptor.de").status_code == 200


@override_settings(TENANT_DOMAIN_BASE="siteadaptor.de", DEBUG=False)
def test_public_base_url_follows_domain_on_next_request():
    from apps.tenants.models import Tenant

    t = _tenant()
    assert hosts.public_base_url(t) == "https://www.baecker-test.de"
    Domain.objects.filter(domain="www.baecker-test.de").delete()
    CustomDomain.objects.filter(tenant=t).delete()
    fresh = Tenant.objects.get(pk=t.pk)  # следующий запрос — новый объект тенанта
    assert hosts.public_base_url(fresh) == "https://baecker.siteadaptor.de"


@override_settings(TENANT_DOMAIN_BASE="siteadaptor.de", DEBUG=False)
def test_city_listing_links_to_own_domain():
    from apps.aggregator import tasks

    t = _tenant()
    assert tasks._site(t) == "https://www.baecker-test.de"


@override_settings(TENANT_DOMAIN_BASE="siteadaptor.de", DEBUG=False)
def test_canonical_points_to_primary_address():
    t = _tenant()
    req = RequestFactory().get("/aktionen/?sort=neu", HTTP_HOST="baecker.siteadaptor.de")
    req.tenant = t
    html = Template("{% load seo %}{% canonical_link %}").render(Context({"request": req}))
    assert html == '<link rel="canonical" href="https://www.baecker-test.de/aktionen/">'


@override_settings(TENANT_DOMAIN_BASE="siteadaptor.de", DEBUG=False)
def test_footer_links_city_portal_only_for_listed_business():
    from apps.aggregator.models import AggregatorPortal

    t = _tenant()
    t.city = "Solingen"
    t.save()
    AggregatorPortal.objects.create(host="solingen.siteadaptor.de", city="Solingen")
    req = RequestFactory().get("/")
    req.tenant = t
    tpl = Template("{% load seo %}{% city_portal_link as cp %}{{ cp.url }}")
    assert tpl.render(Context({"request": req})) == "https://solingen.siteadaptor.de/"
    t.in_city_catalog = False
    t.save()
    assert tpl.render(Context({"request": req})) == ""
