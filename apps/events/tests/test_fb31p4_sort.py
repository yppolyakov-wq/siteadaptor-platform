"""FB-31 P4 R6: порядок туров, блога и отзывов — умолчание владельца (без ключа — как раньше);
туры — ★ «Abschnitte» (по странам / одним списком)."""

import pytest

from apps.events import public_views as ev
from apps.tenants import siteconfig

pytestmark = pytest.mark.django_db


class _Dep:
    def __init__(self, starts_at):
        self.starts_at = starts_at


class _Tour:
    def __init__(self, title, starts):
        self.title_text = title
        self._starts = starts

    def upcoming_departures(self):
        return [_Dep(s) for s in self._starts]


def test_tours_order_by_owner_choice():
    from datetime import timedelta

    from django.utils import timezone

    now = timezone.now()
    a = _Tour("Zeta", [now + timedelta(days=2)])
    b = _Tour("alpha", [])
    c = _Tour("Mitte", [now + timedelta(days=1)])
    tours = [a, b, c]
    assert ev._sort_tours(tours, "") == tours, "без ключа — порядок владельца"
    assert [t.title_text for t in ev._sort_tours(tours, "name")] == ["alpha", "Mitte", "Zeta"]
    assert [t.title_text for t in ev._sort_tours(tours, "next")] == ["Mitte", "Zeta", "alpha"]


def test_sorts_are_presence_minimal_and_whitelisted():
    cfg = siteconfig.normalize({"tours_sort": "name", "blog_sort": "evil", "reviews_sort": "best"})
    assert cfg["tours_sort"] == "name" and cfg["reviews_sort"] == "best"
    assert "blog_sort" not in cfg
    assert "tours_sort" not in siteconfig.normalize({})


def test_blog_oldest_first(rf):
    from django.contrib.sessions.middleware import SessionMiddleware

    from apps.events.models import BlogPost
    from apps.tenants.tests.factories import TenantFactory

    BlogPost.objects.create(title="Beitrag-Alt-Q", slug="alt", is_published=True)
    BlogPost.objects.create(title="Beitrag-Neu-Q", slug="neu", is_published=True)
    BlogPost.objects.filter(slug="alt").update(published_at="2020-01-01T00:00:00Z")
    BlogPost.objects.filter(slug="neu").update(published_at="2026-01-01T00:00:00Z")
    tenant = TenantFactory.build(site_config={"blog_sort": "oldest"}, enabled_modules=["events"])

    req = rf.get("/blog/")
    SessionMiddleware(lambda r: None).process_request(req)
    req.tenant = tenant
    html = ev.blog_index(req).content.decode()
    assert html.index("Beitrag-Alt-Q") < html.index("Beitrag-Neu-Q")


def test_tours_grouping_reads_the_star_field():
    from apps.core import listing_parts

    cfg = {"page_blocks": {"tours": [{"key": "main", "grouping": "ohne"}]}}
    assert listing_parts.effective(cfg, "tours").grouping == "ohne"
    got = siteconfig.normalize_page_blocks(cfg["page_blocks"])
    assert got["tours"] == [{"key": "main", "grouping": "ohne"}]
