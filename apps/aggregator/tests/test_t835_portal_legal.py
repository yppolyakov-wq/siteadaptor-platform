"""T-8.35: «Rechtliches» городского портала (план docs/t8-35-portal-legal-plan-2026-11-17.md).

Замки: свои страницы портала (не B2B-тексты платформы); без полных реквизитов или вычитки —
«Entwurf»; реквизиты экранируются; у каждого процесса ПД портала — раздел Datenschutz;
внешние хосты CSP названы в получателях; подвал, формы, llms.txt ведут на страницы портала.
"""

import datetime

import pytest
from django.conf import settings as dj_settings

from apps.aggregator import legal_views, portal_operator
from apps.aggregator.models import PortalOperator
from apps.aggregator.tests.test_follow import _portal, _req

pytestmark = pytest.mark.django_db

FULL = {
    "name": "Stadtportal Solingen UG (haftungsbeschränkt)",
    "legal_form": "UG",
    "representative": "Erika Muster",
    "street": "Hauptstr. 1",
    "zip_city": "42651 Solingen",
    "email": "kontakt@portal.test",
    "phone": "+49 212 000000",
}


@pytest.fixture(autouse=True)
def _urlconf(settings):
    settings.ROOT_URLCONF = "config.urls_portal"


def _page(portal, page):
    return legal_views.legal_page(_req("get", "/", portal=portal), page=page).content.decode()


@pytest.mark.parametrize("page", sorted(legal_views.PAGES))
def test_pages_render_noindex_with_draft_banner_without_operator(page):
    html = _page(_portal(), page)
    assert f'data-legal-page="{page}"' in html
    assert 'name="robots" content="noindex' in html
    assert "data-legal-draft" in html and "Name / Firma" in html
    assert "[Name" not in html and "[Platzhalter" not in html


def test_banner_stays_until_reviewed_then_goes():
    op = PortalOperator.objects.create(**FULL)
    portal = _portal(operator=op)
    html = _page(portal, "impressum")
    assert "data-legal-draft" in html and "rechtlich geprüft" in html
    assert "Erika Muster" in html and "42651 Solingen" in html
    op.reviewed_at = datetime.date(2026, 11, 17)
    op.save()
    portal.refresh_from_db()
    assert "data-legal-draft" not in _page(portal, "impressum")


def test_company_without_representative_is_incomplete():
    op = PortalOperator(**{**FULL, "representative": ""})
    assert "Vertretungsberechtigt" in portal_operator.missing(op)
    op.legal_form = "Einzelunternehmen"
    assert portal_operator.missing(op) == ()


def test_operator_data_is_escaped():
    op = PortalOperator.objects.create(**{**FULL, "name": "<script>alert(1)</script>"})
    html = _page(_portal(operator=op), "hub")
    assert "<script>alert(1)" not in html and "&lt;script&gt;" in html


def test_every_personal_data_process_has_a_privacy_section():
    html = _page(_portal(), "datenschutz")
    for anchor in (
        "ds-verantwortlich",
        "ds-hosting",
        "ds-cookies",
        "ds-konto",  # PortalUser, FavoriteListing
        "ds-folgen",  # FollowSubscription (DOI)
        "ds-bewertungen",  # BusinessReview
        "ds-meldungen",  # ListingReport
        "ds-telegram",  # бот портала
        "ds-empfaenger",
        "ds-rechte",
    ):
        assert f'id="{anchor}"' in html, anchor
    assert "Art. 77" in html and "Double-Opt-In" in html


def test_external_hosts_of_csp_are_named_as_recipients():
    import re

    csp = " ".join(
        str(v) for k, v in vars(dj_settings).items() if "CSP" in k or "SECURITY_HEADERS" in k
    )
    hosts = {h.split(".")[-2] for h in re.findall(r"https://\*?\.?([a-z0-9.-]+\.[a-z]+)", csp)}
    html = _page(_portal(), "datenschutz").lower()
    for host in hosts:
        assert host in html, f"внешний хост CSP «{host}» не назван в Datenschutz"


def test_footer_and_follow_forms_link_portal_pages_not_platform_terms():
    from apps.aggregator import portal_views

    html = portal_views.portal_home(_req("get", "/", portal=_portal())).content.decode()
    legal = html[html.index('id="foot-legal"') :]
    assert 'href="/impressum/"' in legal and 'href="/datenschutz/"' in legal
    assert 'href="/nutzungsbedingungen/"' in legal and 'href="/rechtliches/"' in legal
    assert "siteadaptor" not in legal.split("</nav>")[0].replace("· siteadaptor", "")
    from apps.aggregator import follow_views

    req = _req("get", "/folgen/auswahl/", portal=_portal())
    assert 'href="/datenschutz/"' in follow_views.follow_center_view(req).content.decode()


def test_llms_and_feed_point_to_portal_pages():
    from apps.aggregator import llms

    portal = _portal()
    text = llms.build_portal(_req("get", "/llms.txt", portal=portal), portal)
    assert "/impressum/" in text and "siteadaptor.de/impressum" not in text
