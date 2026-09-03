"""DL-17.4 (A1 «Vorschau») — витрина показывает ЗАПЛАНИРОВАННЫЕ акции.

До этой волны `scheduled` не показывалась нигде, а её деталь отдавала голый 404 —
поэтому карточку «Ab Montag» (привычка Prospekt в DACH) показать было нельзя.
"""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest
from django.contrib.messages.middleware import MessageMiddleware
from django.contrib.sessions.middleware import SessionMiddleware
from django.http import Http404
from django.test import RequestFactory
from django.utils import timezone

from apps.promotions import public_views
from apps.promotions.models import Promotion
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _urlconf(settings):
    settings.ROOT_URLCONF = "config.urls_tenant"


def _tenant(slug):
    return TenantFactory(schema_name="public", slug=slug, name="Sparfuchs", disabled_modules=[])


def _list(tenant, params=None):
    req = RequestFactory().get("/aktionen/", params or {})
    req.tenant = tenant
    return public_views.promotion_list(req).content.decode()


def _detail(tenant, pk):
    req = RequestFactory().get(f"/p/{pk}/")
    SessionMiddleware(lambda r: None).process_request(req)
    MessageMiddleware(lambda r: None).process_request(req)
    req.tenant = tenant
    return public_views.promotion_detail(req, pk=pk)


def _promo(title, *, status="active", starts_in=None, **kw):
    now = timezone.now()
    return Promotion.objects.create(
        title={"de": title},
        status=status,
        promo_type="discount",
        starts_at=now + timedelta(days=starts_in) if starts_in is not None else now,
        ends_at=now + timedelta(days=(starts_in or 0) + 14),
        **kw,
    )


# --- лента будущих акций -------------------------------------------------------
def test_upcoming_strip_lists_scheduled_and_marks_start_date():
    tenant = _tenant("dl17a")
    _promo("Jetzt aktiv", discount_percent=10)
    _promo("Ab Montag", status="scheduled", starts_in=3, discount_percent=30)

    body = _list(tenant)
    assert "data-upcoming-strip" in body
    strip = body[body.index("data-upcoming-strip") :]
    strip = strip[: strip.index("</section>")]
    assert "Ab Montag" in strip and "Jetzt aktiv" not in strip
    assert "data-promo-starts" in strip  # чип «ab <дата>»
    # у будущей акции счётчика и остатка нет — покупать пока нечего
    assert "data-countdown" not in strip


def test_upcoming_hidden_when_filtered_or_absent():
    tenant = _tenant("dl17b")
    _promo("Nur aktiv", discount_percent=10)
    assert "data-upcoming-strip" not in _list(tenant)  # будущих нет — секции нет

    _promo("Ab Montag", status="scheduled", starts_in=3, discount_percent=30)
    assert "data-upcoming-strip" in _list(tenant)
    # выбран фильтр → плоская выдача действующих, превью не мешает сравнению
    assert "data-upcoming-strip" not in _list(tenant, {"rabatt": "20"})


def test_started_and_draft_promotions_never_reach_the_preview_strip():
    tenant = _tenant("dl17c")
    # beat ещё не перевёл в active, но старт уже прошёл — не превью
    _promo("Schon gestartet", status="scheduled", starts_in=-1, discount_percent=20)
    _promo("Entwurf", status="draft", starts_in=3, discount_percent=20)
    body = _list(tenant)
    assert "data-upcoming-strip" not in body
    assert "Entwurf" not in body and "Schon gestartet" not in body


def test_upcoming_buckets_split_by_start_week():
    """Бакеты считаются от НАЧАЛА недели, а не «через N дней» (Prospekt-логика)."""
    now = timezone.make_aware(datetime(2026, 9, 7, 10, 0))  # понедельник

    class _P:
        def __init__(self, starts_at):
            self.starts_at = starts_at

    this_week = _P(now + timedelta(days=2))  # среда той же недели
    next_week = _P(now + timedelta(days=9))  # следующая неделя
    later = _P(now + timedelta(days=30))
    keys = [k for k, _label, _items in public_views._upcoming_buckets([this_week], now)]
    assert keys == ["start_woche"]
    keys = [k for k, _l, _i in public_views._upcoming_buckets([next_week, later, this_week], now)]
    assert keys == ["start_woche", "start_naechste", "start_spaeter"]  # порядок близости


# --- деталь будущей акции ------------------------------------------------------
def test_scheduled_detail_is_preview_without_cta():
    tenant = _tenant("dl17d")
    promo = _promo("Ab Montag", status="scheduled", starts_in=4, discount_percent=30)
    resp = _detail(tenant, promo.pk)
    assert resp.status_code == 200
    body = resp.content.decode()
    assert "data-promo-preview" in body and "Startet am" in body
    assert "Reserve now" not in body  # покупки нет
    assert 'id="promo-reserve-modal"' not in body  # и формы брони тоже
    assert "data-buybar" not in body  # мобильная липкая панель молчит


def test_active_detail_keeps_cta_and_draft_still_404():
    tenant = _tenant("dl17e")
    live = _promo("Jetzt aktiv", discount_percent=20, price_override="1.99")
    body = _detail(tenant, live.pk).content.decode()
    assert 'id="promo-reserve-modal"' in body and "data-promo-preview" not in body

    draft = _promo("Entwurf", status="draft", starts_in=2)
    with pytest.raises(Http404):
        _detail(tenant, draft.pk)


# --- DL-17.3: страница акций видит черновик Studio -----------------------------
def test_promo_page_reads_builder_draft_in_preview():
    """Правка «Aktionsseite: Aufbau» в Studio обязана быть видна на канве СРАЗУ:
    остальные витринные вьюхи черновик читают, страница акций — не читала."""
    from importlib import import_module

    from django.conf import settings as dj_settings

    tenant = _tenant("dl17f")
    for i in range(3):
        _promo(f"Deal {i}", group="Wochenangebote", discount_percent=10 + i)

    req = RequestFactory().get("/aktionen/", {"preview": "1"})
    req.session = import_module(dj_settings.SESSION_ENGINE).SessionStore()
    req.session["site_preview_draft"] = {"promo_layout": "slider"}
    req.tenant = tenant
    body = public_views.promotion_list(req).content.decode()
    assert "data-promo-strip" in body  # черновик включил ленты

    # без превью — сохранённый конфиг (сеток), черновик не влияет
    assert "data-promo-strip" not in _list(tenant)


# --- DL-23: бакеты предпросмотра рядом колонками -------------------------------
def test_small_preview_buckets_sit_side_by_side():
    """Фидбэк 2026-09-03: три бакета по одной карточке занимали три пустых ряда →
    при ≥2 бакетах по ≤2 карточки блоки идут колонками в одном ряду (без слайдера);
    заголовки и маркеры бакетов сохраняются."""
    tenant = _tenant("dl23a")
    _promo("Diese Woche", status="scheduled", starts_in=1, discount_percent=10)
    _promo("Nächste Woche", status="scheduled", starts_in=8, discount_percent=10)
    _promo("Später", status="scheduled", starts_in=30, discount_percent=10)
    body = _list(tenant)
    assert 'data-upcoming-row="3"' in body and "md:grid-cols-3" in body
    row = body[body.index("data-upcoming-row") :]
    assert row.count("data-upcoming=") == 3 and row.count("data-upcoming-strip") == 3
    assert "data-sf-slider" not in row[: row.index("data-grid")] if "data-grid" in row else True


def test_preview_buckets_stay_as_strips_when_one_bucket_or_many_cards():
    tenant = _tenant("dl23b")
    _promo("Solo", status="scheduled", starts_in=1, discount_percent=10)
    body = _list(tenant)
    assert "data-upcoming-row" not in body and "data-sf-slider" in body  # один бакет — лента
    for i in range(3):
        _promo(f"Mehr {i}", status="scheduled", starts_in=8, discount_percent=10)
    body = _list(tenant)
    assert "data-upcoming-row" not in body  # в бакете 3 карточки — ленты, не колонки
