"""FB-33 M2g-0: характеризация ДО разбивки — события («Groups & companies», «Weitere Termine»),
тур (приватный выезд) и акция («Teilen», визитка «So finden Sie uns»).

План — `docs/fb33-editor-model-2026-11-19.md` §«План M2g». Снимки сняты до кода M2g: без
своих настроек страницы рисуются байт-в-байт как раньше (и со старыми строками блоков).

Обновить (осознанно): FB33M2G_GOLDEN=update uv run pytest <этот файл>
"""

import os
import uuid
from datetime import timedelta
from pathlib import Path

import pytest
from django.utils import timezone

from apps.core.tests import test_fb31p5_detail_golden as _p5
from apps.promotions.tests import test_fb31p3_promo_golden as _p3

pytestmark = pytest.mark.django_db
GOLDEN = Path(__file__).parent / "golden_fb33m2g"
UPDATE = os.environ.get("FB33M2G_GOLDEN") == "update"
TEXT = _p5.TEXT


@pytest.fixture(autouse=True)
def _urlconf(settings, frozen_now):
    settings.ROOT_URLCONF = "config.urls_tenant"


frozen_now = _p5.frozen_now


def _check(name, got):
    path = GOLDEN / f"{name}.html"
    if UPDATE or not path.exists():
        if not UPDATE:
            pytest.fail(f"нет снимка {path.name}: FB33M2G_GOLDEN=update")
        GOLDEN.mkdir(exist_ok=True)
        path.write_text(got)
        return
    assert got == path.read_text(), f"страница изменилась: {path.name}"


def _req(path, cfg, jobs=True):
    request = _p5._req(path, cfg)
    if jobs:
        base = request.tenant.is_module_active
        request.tenant.is_module_active = lambda m, *a, **k: m == "jobs" or base(m, *a, **k)
    return request


def event_html(cfg, *, jobs=True, series=True):
    from apps.events import public_views
    from apps.events.models import Event

    sid = uuid.uuid4() if series else None
    ev = Event.objects.create(
        title="Konzert",
        description="Ein Abend mit Live-Musik.",
        starts_at=timezone.now() + timedelta(days=7),
        status=Event.STATUS_PUBLISHED,
        details=_p5.DETAILS,
        series_id=sid,
    )
    if series:
        Event.objects.create(
            title="Konzert",
            starts_at=timezone.now() + timedelta(days=14),
            status=Event.STATUS_PUBLISHED,
            series_id=sid,
        )
    req = _req(f"/veranstaltung/{ev.pk}/", cfg, jobs)
    return public_views.veranstaltung_detail(req, pk=ev.pk).content.decode()


def tour_html(cfg, *, jobs=True, departures=True):
    from apps.events import public_views
    from apps.events.models import Event, Tour

    tour = Tour.objects.create(
        title="Manali – Leh",
        slug=f"manali-{uuid.uuid4().hex[:6]}",
        is_published=True,
        details=_p5.DETAILS,
    )
    if departures:
        Event.objects.create(
            title="Juni-Tour",
            tour=tour,
            starts_at=timezone.now() + timedelta(days=30),
            status=Event.STATUS_PUBLISHED,
        )
    req = _req(f"/touren/{tour.slug}/", cfg, jobs)
    return public_views.tour_detail(req, slug=tour.slug).content.decode()


def promo_html(cfg, **kw):
    from apps.promotions import public_views
    from apps.tenants.tests.factories import TenantFactory

    promo = _p3._promo("Brot der Woche", **kw)
    _p3._promo("Kuchen der Woche", days=5)
    # адрес и телефон — у сайта есть визитка «So finden Sie uns»
    tenant = TenantFactory.build(
        name="Laden X", site_config=cfg, address="Hauptstr. 1, Solingen", contact_phone="0212 1"
    )
    req = _p3._request(f"/aktionen/{promo.pk}/", tenant)
    return _p3._normalize(public_views.promotion_detail(req, pk=promo.pk).content.decode())


#: старые строки блоков у общей страницы событий (до M2g)
EVENT_ROWS = {
    "plain": {},
    "tail": {"page_blocks": {"event_detail": [TEXT]}},
    "between": {"page_blocks": {"event_detail": [{"key": "idea"}, TEXT, {"key": "includes"}]}},
    "hidden": {"event_detail": {"hidden": ["includes"]}},
    "tabs": {"event_detail": {"layout": "tabs"}},
}


@pytest.mark.parametrize("case", sorted(EVENT_ROWS))
def test_event_page_looks_as_before(case):
    _check(f"event-{case}", _p5._normalize(event_html(EVENT_ROWS[case])))


def test_event_without_jobs_and_series_looks_as_before():
    _check("event-bare", _p5._normalize(event_html({}, jobs=False, series=False)))


@pytest.mark.parametrize("case", ["plain", "tail", "between"])
def test_tour_page_looks_as_before(case):
    _check(f"tour-{case}", _p5._normalize(tour_html(EVENT_ROWS[case])))


@pytest.mark.parametrize("departures", [True, False], ids=["dates", "nodates"])
@pytest.mark.parametrize("jobs", [True, False], ids=["jobs", "nojobs"])
def test_tour_head_buttons_look_as_before(jobs, departures):
    name = f"tour-head-{'jobs' if jobs else 'nojobs'}-{'dates' if departures else 'nodates'}"
    _check(name, _p5._normalize(tour_html({}, jobs=jobs, departures=departures)))


PROMO_ROWS = {
    "plain": {},
    "mid": {"page_blocks": {"promo_detail": [{"key": "offer"}, TEXT, {"key": "related"}]}},
    "style": {"page_blocks": {"promo_detail": [{"key": "offer", "style": "plakat"}, TEXT]}},
    "norelated": {"promo_show_related": False},
}


@pytest.mark.parametrize("case", sorted(PROMO_ROWS))
def test_promo_page_looks_as_before(case):
    _check(f"promo-{case}", promo_html(PROMO_ROWS[case]))


def test_promo_show_only_looks_as_before():
    _check("promo-show", promo_html({}, metadata={"response": "show"}))
