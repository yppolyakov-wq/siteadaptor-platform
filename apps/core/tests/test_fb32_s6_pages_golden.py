"""FB-32 S6a R0: характеризация «Über uns» и своей страницы ДО строк разделов. Без якорей
(строк разделов в `page_blocks`) страница обязана остаться байт-в-байт прежней — сверка с этими
снимками (`docs/fb32-unified-blocks-plan-2026-11-17.md`, S6).

Обновить (только осознанно): FB32S6_GOLDEN=update uv run pytest <этот файл>
"""

import os
import re
from pathlib import Path

import pytest

from apps.core.tests.test_fb31p5_detail_golden import _req

pytestmark = pytest.mark.django_db
GOLDEN = Path(__file__).parent / "golden_fb32s6"
UPDATE = os.environ.get("FB32S6_GOLDEN") == "update"

TEXT = {"key": "text", "id": "t-s6", "enabled": True, "data": {"title": "Anfahrt", "body": "Bus 5"}}
CASES = {
    "plain": {},
    "tail": {"page_blocks": {"info": [TEXT]}},
    "nocontact": {"about_contact": False, "page_blocks": {"info": [TEXT]}},
    "texts": {"about_title": "Wir", "about_text": "Seit 1990."},
}


@pytest.fixture(autouse=True)
def _urlconf(settings):
    settings.ROOT_URLCONF = "config.urls_tenant"


def _main(html: str) -> str:
    start = html.find("<main")
    end = html.find("</main>", start)
    body = html[start:end] if start != -1 else html
    body = re.sub(r'name="csrfmiddlewaretoken" value="[^"]+"', "", body)
    return re.sub(r"\n\s*\n+", "\n", body)


def _about(cfg):
    from apps.promotions import public_views

    req = _req("/ueber-uns/", cfg)
    req.tenant.address = "Hauptstr. 1, 42651 Solingen"  # иначе карточки контактов нет
    req.tenant.contact_phone = "+49 212 1234"
    return _main(public_views.about_page(req).content.decode())


def _page(cfg):
    from apps.core import content_page_views
    from apps.core.models import ContentPage

    ContentPage.objects.get_or_create(
        slug="anfahrt", defaults={"title": "Anfahrt", "body": "<p>Hier</p>"}
    )
    cfg = {**cfg, "page_blocks": {"seite:anfahrt": (cfg.get("page_blocks") or {}).get("info", [])}}
    req = _req("/anfahrt/", cfg)
    return _main(content_page_views.storefront_page(req, "anfahrt").content.decode())


def _check(name, got):
    path = GOLDEN / f"{name}.html"
    if UPDATE or not path.exists():
        if not UPDATE:
            pytest.fail(f"нет снимка {path.name}: FB32S6_GOLDEN=update")
        GOLDEN.mkdir(exist_ok=True)
        path.write_text(got)
        return
    assert got == path.read_text(), f"страница изменилась: {path.name}"


@pytest.mark.parametrize("case", sorted(CASES))
def test_about_page_without_anchors_looks_as_before(case):
    _check(f"about-{case}", _about(CASES[case]))


@pytest.mark.parametrize("case", ("plain", "tail"))
def test_content_page_without_anchors_looks_as_before(case):
    _check(f"page-{case}", _page(CASES[case]))


# ── S6b: «Versand» ──────────────────────────────────────────────────────────────


def _versand(cfg, *, body="", show=True):
    from apps.core.models import ContentPage
    from apps.orders import public_views
    from apps.orders.models import ShippingMethod

    ShippingMethod.objects.create(kind="pickup")
    ShippingMethod.objects.create(kind="carrier", carrier="dhl", fee_cents=499)
    if body:
        ContentPage.objects.create(
            slug="versand", title="Versand", body=body, show_shipping_methods=show
        )
    cfg = {**cfg, "page_blocks": {"versand": (cfg.get("page_blocks") or {}).get("info", [])}}
    return _main(public_views.shipping_info(_req("/versand/", cfg)).content.decode())


VERSAND = {
    "plain": ({}, "", True),
    "tail": (CASES["tail"], "", True),
    "body": (CASES["tail"], "<p>Wir liefern montags.</p>", True),
    "body-nolist": (CASES["tail"], "<p>Wir liefern montags.</p>", False),
}


@pytest.mark.parametrize("case", sorted(VERSAND))
def test_versand_page_without_anchors_looks_as_before(case):
    cfg, body, show = VERSAND[case]
    _check(f"versand-{case}", _versand(cfg, body=body, show=show))


# ── S6c: «Kontakt» и «Anfrage» ──────────────────────────────────────────────────


def _kontakt(cfg):
    from apps.inbox import public_views

    cfg = {**cfg, "page_blocks": {"message": (cfg.get("page_blocks") or {}).get("info", [])}}
    req = _req("/nachricht/", cfg)
    req.tenant.address = "Hauptstr. 1, 42651 Solingen"
    return _main(public_views.contact(req).content.decode())


def _anfrage(cfg):
    from apps.jobs import public_views

    cfg = {**cfg, "page_blocks": {"anfrage": (cfg.get("page_blocks") or {}).get("info", [])}}
    req = _req("/anfrage/", cfg)
    req.tenant.address = "Hauptstr. 1, 42651 Solingen"
    return _main(public_views.anfrage(req).content.decode())


@pytest.mark.parametrize("case", ("plain", "tail"))
def test_kontakt_and_anfrage_without_anchors_look_as_before(case):
    _check(f"kontakt-{case}", _kontakt(CASES[case]))
    _check(f"anfrage-{case}", _anfrage(CASES[case]))


# ── S6d: «Gutschein» и «Treue» ──────────────────────────────────────────────────


def _gift(cfg):
    from unittest import mock

    from apps.loyalty import public_views

    cfg = {**cfg, "page_blocks": {"gift": (cfg.get("page_blocks") or {}).get("info", [])}}
    with mock.patch.object(public_views, "gift_purchase_active", return_value=True):
        return _main(public_views.gutschein_index(_req("/gutschein/", cfg)).content.decode())


def _treue(cfg):
    from apps.loyalty.models import LoyaltyProgram
    from apps.promotions import public_views

    if not LoyaltyProgram.objects.exists():
        LoyaltyProgram.objects.create(
            label="Kaffeekarte", stamps_required=10, reward_label="1 Kaffee"
        )
    cfg = {**cfg, "page_blocks": {"loyalty": (cfg.get("page_blocks") or {}).get("info", [])}}
    return _main(public_views.loyalty_page(_req("/treue/", cfg)).content.decode())


@pytest.mark.parametrize("case", ("plain", "tail"))
def test_gift_and_loyalty_without_anchors_look_as_before(case):
    _check(f"gift-{case}", _gift(CASES[case]))
    _check(f"treue-{case}", _treue(CASES[case]))


# ── S6e: «Blogbeitrag» и «Finder» ───────────────────────────────────────────────


def _blog(cfg):
    from datetime import UTC, datetime

    from apps.events import public_views
    from apps.events.models import BlogPost

    when = datetime(2026, 5, 1, 9, 0, tzinfo=UTC)
    for i, slug in enumerate(("erster", "zweiter", "dritter")):
        BlogPost.objects.get_or_create(
            slug=slug,
            defaults={
                "title": f"Post {i}",
                "body": "Text",
                "is_published": True,
                "published_at": when,
            },
        )
    cfg = {**cfg, "page_blocks": {"blog_post": (cfg.get("page_blocks") or {}).get("info", [])}}
    return _main(public_views.blog_detail(_req("/blog/erster/", cfg), "erster").content.decode())


def _finder(cfg):
    from apps.promotions import public_views

    cfg = {
        **cfg,
        "finder": {"enabled": True},
        "page_blocks": {"finder": (cfg.get("page_blocks") or {}).get("info", [])},
    }
    req = _req("/finder/", cfg)
    req.tenant.business_type = "bakery"
    return _main(public_views.finder_page(req).content.decode())


@pytest.mark.parametrize("case", ("plain", "tail"))
def test_blog_and_finder_without_anchors_look_as_before(case):
    _check(f"blog-{case}", _blog(CASES[case]))
    _check(f"finder-{case}", _finder(CASES[case]))


# ── S6f: деталь акции ───────────────────────────────────────────────────────────


def _promo_detail(cfg, *, others=True, **kw):
    from apps.promotions.tests import test_fb31p3_promo_golden as p3

    promo = p3._promo("Brot der Woche", **kw)
    if others:
        p3._promo("Kuchen der Woche", days=5)
        p3._promo("Kaffee der Woche", days=6)
    rows = (cfg.get("page_blocks") or {}).get("info", [])
    cfg = {**cfg, "page_blocks": {"promo_detail": rows}}
    return p3._normalize(p3._detail(promo, cfg))  # pk/даты/время — как у снимков P3


PROMO = {
    "plain": ({}, True, {}),
    "alone": ({}, False, {}),
    "tail": (CASES["tail"], True, {}),
    "offer-style": (
        {"page_blocks": {"info": [{"key": "offer", "style": "plakat"}, TEXT]}},
        True,
        {},
    ),
    "own-style": (CASES["tail"], True, {"page_style": "kompakt"}),
}


@pytest.mark.parametrize("case", sorted(PROMO))
def test_promo_detail_without_anchors_looks_as_before(case):
    cfg, others, kw = PROMO[case]
    _check(f"promo-{case}", _promo_detail(cfg, others=others, **kw))


# ── S6g-1: «Lehrer», «Kalender», «Karten» ──────────────────────────────────────


def _stable(html):
    from apps.promotions.tests import test_fb31p3_promo_golden as p3

    return p3._normalize(html)  # pk/даты — как у снимков P3


def _rows_for(cfg, host):
    return {**cfg, "page_blocks": {host: (cfg.get("page_blocks") or {}).get("info", [])}}


def _lehrer(cfg):
    from apps.events import public_views
    from apps.events.models import Teacher

    Teacher.objects.get_or_create(
        name="Anna", defaults={"title": "Yogalehrerin", "is_active": True}
    )
    req = _req("/lehrer/", _rows_for(cfg, "teachers"))
    return _stable(public_views.lehrer_index(req).content.decode())


def _kalender(cfg):
    from apps.events import public_views

    req = _req("/veranstaltung/kalender/", _rows_for(cfg, "event_calendar"))
    return _stable(public_views.veranstaltung_calendar(req).content.decode())


def _karten(cfg):
    from apps.booking import public_views
    from apps.booking.models import PassPlan

    PassPlan.objects.get_or_create(
        label="10er-Karte", defaults={"credits": 10, "price_cents": 9000}
    )
    req = _req("/karten/", _rows_for(cfg, "passes"))
    return _stable(public_views.karten(req).content.decode())


def test_lehrer_kalender_karten_without_blocks_look_as_before():
    _check("lehrer-plain", _lehrer({}))
    _check("kalender-plain", _kalender({}))
    _check("karten-plain", _karten({}))
