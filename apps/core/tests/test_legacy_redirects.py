"""M21.1: переадресации старых адресов после переезда (план m21-cscart-migration)."""

from types import SimpleNamespace

import pytest
from django.http import HttpResponse, HttpResponseNotFound
from django.test import RequestFactory

from apps.core import legacy_redirects as lr
from apps.core.middleware import LegacyRedirectMiddleware
from apps.core.models import LegacyRedirect

pytestmark = pytest.mark.django_db
rf = RequestFactory()


def _call(path, *, status=404, schema="haanerteeladen", method="get"):
    request = getattr(rf, method)(path)
    request.tenant = SimpleNamespace(schema_name=schema)
    inner = HttpResponseNotFound("nf") if status == 404 else HttpResponse("ok", status=status)
    return LegacyRedirectMiddleware(lambda r: inner)(request)


def test_normalize_and_parse_source():
    assert lr.normalize_path("/Fruchtetee/Apfeltees/") == "/fruchtetee/apfeltees"
    assert lr.normalize_path("/") == "/"
    assert lr.normalize_path("/gr%C3%BCner-tee/") == "/grüner-tee"
    assert lr.parse_source("https://haanerteeladen.de/x/?b=2&a=1") == ("/x", "a=1&b=2")
    for bad in ("javascript:alert(1)", "http://[", "//[x"):
        with pytest.raises(lr.RedirectError):
            lr.parse_source(bad)


@pytest.mark.parametrize(
    "bad", ["//evil.com/x", "https://evil.com/", "/\\evil.com", "x/y", "/a\tb", ""]
)
def test_target_must_be_local(bad):
    with pytest.raises(lr.RedirectError):
        lr.clean_target(bad)


def test_same_source_and_target_rejected():
    with pytest.raises(lr.RedirectError):
        lr.upsert("/sortiment/", "/sortiment/")


def test_match_prefers_most_specific_query_rule():
    lr.upsert("/index.php", "/")
    lr.upsert("/index.php?dispatch=products.view&product_id=800", "/sortiment/assam/assam-ctc/")
    got = lr.match("/index.php", "sl=de&product_id=800&dispatch=products.view")
    assert got.target == "/sortiment/assam/assam-ctc/"
    assert lr.match("/index.php", "dispatch=products.view&product_id=1").target == "/"
    assert lr.match("/nichts", "") is None


def test_upsert_is_idempotent():
    lr.upsert("/alt/", "/neu/")
    obj, created = lr.upsert("/ALT", "/neuer/")
    assert created is False and obj.target == "/neuer/"
    assert LegacyRedirect.objects.count() == 1


def test_middleware_redirects_only_on_404():
    lr.upsert("/schwarzertee/assam/", "/sortiment/assam/")
    resp = _call("/schwarzertee/assam/?variation_id=806")
    assert resp.status_code == 301 and resp["Location"] == "/sortiment/assam/"
    assert LegacyRedirect.objects.get().hits == 1
    assert _call("/schwarzertee/assam/", status=200).status_code == 200


def test_middleware_gone_keeps_page_with_410():
    lr.upsert("/blog/", status=LegacyRedirect.STATUS_GONE)
    resp = _call("/blog")
    assert resp.status_code == 410 and resp.content == b"nf"


def test_middleware_ignores_public_schema_and_post():
    lr.upsert("/alt/", "/neu/")
    assert _call("/alt/", schema="public").status_code == 404
    assert _call("/alt/", method="post").status_code == 404


def test_middleware_fail_open_on_db_error(monkeypatch):
    from django.db import DatabaseError

    def boom(*a, **k):
        raise DatabaseError("no table")

    monkeypatch.setattr(lr, "match", boom)
    assert _call("/alt/").status_code == 404


def test_csv_import_and_export_roundtrip():
    raw = (
        b"alte_adresse;neue_adresse;status\n"
        b"/a/;/b/;\n"
        b"https://haanerteeladen.de/blog/x/;;410\n"
        b"/c/;//evil.com/;301\n"
    )
    result = lr.import_csv(raw)
    assert result.created == 2 and len(result.errors) == 1
    assert LegacyRedirect.objects.get(source_path="/blog/x").status == 410
    lr.upsert("/=cmd", "/-x/")
    body = lr.export_csv(LegacyRedirect.objects.all())
    assert "'/-x/" not in body  # пути начинаются с «/», нейтрализация не нужна
    assert "/a;/b/;301;0" in body


def test_csv_formula_cells_neutralized():
    assert lr._safe_cell("=HYPERLINK()") == "'=HYPERLINK()"
    assert lr._safe_cell("/ok/") == "/ok/"
