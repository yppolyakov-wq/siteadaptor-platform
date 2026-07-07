"""U-D1: протокол Transaction — по адаптеру на kind, guard «не пишет статус»,
payment_method в проекции, ленивая резолюция модели/FSM, кабинетный резолвер."""

import uuid
from datetime import datetime, timedelta
from decimal import Decimal

import pytest
from django.utils import timezone

from apps.core import transactions
from apps.core.pipeline import STAGES

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _urlconf(settings):
    settings.ROOT_URLCONF = "config.urls_tenant"


# --- конструкторы одной транзакции каждого kind ------------------------------


def _make_order(**kw):
    from apps.catalog.tests.factories import ProductFactory
    from apps.orders.services import create_order

    product = ProductFactory(base_price=Decimal("8.00"))
    kw.setdefault("name", "Max")
    kw.setdefault("email", "max@test.de")
    return create_order(items=[(product, 1)], **kw)


def _make_booking():
    from apps.booking import services
    from apps.booking.models import Resource

    resource = Resource.objects.create(name=f"Tisch {uuid.uuid4().hex[:6]}")
    start = timezone.make_aware(datetime(2026, 7, 1, 12, 0))
    return services.book(resource, start=start, end=start + timedelta(hours=1), name="Gast")


def _make_stay():
    from apps.stays import services
    from apps.stays.models import StayUnit

    unit = StayUnit.objects.create(name=f"Zimmer {uuid.uuid4().hex[:6]}", price_cents=8000)
    arrival = timezone.localdate() + timedelta(days=10)
    return services.book_stay(
        unit, arrival=arrival, departure=arrival + timedelta(days=2), name="Gast"
    )


def _make_ticket():
    from apps.events.models import Event
    from apps.events.services import book_ticket

    event = Event.objects.create(
        title="Workshop",
        starts_at=timezone.now() + timedelta(days=5),
        status=Event.STATUS_PUBLISHED,
        price_cents=2000,
        capacity=10,
    )
    return book_ticket(event, name="K", email="k@test.de")


def _make_job():
    from apps.jobs import services

    return services.create_job(title="Bad streichen", name="Kunde", email="kunde@test.de")


def _make_reservation():
    from apps.promotions import services
    from apps.promotions.tests.factories import PromotionFactory

    promo = PromotionFactory()
    return services.reserve(promo, name="Gast", email="res@test.de")


_MAKERS = {
    "order": _make_order,
    "booking": _make_booking,
    "stay": _make_stay,
    "ticket": _make_ticket,
    "job": _make_job,
    "reservation": _make_reservation,
}


# --- контракт по каждому kind ------------------------------------------------


@pytest.mark.parametrize("kind", transactions.TRANSACTION_KINDS)
def test_adapter_returns_normalized_contract(kind):
    obj = _MAKERS[kind]()
    tx = transactions.transaction_for(kind, obj)

    assert tx.kind == kind
    assert tx.pk == obj.pk
    assert tx.reference_code == obj.reference_code
    assert tx.customer == obj.customer
    assert tx.title  # непусто
    assert tx.status == obj.status
    assert tx.status_label  # непусто; у Reservation нет choices → свой словарь
    if hasattr(obj, "get_status_display"):
        assert tx.status_label == obj.get_status_display()
    assert tx.pipeline_stage in STAGES
    assert isinstance(tx.payment_method, str)  # null-safe
    assert tx.created_at == obj.created_at
    # публичная и кабинетная ссылки реверсятся (config.urls_tenant активен)
    assert tx.detail_url_customer
    assert tx.manage_url


@pytest.mark.parametrize("kind", transactions.TRANSACTION_KINDS)
def test_allowed_actions_match_fsm_without_reimplementing(kind):
    obj = _MAKERS[kind]()
    tx = transactions.transaction_for(kind, obj)
    sm = transactions.sm_for(kind)
    assert [a["target"] for a in tx.allowed_actions] == sm.allowed_targets(obj.status)
    for a in tx.allowed_actions:
        assert a["label"]
        assert a["stage"] in STAGES


@pytest.mark.parametrize("kind", transactions.TRANSACTION_KINDS)
def test_projection_never_writes_status(kind):
    obj = _MAKERS[kind]()
    before = obj.status
    transactions.transaction_for(kind, obj)
    assert obj.status == before  # инстанс не тронут
    obj.refresh_from_db()
    assert obj.status == before  # и в БД тоже


def test_payment_method_surfaced_for_order():
    order = _make_order(payment_method="stripe")
    tx = transactions.transaction_for("order", order)
    assert tx.payment_method == "stripe"


def test_payment_method_null_safe_for_kinds_without_field():
    # booking не имеет payment_method — проекция даёт '' (не падает)
    tx = transactions.transaction_for("booking", _make_booking())
    assert tx.payment_method == ""


def test_jobs_customer_url_uses_public_token():
    job = _make_job()
    tx = transactions.transaction_for("job", job)
    assert str(job.public_token) in tx.detail_url_customer


def test_subtotal_display_is_formatted_string():
    tx = transactions.transaction_for("order", _make_order())
    assert tx.subtotal_display.endswith("€")  # «8,00 €»


def test_unknown_kind_raises_value_error():
    with pytest.raises(ValueError):
        transactions.transaction_for("nope", object())


def test_lazy_fsm_registry_uses_string_paths():
    # доказательство ленивости: FSM объявлены строковыми путями, не импортами
    for _kind, spec in transactions._KIND_SM.items():
        assert isinstance(spec, tuple) and len(spec) == 2
        assert all(isinstance(part, str) for part in spec)
    # model_for резолвит модель по требованию
    assert transactions.model_for("order").__name__ == "Order"


# --- UD1-3: кабинетный резолвер ----------------------------------------------


def _tenant(disabled=None):
    from apps.tenants.tests.factories import TenantFactory

    return TenantFactory.build(business_type="restaurant", disabled_modules=disabled or [])


def test_manage_sections_lists_active_transaction_modules():
    order = _make_order()
    sections = transactions.manage_sections_for(_tenant())
    orders_sec = next((s for s in sections if s["kind"] == "order"), None)
    assert orders_sec is not None
    assert orders_sec["label"] == "Bestellungen"
    assert [c["stage"] for c in orders_sec["columns"]] == list(STAGES)
    assert any(t.pk == order.pk for t in orders_sec["transactions"])
    # счётчик по стадиям сходится с числом транзакций
    assert sum(orders_sec["stage_counts"].values()) == orders_sec["total"]


def test_manage_sections_skips_inactive_module():
    _make_order()
    sections = transactions.manage_sections_for(_tenant(disabled=["orders"]))
    assert not any(s["kind"] == "order" for s in sections)
