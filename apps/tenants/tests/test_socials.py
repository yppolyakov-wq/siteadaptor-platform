"""GK-9: соцпрофили бизнеса — handle→URL, футер-иконки, sameAs (замок в test_seo)."""

import pytest
from django.template import Context, Template
from django.test import RequestFactory

from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db


def test_social_links_normalizes_handles_and_urls():
    t = TenantFactory.build(
        instagram="@meinladen",
        facebook="meincafe",
        linkedin="https://www.linkedin.com/company/firma",
        tiktok="",
        youtube="  ",
    )
    links = t.social_links()
    assert links == [
        ("instagram", "Instagram", "https://instagram.com/meinladen"),
        ("facebook", "Facebook", "https://facebook.com/meincafe"),
        ("linkedin", "LinkedIn", "https://www.linkedin.com/company/firma"),
    ]


def test_social_links_empty_tenant_gives_empty_list():
    assert TenantFactory.build().social_links() == []


def _render_footer(tenant):
    req = RequestFactory().get("/")
    req.tenant = tenant
    tpl = Template(
        '{% include "storefront/_social_icons.html" with links=request.tenant.social_links %}'
    )
    return tpl.render(Context({"request": req}))


def test_footer_partial_renders_icons_only_when_set():
    html = _render_footer(TenantFactory.build(instagram="laden"))
    assert 'aria-label="Instagram"' in html
    assert 'href="https://instagram.com/laden"' in html
    assert 'target="_blank"' in html and 'rel="noopener nofollow"' in html
    assert _render_footer(TenantFactory.build()).strip() == ""
