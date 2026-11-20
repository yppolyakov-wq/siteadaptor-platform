"""FB-33 M2b-2b C3: витрина — блок FAQ со своими вопросами объекта (`data.source=object`).

Замки: свои вопросы у всех пяти видов (общий хост детали и хост объекта); FAQPage — одна на
страницу и только из такого блока; у своих вопросов нет `data-edit` (канва пишет только общие);
пустой — ничего (в превью заглушка); экранирование; блок без `source` — прежний (снимки
`test_fb33_m2b2a_before`).
"""

import uuid
from datetime import timedelta

import pytest
from django.utils import timezone, translation

from apps.core.tests import test_fb31p5_detail_golden as _p5

pytestmark = pytest.mark.django_db
frozen_now = _p5.frozen_now
FAQPAGE = '"@type":"FAQPage"'
OWN = [
    {"q": "Wie lange dauert Balayage?", "a": "Je nach Haarlänge 2,5 bis 3,5 Stunden."},
    {"q": "Muss ich mit gewaschenen Haaren kommen?", "a": "Nein."},
]
SHARED = [{"q": "Wann haben Sie offen?", "a": "Mo–Fr 8–18 Uhr."}]


@pytest.fixture(autouse=True)
def _urlconf(settings, frozen_now):
    settings.ROOT_URLCONF = "config.urls_tenant"


def own_block(bid="faq-own", style=""):
    data = {"source": "object", **({"style": style} if style else {})}
    return {"key": "faq_ref", "id": bid, "data": data}


def create(kind, faq=OWN, i18n=None):
    if kind == "service":
        from apps.booking.models import Service

        return Service.objects.create(
            name="Balayage", duration_minutes=150, price_cents=12900, is_active=True, faq=faq,
            faq_i18n=i18n or {},
        )  # fmt: skip
    if kind == "product":
        from apps.catalog.tests.factories import ProductFactory

        return ProductFactory(name={"de": "Bauernbrot"}, faq=faq, faq_i18n=i18n or {})
    if kind == "stay":
        from apps.stays.models import StayUnit

        return StayUnit.objects.create(
            name="FeWo See", price_cents=9000, faq=faq, faq_i18n=i18n or {}
        )
    from apps.events.models import Event, Tour

    det = {"faq": faq}
    di18n = {loc: {"faq": v} for loc, v in (i18n or {}).items()}
    if kind == "event":
        return Event.objects.create(
            title="Konzert",
            starts_at=timezone.now() + timedelta(days=7),
            status=Event.STATUS_PUBLISHED,
            details=det,
            details_i18n=di18n,
        )
    tour = Tour.objects.create(
        title="Manali – Leh",
        slug=f"manali-{uuid.uuid4().hex[:6]}",
        is_published=True,
        details=det,
        details_i18n=di18n,
    )
    Event.objects.create(
        title="Juni-Tour",
        tour=tour,
        starts_at=timezone.now() + timedelta(days=30),
        status=Event.STATUS_PUBLISHED,
    )
    return tour


def render(kind, obj, cfg, query=""):
    from apps.booking import public_views as bv
    from apps.events import public_views as ev
    from apps.promotions import public_views as pv
    from apps.stays import public_views as sv

    req = _p5._req("/x/" + query, cfg)
    if kind == "service":
        resp = bv.service_detail(req, pk=obj.pk)
    elif kind == "product":
        resp = pv.product_detail(req, pk=obj.pk)
    elif kind == "stay":
        resp = sv.unterkunft_unit(req, pk=obj.pk)
    elif kind == "event":
        resp = ev.veranstaltung_detail(req, pk=obj.pk)
    else:
        resp = ev.tour_detail(req, slug=obj.slug)
    return resp.content.decode()


SHARED_HOST = {
    "service": "service_detail",
    "product": "product_detail",
    "stay": "stay_detail",
    "event": "event_detail",
    "tour": "event_detail",
}
KINDS = list(SHARED_HOST)


@pytest.mark.parametrize("kind", KINDS)
def test_own_questions_on_the_shared_detail_host(kind):
    obj = create(kind)
    cfg = {"faq": SHARED, "page_blocks": {SHARED_HOST[kind]: [own_block()]}}
    html = render(kind, obj, cfg)
    assert "Wie lange dauert Balayage?" in html and "data-faq-own" in html
    assert "Wann haben Sie offen?" not in html
    assert html.count(FAQPAGE) == 1


@pytest.mark.parametrize("kind", KINDS)
def test_own_questions_on_the_object_host(kind):
    obj = create(kind)
    cfg = {"page_blocks": {f"{kind}:{obj.pk.hex}": [own_block()]}}
    html = render(kind, obj, cfg)
    assert "Muss ich mit gewaschenen Haaren kommen?" in html and html.count(FAQPAGE) == 1


def test_foreign_object_host_shows_nothing():
    obj, other = create("service"), create("service", faq=[{"q": "Andere?", "a": "x"}])
    cfg = {"page_blocks": {f"service:{other.pk.hex}": [own_block()]}}
    assert "Andere?" not in render("service", obj, cfg)


def test_one_faqpage_per_page_and_only_from_the_block():
    obj = create("service")
    cfg = {
        "faq": SHARED,
        "page_blocks": {
            "service_detail": [
                own_block("a"),
                own_block("b", "list"),
                {"key": "faq_ref", "id": "c"},
            ],
        },
    }
    html = render("service", obj, cfg)
    assert html.count(FAQPAGE) == 1 and html.count("data-faq-own") == 2
    assert "Wann haben Sie offen?" in html  # общий блок рядом — без FAQPage, как был
    # старый раздел «faq» услуги — без FAQPage (как до среза)
    assert FAQPAGE not in render("service", create("service"), {})


@pytest.mark.parametrize("style", ["", "list", "twocol", "cards", "numbered"])
def test_own_questions_have_no_canvas_edit(style):
    obj = create("service")
    cfg = {"page_blocks": {"service_detail": [own_block(style=style)]}}
    html = render("service", obj, cfg)
    start = html.index("data-faq-own")
    section = html[start : html.index("</section>", start)]
    assert "Wie lange dauert Balayage?" in section and "data-edit" not in section


@pytest.mark.parametrize("kind", ["service", "product"])
def test_empty_own_questions_draw_nothing(kind):
    obj = create(kind, faq=[])
    cfg = {"page_blocks": {SHARED_HOST[kind]: [own_block()]}}
    html = render(kind, obj, cfg)
    assert 'data-sf-section="faq-own"' not in html and "data-faq-own" not in html
    assert f'data-pb-host="{SHARED_HOST[kind]}"' not in html
    assert FAQPAGE not in html


def test_questions_are_escaped():
    obj = create("service", faq=[{"q": "<script>alert(1)</script>?", "a": "<b>x</b>"}])
    cfg = {"page_blocks": {"service_detail": [own_block()]}}
    html = render("service", obj, cfg)
    assert "<script>alert(1)</script>" not in html and "&lt;script&gt;" in html
    assert "<b>x</b>" not in html


@pytest.mark.parametrize("kind", ["service", "event", "stay"])
def test_own_questions_are_translated(kind):
    obj = create(kind, i18n={"ru": [{"q": "Сколько длится?"}]})
    cfg = {"page_blocks": {SHARED_HOST[kind]: [own_block()]}}
    with translation.override("ru"):
        html = render(kind, obj, cfg)
    assert "Сколько длится?" in html and "Muss ich mit gewaschenen Haaren kommen?" in html


def test_source_survives_normalize():
    from apps.tenants import siteconfig

    cfg = siteconfig.normalize({"page_blocks": {"service_detail": [own_block(style="list")]}})
    assert cfg["page_blocks"]["service_detail"][0]["data"] == {"style": "list", "source": "object"}
    junk = siteconfig.normalize(
        {"page_blocks": {"service_detail": [{**own_block(), "data": {"source": "x"}}]}}
    )
    assert junk["page_blocks"]["service_detail"][0]["data"] == {}
