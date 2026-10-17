"""Ревью Г1 (django + security): владение сайтом, транспорт, обход, применение, профиль."""

import io
import ipaddress
import uuid
from datetime import timedelta
from decimal import Decimal
from unittest import mock

import pytest
from django.test import RequestFactory
from django.utils import timezone
from PIL import Image

from apps.aggregator import tasks as agg_tasks
from apps.catalog.models import Category, Product
from apps.core import ssrf
from apps.core.ssrf import Fetched, SsrfError
from apps.imports import views
from apps.imports.models import SiteImportItem, SiteImportRun
from apps.imports.site import apply, crawl, htmlparse, service, structured, verify
from apps.imports.tests.site_fakes import FakeSite, html, verified_run
from apps.tenants.tests.factories import TenantFactory

ROOT = "https://laden.example"


@pytest.fixture(autouse=True)
def _fast(settings):
    settings.SITE_IMPORT_PAUSE_S = 0
    settings.SITE_IMPORT_MAX_PAGES = 20
    settings.SITE_IMPORT_TIME_BUDGET_S = 120


@pytest.fixture
def owner(django_user_model, db):
    from apps.core.models import Membership

    user = django_user_model.objects.create_user(username="inhaber", password="x")
    Membership.objects.create(user=user, role=Membership.ROLE_OWNER)
    return user


def _run(**kw):
    kw.setdefault("status", SiteImportRun.STATUS_READY)
    return SiteImportRun.objects.create(
        start_url=ROOT + "/",
        host="laden.example",
        consent_at=timezone.now(),
        consent_version="x",
        **kw,
    )


def _item(run, name="Brot", price="4.90", **data):
    payload = {
        "kind": "product",
        "name": name,
        "price": price,
        "description": "",
        "image_url": "",
        "page_url": f"{ROOT}/p/{name}",
        "method": "structured",
        "identity": "url:" + name,
        **data,
    }
    return SiteImportItem.objects.create(
        run=run,
        kind="product",
        data=payload,
        source_url=payload["page_url"],
        fingerprint=service.fingerprint(payload),
        identity_key=service.identity_key(payload["identity"]),
    )


def _tenant(**kw):
    kw.setdefault("subscription_status", "trial")
    return TenantFactory.build(schema_name="laden", **kw)


def _all(run, **edits):
    return {str(i.pk): dict(edits) for i in run.items.all()}


def _apply(run, tenant=None, decisions=None):
    with mock.patch.object(apply, "_enqueue_images"):
        return apply.apply_items(run, tenant or _tenant(), decisions or _all(run))


# --- SSRF-транспорт ---------------------------------------------------------------------


@pytest.mark.parametrize(
    "raw,blocked",
    [
        ("100.64.0.1", True),  # CGNAT / метаданные некоторых облаков
        ("100.100.100.200", True),
        ("192.0.2.1", True),  # TEST-NET
        ("2002:0a00:0001::", True),  # 6to4 с 10.0.0.1 внутри
        ("::ffff:10.0.0.1", True),
        ("::ffff:93.184.216.34", False),
        ("93.184.216.34", False),
    ],
)
def test_non_global_addresses_blocked(raw, blocked):
    assert ssrf._is_blocked(ipaddress.ip_address(raw)) is blocked


def test_invalid_port_is_ssrf_error_not_value_error():
    with pytest.raises(SsrfError):
        ssrf.validate_public_url("http://laden.example:99999/")
    with pytest.raises(SsrfError):
        ssrf.safe_fetch("http://laden.example:99999/")


def test_peer_ip_with_scope_id_parsed():
    assert ssrf._ip("fe80::1%eth0") == ipaddress.ip_address("fe80::1")
    with pytest.raises(SsrfError):
        ssrf._ip("not-an-ip")


class _Resp:
    def __init__(self, status, headers=None, body=b""):
        self.status_code, self.headers, self.body, self.encoding = status, headers or {}, body, None

    def iter_content(self, chunk_size=8192):
        yield self.body

    def close(self):
        pass


class _Session:
    def __init__(self, responses):
        self.responses, self.calls = responses, []

    def get(self, url, **kw):
        self.calls.append((url, kw))
        return self.responses[url]

    def close(self):
        pass


@pytest.fixture
def public_dns(monkeypatch):
    monkeypatch.setattr(
        ssrf, "_resolve", lambda host, port: [(0, 0, 0, "", ("93.184.216.34", port))]
    )


def test_https_to_http_redirect_refused(public_dns):
    session = _Session({ROOT + "/": _Resp(302, {"Location": "http://laden.example/"})})
    with pytest.raises(SsrfError):
        ssrf.safe_fetch(ROOT + "/", session=session)


def test_deadline_caps_socket_timeout(public_dns):
    import time

    session = _Session({ROOT + "/": _Resp(200, {"Content-Type": "text/html"}, b"<html>")})
    ssrf.safe_fetch(ROOT + "/", session=session, deadline=time.monotonic() + 2)
    assert session.calls[0][1]["timeout"] <= 2
    with pytest.raises(SsrfError):
        ssrf.safe_fetch(ROOT + "/", session=session, deadline=time.monotonic() - 1)


# --- Обход ------------------------------------------------------------------------------


def test_normalize_drops_broken_port():
    assert crawl.normalize("http://laden.example:99999/x") is None


@pytest.mark.parametrize("status,blocked", [(401, True), (403, True), (503, True), (404, False)])
def test_robots_status_semantics(status, blocked):
    site = FakeSite({ROOT + "/robots.txt": (status, "text/plain", ""), ROOT + "/": html()})
    result = crawl.crawl(ROOT + "/", fetch=site)
    assert result.robots_blocked is blocked
    assert bool(result.pages) is not blocked


def test_redirect_target_checked_against_robots():
    def fetch(url, **kw):
        if url.endswith("/robots.txt"):
            return Fetched(url, 200, "text/plain", b"User-agent: *\nDisallow: /privat")
        if url == ROOT + "/":
            return Fetched(ROOT + "/privat/x", 200, "text/html", html().encode())
        return Fetched(url, 404, "text/html", b"")

    result = crawl.crawl(ROOT + "/", fetch=fetch)
    assert result.pages == []
    assert any(e["status"] == "robots" for e in result.log)


def test_crawl_delay_honored_but_capped():
    sleeps = []
    site = FakeSite(
        {
            ROOT + "/robots.txt": (200, "text/plain", "User-agent: *\nCrawl-delay: 60"),
            ROOT + "/": html(),
        }
    )
    crawl.crawl(ROOT + "/", fetch=site, sleep=sleeps.append)
    assert sleeps and max(sleeps) == crawl.CRAWL_DELAY_MAX


def test_fetch_gets_one_shared_deadline():
    seen = []

    def fetch(url, **kw):
        seen.append(kw.get("deadline"))
        return Fetched(url, 404, "text/plain", b"")

    crawl.crawl(ROOT + "/", fetch=fetch)
    assert seen and len(set(seen)) == 1 and seen[0] is not None


def test_partial_crawl_flagged_on_errors():
    site = FakeSite({ROOT + "/": html(body='<a href="/a">a</a>')}, blocked={ROOT + "/a"})
    assert crawl.crawl(ROOT + "/", fetch=site).partial is True
    assert crawl.crawl(ROOT + "/", fetch=FakeSite({ROOT + "/": html()})).partial is False


def test_links_per_page_capped():
    page = htmlparse.parse("".join(f'<a href="/p{i}">x</a>' for i in range(2000)), ROOT + "/")
    assert len(page.links) == htmlparse._MAX_LINKS


# --- Разбор -----------------------------------------------------------------------------


@pytest.mark.parametrize("raw", ["NaN", "Infinity", "-Infinity", "sNaN"])
def test_non_finite_price_rejected(raw):
    assert structured.price_of(raw) is None


def test_gtin_requires_ascii_digits():
    assert structured._gtin({"gtin13": "٤٠٠٦٣٨١٣٣٣٩٣١"}) == ""
    assert structured._gtin({"gtin13": "4006381333931"}) == "4006381333931"


def test_jsonld_item_url_offsite_falls_back_to_page():
    node = {"@type": "Product", "name": "Brot", "url": "https://fremd.example/p/brot"}
    item = structured._item(node, "product", ROOT + "/shop")
    assert item["page_url"] == ROOT + "/shop"
    node["url"] = "https://www.laden.example/p/brot"
    assert structured._item(node, "product", ROOT + "/shop")["page_url"] == node["url"]


# --- Подтверждение владения -------------------------------------------------------------


def test_token_deterministic_per_schema():
    assert verify.token("laden") == verify.token("laden")
    assert verify.token("laden") != verify.token("andere")
    assert verify.token("laden") in verify.meta_tag("laden")


def test_check_finds_meta_or_file():
    tag = verify.meta_tag("laden")
    assert (
        verify.check(
            ROOT + "/",
            schema="laden",
            fetch=FakeSite({ROOT + "/": html(meta={verify.META_NAME: verify.token("laden")})}),
        )
        == "meta"
    )
    files = FakeSite({ROOT + verify.FILE_PATH: (200, "text/plain", verify.token("laden") + "\n")})
    assert verify.check(ROOT + "/", schema="laden", fetch=files) == "file"
    wrong = FakeSite({ROOT + "/": html(meta={verify.META_NAME: "falsch"})})
    assert verify.check(ROOT + "/", schema="laden", fetch=wrong) == ""
    assert tag.startswith("<meta")


def test_check_ignores_token_on_other_host_after_redirect():
    def fetch(url, **kw):
        return Fetched(
            "https://fremd.example/",
            200,
            "text/html",
            html(meta={verify.META_NAME: verify.token("laden")}).encode(),
        )

    assert verify.check(ROOT + "/", schema="laden", fetch=fetch) == ""


@pytest.mark.django_db
def test_unverified_run_is_preview_only():
    site = FakeSite(
        {ROOT + "/": html(jsonld=[{"@type": "Product", "name": "Brot", "offers": {"price": "3"}}])}
    )
    run = _run(status=SiteImportRun.STATUS_QUEUED)
    service.execute(run, fetch=site)
    run.refresh_from_db()
    assert run.status == SiteImportRun.STATUS_READY and run.verified_at is None
    with pytest.raises(apply.ApplyError, match="unverified"):
        _apply(run)
    assert not Product.objects.exists()
    assert apply.apply_profile(run, _tenant(), ["phone"]) == []


@pytest.mark.django_db
def test_execute_verifies_and_adopts_website(settings):
    tenant = TenantFactory(schema_name="public", website_url="")
    token = verify.token()
    product = {"@type": "Product", "name": "Brot", "offers": {"price": "3"}}
    site = FakeSite({ROOT + "/": html(jsonld=[product], meta={verify.META_NAME: token})})
    run = _run(status=SiteImportRun.STATUS_QUEUED)
    service.execute(run, fetch=site)
    run.refresh_from_db()
    tenant.refresh_from_db()
    assert run.verified_at and run.verified_method == "meta"
    assert tenant.website_url == ROOT


@pytest.mark.django_db
def test_once_verified_same_site_reruns_need_no_token():
    verified_run()
    run = _run()
    assert verify.ensure(run, fetch=FakeSite({})) is True
    assert run.verified_method == "known"
    other = SiteImportRun.objects.create(
        start_url="https://fremd.example/", host="fremd.example", consent_at=timezone.now(),
        consent_version="x", status=SiteImportRun.STATUS_READY,
    )  # fmt: skip
    assert verify.ensure(other, fetch=FakeSite({})) is False


@pytest.mark.django_db
def test_run_page_shows_verify_block_not_review_form(owner):
    run = _run()
    _item(run)
    request = RequestFactory().get("/")
    request.user, request.tenant = owner, _tenant()
    body = views.website_run(request, run.pk).content.decode()
    assert "data-site-verify" in body and "data-site-review" not in body
    assert verify.token() in body


@pytest.mark.django_db
def test_verify_action_marks_run(owner):
    run = _run()
    request = RequestFactory().post("/", {"action": "verify"})
    request.user, request.tenant = owner, _tenant()
    with (
        mock.patch.object(verify, "check", return_value="file"),
        mock.patch.object(views, "messages"),
        mock.patch("apps.imports.site.service._adopt_website"),
    ):
        views.website_run(request, run.pk)
    run.refresh_from_db()
    assert run.verified_method == "file"


@pytest.mark.django_db
def test_staff_gets_403(django_user_model):
    from django.core.exceptions import PermissionDenied

    from apps.core.models import Membership

    staff = django_user_model.objects.create_user(username="mitarbeiter", password="x")
    Membership.objects.create(user=staff, role=Membership.ROLE_STAFF)
    request = RequestFactory().get("/")
    request.user, request.tenant = staff, _tenant()
    with pytest.raises(PermissionDenied):
        views.website_start(request)


# --- «Nur Eintrag» ----------------------------------------------------------------------


@pytest.mark.django_db
def test_eintrag_post_checked_on_server(owner):
    run = _run(status=SiteImportRun.STATUS_APPLIED)  # сайт не подтверждён
    tenant = _tenant(website_url=ROOT + "/", site_config={})
    request = RequestFactory().post("/", {"action": "eintrag"})
    request.user, request.tenant = owner, tenant
    with mock.patch.object(views, "messages"), mock.patch.object(type(tenant), "save") as save:
        views.website_run(request, run.pk)
    save.assert_not_called()
    assert "profile" not in tenant.site_config


@pytest.mark.django_db
def test_eintrag_website_must_match_verified_host(owner):
    verified_run("laden.example")
    run = _run(status=SiteImportRun.STATUS_APPLIED)
    assert views._can_eintrag(_tenant(website_url=ROOT + "/"), run)
    assert not views._can_eintrag(_tenant(website_url="https://evil.example/"), run)


@pytest.mark.django_db
def test_external_url_uses_verified_host_not_website_url():
    verified_run("laden.example")
    tenant = TenantFactory.build(schema_name="public", website_url="https://evil.example/")
    assert agg_tasks._external_url(tenant, "https://evil.example/p/x") == ""
    tenant = TenantFactory.build(schema_name="public", website_url="https://evil.example/")
    assert agg_tasks._external_url(tenant, ROOT + "/p/x") == ROOT + "/p/x"


@pytest.mark.django_db
def test_external_url_empty_without_any_verification():
    tenant = TenantFactory.build(schema_name="public", website_url=ROOT + "/")
    assert agg_tasks._external_url(tenant, ROOT + "/p/x") == ""


def test_platform_host_check_fail_closed(settings):
    from apps.aggregator.models import _is_platform_host

    settings.TENANT_DOMAIN_BASE = "siteadaptor.de"
    with mock.patch("apps.tenants.hosts.known_hosts", return_value=set()):
        assert _is_platform_host("laden.siteadaptor.de")
        assert not _is_platform_host("laden.example")


def test_lite_nav_has_import_for_eintrag_only():
    from apps.core import lite_cabinet

    names = lambda t: [i["url_name"] for i in lite_cabinet.sidebar_items(t)]  # noqa: E731
    assert "imports:website" in names({"profile": "eintrag"})
    assert "imports:website" not in names({"profile": "aktionen"})


# --- Старт прогона ----------------------------------------------------------------------


@pytest.mark.django_db
@pytest.mark.parametrize(
    "url", ["https://127.0.0.1/", "https://[::1]/", "https://laden.siteadaptor.de/"]
)
def test_start_rejects_ip_literals_and_platform_hosts(owner, settings, url):
    settings.TENANT_DOMAIN_BASE = "siteadaptor.de"
    with pytest.raises(service.StartError):
        service.start_run(user=owner, url=url)


@pytest.mark.django_db
def test_stale_run_reaped_on_start(owner):
    stale = _run(status=SiteImportRun.STATUS_CRAWLING)
    SiteImportRun.objects.filter(pk=stale.pk).update(updated_at=timezone.now() - timedelta(hours=1))
    with mock.patch.object(service, "_enqueue"):
        run = service.start_run(user=owner, url=ROOT)
    stale.refresh_from_db()
    assert stale.status == SiteImportRun.STATUS_FAILED and stale.error_code == "stale"
    assert run.status == SiteImportRun.STATUS_QUEUED


@pytest.mark.django_db
def test_fresh_active_run_still_blocks(owner):
    _run(status=SiteImportRun.STATUS_CRAWLING)
    with pytest.raises(service.StartError):
        service.start_run(user=owner, url=ROOT)


@pytest.mark.django_db
def test_enqueue_failure_marks_run_failed():
    run = _run(status=SiteImportRun.STATUS_QUEUED)
    with mock.patch("apps.imports.tasks.run_site_import.delay", side_effect=ConnectionError):
        service._enqueue("laden", run.pk)
    run.refresh_from_db()
    assert run.status == SiteImportRun.STATUS_FAILED and run.error_code == "queue"


@pytest.mark.django_db
def test_start_takes_advisory_lock(owner):
    with (
        mock.patch.object(service, "_lock_schema", wraps=service._lock_schema) as spy,
        mock.patch.object(service, "_enqueue"),
    ):
        service.start_run(user=owner, url=ROOT)
    spy.assert_called_once()


# --- Применение -------------------------------------------------------------------------


@pytest.mark.django_db
def test_existing_category_choice_applied():
    category = Category.objects.create(name={"de": "Brot"}, slug="brot")
    run = _run(verified_at=timezone.now())
    item = _item(run)
    _apply(run, decisions={str(item.pk): {"category": str(category.pk)}})
    assert Product.objects.get().category_id == category.pk
    assert apply._category(str(uuid.uuid4())) is None and apply._category("12") is None


@pytest.mark.django_db
def test_reimport_keeps_owner_edits():
    run = _run(verified_at=timezone.now())
    _item(run)
    _apply(run)
    product = Product.objects.get()
    product.is_active, product.list_price, product.badge = False, Decimal("9.90"), "sale"
    product.primary_action = "request"
    product.save()
    second = _run(verified_at=timezone.now())
    _item(second, price=None, description="neu")
    _apply(second)
    product.refresh_from_db()
    assert product.is_active is False and product.list_price == Decimal("9.90")
    assert product.badge == "sale" and product.primary_action == "request"
    assert product.base_price == Decimal("4.90")  # на сайте цены нет — не «0 €»


@pytest.mark.django_db
def test_deleted_target_returns_as_new_and_frees_limit(settings):
    settings.IMPORT_FREE_ITEMS = 1
    run = _run(verified_at=timezone.now())
    _item(run)
    _apply(run)
    Product.objects.get().delete()  # soft delete владельцем
    assert apply.used_count() == 0
    assert service.applied_state() == {}
    second = _run(verified_at=timezone.now())
    _item(second)
    result = _apply(second)
    assert result.created == 1 and Product.objects.count() == 1


@pytest.mark.django_db
def test_apply_twice_refused_and_stale_run_refused():
    run = _run(verified_at=timezone.now())
    _item(run)
    _apply(run)
    with pytest.raises(apply.ApplyError, match="not_ready"):
        _apply(run)
    older = _run(verified_at=timezone.now())
    SiteImportRun.objects.filter(pk=older.pk).update(created_at=run.created_at - timedelta(hours=1))
    older.refresh_from_db()
    _item(older, name="Alt")
    with pytest.raises(apply.ApplyError, match="stale"):
        _apply(older)


@pytest.mark.django_db
def test_over_limit_keeps_run_ready(settings):
    settings.IMPORT_FREE_ITEMS = 1
    run = _run(verified_at=timezone.now())
    _item(run, name="A")
    _item(run, name="B")
    result = _apply(run)
    run.refresh_from_db()
    assert result.over_limit == 1 and run.status == SiteImportRun.STATUS_READY


@pytest.mark.django_db
def test_failed_item_reported_by_name():
    run = _run(verified_at=timezone.now())
    _item(run, name="Kaputt")
    with mock.patch.object(apply, "_save_product", side_effect=RuntimeError):
        result = _apply(run)
    assert result.errors == ["Kaputt"]
    run.refresh_from_db()
    assert run.status == SiteImportRun.STATUS_READY


@pytest.mark.django_db
def test_partial_crawl_proposes_no_removals():
    verified_run()
    first = _run(status=SiteImportRun.STATUS_QUEUED)
    products = [
        {"@type": "Product", "name": n, "offers": {"price": "3"}} for n in ("Brot", "Honig")
    ]
    service.execute(first, fetch=FakeSite({ROOT + "/": html(jsonld=products)}))
    first.refresh_from_db()
    _apply(first)
    second = _run(status=SiteImportRun.STATUS_QUEUED)
    site = FakeSite(
        {ROOT + "/": html(jsonld=products[:1], body='<a href="/x">x</a>')}, blocked={ROOT + "/x"}
    )
    service.execute(second, fetch=site)
    assert not second.items.filter(diff=SiteImportItem.DIFF_REMOVED).exists()
    second.refresh_from_db()
    assert second.stats["partial"] is True


@pytest.mark.django_db
def test_duplicate_identities_collapsed_in_one_run():
    verified_run()
    run = _run(status=SiteImportRun.STATUS_QUEUED)
    dup = {"@type": "Product", "name": "Brot", "gtin13": "4006381333931", "offers": {"price": "3"}}
    pages = {
        ROOT + "/": html(jsonld=[dup], body='<a href="/b">b</a>'),
        ROOT + "/b": html(jsonld=[dup]),
    }
    with mock.patch("apps.imports.site.ai_extract.extract", return_value=([], "")):
        service.execute(run, fetch=FakeSite(pages))
    assert run.items.count() == 1


def _tiff():
    buf = io.BytesIO()
    Image.new("RGB", (10, 10), "red").save(buf, "TIFF")
    return buf.getvalue()


@pytest.mark.django_db
def test_image_formats_whitelisted():
    run = _run(verified_at=timezone.now())
    _item(run, image_url=ROOT + "/x.png")
    _apply(run)
    fetch = lambda url, **kw: Fetched(url, 200, "image/png", _tiff())  # noqa: E731 — тип врёт
    assert apply.fetch_images(run, fetch=fetch) == 0


def test_images_dedupe_key_unique_per_call():
    keys = []
    with mock.patch(
        "apps.imports.tasks.fetch_site_import_images.delay",
        side_effect=lambda **kw: keys.append(kw["dedupe_key"]),
    ):
        apply._enqueue_images("laden", "r1")
    assert keys[0].startswith("site-import-img:laden:r1:")


@pytest.mark.django_db
def test_profile_written_to_fresh_tenant_row():
    tenant = TenantFactory(schema_name="public", address="", site_config={"ui": "x"})
    run = _run(
        verified_at=timezone.now(), profile={"address": "Markt 1", "description": "<b>Hi</b>"}
    )
    stale = TenantFactory._meta.model.objects.get(pk=tenant.pk)
    TenantFactory._meta.model.objects.filter(pk=tenant.pk).update(site_config={"ui": "x", "neu": 1})
    apply.apply_profile(run, stale, ["address", "description"])
    tenant.refresh_from_db()
    assert tenant.address == "Markt 1"
    assert tenant.site_config["neu"] == 1 and tenant.site_config["about_text"] == "Hi"
