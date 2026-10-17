"""T-8.27b: старт импорта (согласие, лимиты), выполнение прогона, экраны."""

from unittest import mock

import pytest
from django.test import RequestFactory
from django.urls import reverse

from apps.imports import views
from apps.imports.models import SiteImportItem, SiteImportRun
from apps.imports.site import service
from apps.imports.tests.site_fakes import FakeSite, html
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db
ROOT = "https://laden.example"


@pytest.fixture
def owner(django_user_model):
    return django_user_model.objects.create_user(username="inhaber", password="x")


def _post(user, data, tenant):
    request = RequestFactory().post("/imports/website/", data)
    request.user = user
    request.tenant = tenant
    return request


def test_consent_required_and_recorded(owner, settings):
    tenant = TenantFactory.build(schema_name="laden", website_url="")
    with mock.patch.object(service, "_enqueue"):
        resp = views.website_start(_post(owner, {"url": ROOT}, tenant))
        assert resp.status_code == 200 and SiteImportRun.objects.count() == 0
        with mock.patch.object(type(tenant), "save"):
            resp = views.website_start(_post(owner, {"url": ROOT, "consent": "1"}, tenant))
    run = SiteImportRun.objects.get()
    assert resp.status_code == 302
    assert run.consent_by_id == owner.pk and run.consent_version == service.CONSENT_VERSION
    assert run.consent_at is not None and run.host == "laden.example"
    assert tenant.website_url == ROOT + "/"


def test_daily_run_limit(owner, settings):
    settings.SITE_IMPORT_DAILY_RUNS = 2
    for _ in range(2):
        SiteImportRun.objects.create(
            start_url=ROOT,
            host="laden.example",
            consent_at="2026-10-17T10:00Z",
            consent_version="x",
            status=SiteImportRun.STATUS_READY,
        )
    with pytest.raises(service.StartError):
        service.start_run(user=owner, url=ROOT)


def test_one_active_run_only(owner):
    SiteImportRun.objects.create(
        start_url=ROOT, host="laden.example", consent_at="2026-10-17T10:00Z", consent_version="x"
    )
    with pytest.raises(service.StartError):
        service.start_run(user=owner, url=ROOT)


def test_invalid_url_rejected(owner):
    with pytest.raises(service.StartError):
        service.start_run(user=owner, url="javascript:alert(1)")


def test_execute_builds_draft_items(settings):
    settings.SITE_IMPORT_PAUSE_S = 0
    run = SiteImportRun.objects.create(
        start_url=ROOT + "/",
        host="laden.example",
        consent_at="2026-10-17T10:00Z",
        consent_version="x",
    )
    product = {"@type": "Product", "name": "Brot", "offers": {"price": "3.10"}}
    site = FakeSite({ROOT + "/": html(jsonld=[product], meta={"og:site_name": "Laden"})})
    service.execute(run, fetch=site)
    run.refresh_from_db()
    assert run.status == SiteImportRun.STATUS_READY and run.profile["name"] == "Laden"
    item = SiteImportItem.objects.get(run=run)
    assert item.data["name"] == "Brot" and len(item.fingerprint) == 64
    assert item.identity_key and item.ai_generated is False


def test_execute_robots_blocked_marks_failed(settings):
    run = SiteImportRun.objects.create(
        start_url=ROOT + "/",
        host="laden.example",
        consent_at="2026-10-17T10:00Z",
        consent_version="x",
    )
    site = FakeSite({ROOT + "/robots.txt": (200, "text/plain", "User-agent: *\nDisallow: /")})
    service.execute(run, fetch=site)
    run.refresh_from_db()
    assert run.status == SiteImportRun.STATUS_FAILED and run.error_code == "robots"


def test_task_marks_failed_on_crash(settings):
    from apps.imports.tasks import run_site_import

    run = SiteImportRun.objects.create(
        start_url=ROOT + "/",
        host="laden.example",
        consent_at="2026-10-17T10:00Z",
        consent_version="x",
    )
    with mock.patch.object(service, "execute", side_effect=RuntimeError("secret body")):
        run_site_import(schema_name="public", run_id=str(run.pk))
    run.refresh_from_db()
    assert run.status == SiteImportRun.STATUS_FAILED and run.error_code == "internal"


def test_views_require_login():
    for name, args in (
        ("imports:website", ()),
        ("imports:website-run", ("00000000-0000-0000-0000-000000000000",)),
    ):
        view = views.website_start if not args else views.website_run
        request = RequestFactory().get(reverse(name, args=args))
        from django.contrib.auth.models import AnonymousUser

        request.user = AnonymousUser()
        resp = view(request, *args) if args else view(request)
        assert resp.status_code == 302 and "login" in resp["Location"]


def test_website_paths_are_owner_only():
    from apps.core.middleware import CabinetOwnerAccessMiddleware

    assert reverse("imports:website").startswith(CabinetOwnerAccessMiddleware._OWNER_ONLY)


def test_review_post_applies_selected_items(owner):
    from apps.catalog.models import Product

    run = SiteImportRun.objects.create(
        start_url=ROOT + "/",
        host="laden.example",
        consent_at="2026-10-17T10:00Z",
        consent_version="x",
        status=SiteImportRun.STATUS_READY,
    )
    data = {
        "kind": "product",
        "name": "Brot",
        "price": "3.10",
        "identity": "url:x",
        "page_url": ROOT + "/p",
        "method": "structured",
    }
    item = SiteImportItem.objects.create(
        run=run, kind="product", data=data, fingerprint="f" * 64, identity_key="i" * 64
    )
    other = SiteImportItem.objects.create(
        run=run,
        kind="product",
        data={**data, "name": "Nein", "identity": "url:y"},
        fingerprint="g" * 64,
        identity_key="j" * 64,
    )
    tenant = TenantFactory.build(schema_name="laden", subscription_status="trial")
    request = _post(
        owner,
        {f"take_{item.pk}": "1", f"name_{item.pk}": "Brot hell", f"price_{item.pk}": "3,30"},
        tenant,
    )
    with (
        mock.patch.object(views, "messages"),
        mock.patch("apps.imports.site.apply._enqueue_images"),
    ):
        resp = views.website_run(request, run.pk)
    assert resp.status_code == 302
    product = Product.objects.get()
    assert product.name["de"] == "Brot hell" and str(product.base_price) == "3.30"
    other.refresh_from_db()
    assert other.decision == "skipped"


def test_review_get_renders_form_with_usage(owner):
    run = SiteImportRun.objects.create(
        start_url=ROOT + "/",
        host="laden.example",
        consent_at="2026-10-17T10:00Z",
        consent_version="x",
        status=SiteImportRun.STATUS_READY,
    )
    SiteImportItem.objects.create(
        run=run,
        kind="product",
        fingerprint="f" * 64,
        identity_key="i" * 64,
        data={"kind": "product", "name": "Honig", "price": None, "identity": "url:h"},
    )
    request = RequestFactory().get("/")
    request.user = owner
    request.tenant = TenantFactory.build(schema_name="laden", subscription_status="trial")
    html_out = views.website_run(request, run.pk).content.decode()
    assert "data-site-review" in html_out and "Honig" in html_out
    assert "data-site-usage" in html_out
