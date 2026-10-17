"""T-8.27b: обход сайта — тот же сайт, лимиты, robots, sitemap, дедуп параметров."""

import pytest

from apps.imports.site import crawl
from apps.imports.tests.site_fakes import FakeSite, html

ROOT = "https://laden.example"


@pytest.fixture(autouse=True)
def _fast(settings):
    settings.SITE_IMPORT_PAUSE_S = 0
    settings.SITE_IMPORT_MAX_PAGES = 20
    settings.SITE_IMPORT_TIME_BUDGET_S = 120


def _links(*hrefs):
    return html(body="".join(f'<a href="{h}">x</a>' for h in hrefs))


def test_crawl_stays_on_same_host():
    site = FakeSite(
        {
            ROOT + "/": _links("/shop", "https://fremd.example/x", "https://www.laden.example/a"),
            ROOT + "/shop": html(body="shop"),
            "https://www.laden.example/a": html(body="a"),
        }
    )
    result = crawl.crawl(ROOT + "/", fetch=site)
    urls = [p.url for p in result.pages]
    assert "https://fremd.example/x" not in site.calls
    assert ROOT + "/shop" in urls and "https://www.laden.example/a" in urls


def test_crawl_caps_at_max_pages(settings):
    settings.SITE_IMPORT_MAX_PAGES = 3
    pages = {ROOT + "/": _links(*[f"/p{i}" for i in range(10)])}
    pages.update({f"{ROOT}/p{i}": html(body=str(i)) for i in range(10)})
    result = crawl.crawl(ROOT + "/", fetch=FakeSite(pages))
    assert len(result.pages) == 3


def test_robots_disallow_respected():
    site = FakeSite(
        {
            ROOT + "/robots.txt": (200, "text/plain", "User-agent: *\nDisallow: /privat"),
            ROOT + "/": _links("/privat/x", "/shop"),
            ROOT + "/shop": html(body="ok"),
            ROOT + "/privat/x": html(body="geheim"),
        }
    )
    result = crawl.crawl(ROOT + "/", fetch=site)
    assert ROOT + "/privat/x" not in site.calls
    assert any(e["status"] == "robots" for e in result.log)


def test_robots_blocking_start_marks_run():
    site = FakeSite({ROOT + "/robots.txt": (200, "text/plain", "User-agent: *\nDisallow: /")})
    result = crawl.crawl(ROOT + "/", fetch=site)
    assert result.robots_blocked and result.pages == []


def test_sitemap_urls_crawled_and_hinted_first(settings):
    settings.SITE_IMPORT_MAX_PAGES = 2
    sitemap = (
        '<?xml version="1.0"?><urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
        f"<url><loc>{ROOT}/ueber-uns</loc></url><url><loc>{ROOT}/produkt/brot</loc></url></urlset>"
    )
    site = FakeSite(
        {
            ROOT + "/sitemap.xml": (200, "application/xml", sitemap),
            ROOT + "/": html(body="start"),
            ROOT + "/produkt/brot": html(body="brot"),
            ROOT + "/ueber-uns": html(body="über"),
        }
    )
    result = crawl.crawl(ROOT + "/", fetch=site)
    assert [p.url for p in result.pages] == [ROOT + "/", ROOT + "/produkt/brot"]


def test_sitemap_with_doctype_rejected():
    with pytest.raises(ValueError):
        crawl.parse_sitemap(
            '<!DOCTYPE x [<!ENTITY a "aaa">]><urlset><url><loc>&a;</loc></url></urlset>'
        )


def test_time_budget_stops_crawl(settings):
    settings.SITE_IMPORT_TIME_BUDGET_S = 10
    ticks = iter([0, 0, 5, 11, 12, 13, 14, 15, 16])
    pages = {ROOT + "/": _links("/a", "/b", "/c")}
    pages.update({f"{ROOT}/{c}": html(body=c) for c in "abc"})
    result = crawl.crawl(ROOT + "/", fetch=FakeSite(pages), clock=lambda: next(ticks))
    assert len(result.pages) < 4
    assert any(e["status"] == "time_budget" for e in result.log)


def test_tracking_params_deduplicated():
    assert crawl.normalize(ROOT + "/shop?utm_source=x&id=3#top") == ROOT + "/shop?id=3"
    assert crawl.normalize("javascript:alert(1)") is None
    assert crawl.normalize("ftp://laden.example/") is None


def test_blocked_and_failed_pages_logged_not_fatal():
    site = FakeSite(
        {ROOT + "/": _links("/a", "/b"), ROOT + "/b": html(body="ok")},
        blocked={ROOT + "/a"},
    )
    result = crawl.crawl(ROOT + "/", fetch=site)
    assert [p.url for p in result.pages] == [ROOT + "/", ROOT + "/b"]
    assert {"url": ROOT + "/a", "status": "blocked"} in result.log


def test_offsite_redirect_dropped():
    from apps.core.ssrf import Fetched

    def fetch(url, **kw):
        if url == ROOT + "/":
            return Fetched("https://fremd.example/", 200, "text/html", b"<html></html>")
        return Fetched(url, 404, "text/html", b"")

    result = crawl.crawl(ROOT + "/", fetch=fetch)
    assert result.pages == []
