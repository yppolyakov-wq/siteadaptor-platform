"""DC-1: единый скелет карточки сделки (ТЗ владельца 2026-08-25).

Замки-характеризации ПЕРЕД перестановкой блоков. Требование владельца:
«базовые функции и блоки должны иметь общие настройки — меняется один, меняются
все сразу», поэтому карточки заказа, заявки, брони и записи собираются ОДНИМ
скелетом: голова → состав → скидка → суммы → оплата; статус, клиент и связанные
сделки — в правой колонке; календарь (там, где движок есть) открывается СРАЗУ
НИЖЕ сетки, а не в узком рейле и не по клику.
"""

import uuid
from datetime import datetime, time, timedelta
from decimal import Decimal

import pytest
from django.contrib.messages.middleware import MessageMiddleware
from django.contrib.sessions.middleware import SessionMiddleware
from django.test import RequestFactory
from django.utils import timezone

from apps.booking import services as booking_services
from apps.booking.models import Resource
from apps.catalog.tests.factories import ProductFactory
from apps.jobs import services as job_services
from apps.orders import services as order_services
from apps.stays import services as stay_services
from apps.stays.models import StayUnit
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _urlconf(settings):
    settings.ROOT_URLCONF = "config.urls_tenant"


class _User:
    is_authenticated = True
    is_active = True
    username = "owner"


def _tenant(business_type="retail"):
    from apps.core.modules import default_disabled_for

    return TenantFactory(
        schema_name=f"t{uuid.uuid4().hex[:8]}",
        business_type=business_type,
        disabled_modules=list(default_disabled_for(business_type)),
    )


def _req(path="/dashboard/", tenant=None):
    req = RequestFactory().get(path)
    SessionMiddleware(lambda r: None).process_request(req)
    MessageMiddleware(lambda r: None).process_request(req)
    req.user = _User()
    req.tenant = tenant if tenant is not None else _tenant()
    return req


# --- сделки четырёх видов ---------------------------------------------------


def _order():
    return order_services.create_order(
        items=[(ProductFactory(name={"de": "Brot"}, base_price=Decimal("5.00")), 2)],
        name="Anna Beispiel",
        email=f"a-{uuid.uuid4().hex[:6]}@t.de",
    )


def _job():
    job = job_services.create_job(title="Badsanierung", name="Ben Bauer", email="ben@t.de")
    job_services.set_lines(job, [{"text": "Fliesen", "qty": 1, "unit_price": "100.00"}])
    return job


def _stay():
    unit = StayUnit.objects.create(name=f"Zimmer {uuid.uuid4().hex[:6]}", price_cents=8000)
    today = timezone.localdate()
    return stay_services.book_stay(
        unit,
        arrival=today + timedelta(days=3),
        departure=today + timedelta(days=5),
        name="Clara Gast",
        email="clara@t.de",
    )


def _booking():
    resource = Resource.objects.create(name=f"Stuhl {uuid.uuid4().hex[:6]}")
    day = timezone.localdate() + timedelta(days=2)
    start = datetime.combine(day, time(10, 0), tzinfo=timezone.get_current_timezone())
    return booking_services.book(
        resource, start=start, end=start + timedelta(hours=1), name="Dora Klein", email="d@t.de"
    )


def _cards():
    """(kind, html) для всех четырёх карточек сделок."""
    from apps.booking import views as booking_views
    from apps.jobs import views as job_views
    from apps.orders import views as order_views
    from apps.stays import views as stay_views

    out = []
    for kind, view, obj, bt in (
        ("order", order_views.order_detail, _order(), "retail"),
        ("job", job_views.job_detail, _job(), "handwerker"),
        ("stay", stay_views.booking_detail, _stay(), "hotel"),
        ("booking", booking_views.booking_detail, _booking(), "friseur"),
    ):
        req = _req(tenant=_tenant(bt))
        out.append((kind, view(req, obj.pk).content.decode()))
    return out


# --- замки ------------------------------------------------------------------


def test_every_deal_card_keeps_its_core_blocks():
    """Номер, клиент и вход в переписку остаются на каждой карточке."""
    for kind, html in _cards():
        assert "data-deal-card" in html, kind
        assert 'data-deal-block="customer"' in html, kind
        assert f"/inbox/deal/{kind}/" in html, kind  # C1: «написать клиенту»


def test_status_lives_in_the_rail_on_every_card():
    """ТЗ: «статус перенести во вторую колонку» — карточка статуса в рейле."""
    for kind, html in _cards():
        assert 'data-deal-block="status"' in html, kind
        assert "data-deal-rail" in html, kind
        assert html.index('data-deal-block="status"') > html.index("data-deal-rail"), kind


def test_block_order_is_the_same_everywhere():
    """Состав → скидка → суммы → оплата: порядок один на всех карточках."""
    for kind, html in _cards():
        order = [
            html.index(f'data-deal-block="{name}"')
            for name in ("items", "discount", "totals", "payment")
            if f'data-deal-block="{name}"' in html
        ]
        assert order == sorted(order), kind


def test_calendar_opens_below_the_grid_where_the_engine_exists():
    """Владелец 2026-08-25: «если есть календарь — открывается сразу ниже сетки».

    У брони и записи движок есть (Belegungsplan / Tagesplan) → блок присутствует
    и стоит ПОСЛЕ сетки. У заявки календарного движка нет → блока нет вовсе."""
    for kind, html in _cards():
        if kind in ("stay", "booking"):
            assert 'data-deal-block="calendar"' in html, kind
            assert html.index('data-deal-block="calendar"') > html.index("data-deal-rail"), kind
        if kind == "job":
            assert 'data-deal-block="calendar"' not in html


def test_shared_blocks_come_from_one_source():
    """«Меняется один — меняются все»: общие блоки живут в общих партиалах."""
    from pathlib import Path

    base = Path("templates/core/deal_card_base.html").read_text()
    for marker in ("_deal_status_card.html", "_deal_customer_card.html", "_deal_links_block.html"):
        assert marker in base, marker
    for tpl in (
        "templates/orders/order_detail.html",
        "templates/jobs/detail.html",
        "templates/stays/booking_detail.html",
        "templates/booking/booking_detail.html",
    ):
        body = Path(tpl).read_text()
        assert "core/deal_card_base.html" in body or "deal_card_base" in body, tpl

    # Панель брони под Belegungsplan — не страница, а fetch-фрагмент; она обязана
    # собираться из ТЕХ ЖЕ кусков, что страница (иначе правка разъедется).
    fragment = Path("templates/stays/_booking_card.html").read_text()
    page = Path("templates/stays/booking_detail.html").read_text()
    for part in (
        "_stay_stay.html",
        "_stay_edit.html",
        "_stay_amount.html",
        "_stay_meldeschein.html",
    ):
        assert part in fragment and part in page, part


# --- DC-4: внешний номер у всех видов сделок ---------------------------------


def test_external_number_form_on_every_card():
    """ТЗ: «номер заказа основной и дополнительный, его можно изменить» — поле
    есть на всех четырёх карточках, приёмник ОДИН (kind-агностичный)."""
    for kind, html in _cards():
        assert 'name="external_code"' in html, kind
        assert f"/dashboard/externe-nummer/{kind}/" in html, kind


def test_external_number_saves_and_is_searchable(client, django_user_model):
    """Сохранение пишет поле сделки и находится поиском продаж."""
    from apps.core import transactions
    from apps.core import views as core_views

    job = _job()
    req = RequestFactory().post(
        f"/dashboard/externe-nummer/job/{job.pk}/",
        {"external_code": "KASSE-4711", "next": "/dashboard/verkaeufe/"},
    )
    SessionMiddleware(lambda r: None).process_request(req)
    MessageMiddleware(lambda r: None).process_request(req)
    req.user = _User()
    req.tenant = _tenant("handwerker")
    resp = core_views.deal_external_edit(req, "job", job.pk)
    assert resp.status_code == 302
    job.refresh_from_db()
    assert job.external_code == "KASSE-4711"
    # Поиск сделок находит по внешнему номеру (реестр _TITLE_SEARCH).
    assert "external_code" in transactions._TITLE_SEARCH["job"]
    assert "external_code" in transactions._TITLE_SEARCH["stay"]
    assert "external_code" in transactions._TITLE_SEARCH["booking"]
