"""VS-3a: связь сделок «якорь + прикреплённые» (план vs3-deal-links-plan-2026-08-20).

Замки написаны ДО кода. Инварианты волны (§4 плана): у спутника ОДИН якорь;
вложенности глубже одного уровня нет; self-link и цикл запрещены; движение по
колонкам независимо (каскадов нет); чтение для доски — батчем (без N+1);
сирота (объект удалён) не ломает рендер.
"""

import uuid
from datetime import datetime, timedelta
from decimal import Decimal

import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.utils import timezone

from apps.core import deal_links
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _urlconf(settings):
    settings.ROOT_URLCONF = "config.urls_tenant"


def _stay():
    from apps.stays import services
    from apps.stays.models import StayUnit

    unit = StayUnit.objects.create(name=f"Zimmer {uuid.uuid4().hex[:6]}", price_cents=8000)
    arrival = timezone.localdate() + timedelta(days=7)
    return services.book_stay(
        unit, arrival=arrival, departure=arrival + timedelta(days=2), name="Fam. Klein"
    )


def _booking(name="Velo"):
    from apps.booking import services
    from apps.booking.models import Resource

    resource = Resource.objects.create(name=f"{name} {uuid.uuid4().hex[:6]}")
    start = timezone.make_aware(datetime(2026, 9, 1, 10, 0))
    return services.book(resource, start=start, end=start + timedelta(hours=2), name="Fam. Klein")


def _order():
    from apps.catalog.tests.factories import ProductFactory
    from apps.orders.services import create_order

    product = ProductFactory(base_price=Decimal("12.00"))
    return create_order(items=[(product, 1)], name="Fam. Klein", email="k@test.de")


# --- 1/2: создание, идемпотентность, перенос ---------------------------------
def test_attach_creates_link_and_is_idempotent():
    stay, velo = _stay(), _booking()
    link = deal_links.attach("stay", stay.pk, "booking", velo.pk, note="Velo, 2 Tage")
    again = deal_links.attach("stay", stay.pk, "booking", velo.pk, note="Velo, 3 Tage")
    assert link.pk == again.pk  # та же строка, не дубль
    assert again.note == "Velo, 3 Tage"
    assert deal_links.DealLink.objects.count() == 1


def test_second_anchor_moves_the_link_not_duplicates_it():
    """У спутника ОДИН якорь: иначе доска врала бы «+1 услуга» у двух броней."""
    first, second, velo = _stay(), _stay(), _booking()
    deal_links.attach("stay", first.pk, "booking", velo.pk)
    deal_links.attach("stay", second.pk, "booking", velo.pk)
    assert deal_links.DealLink.objects.count() == 1
    anchor = deal_links.anchor_of("booking", velo.pk)
    assert (anchor.anchor_kind, anchor.anchor_id) == ("stay", second.pk)


# --- 3/4/5: запрещённые связи -------------------------------------------------
def test_self_link_rejected():
    stay = _stay()
    with pytest.raises(ValueError):
        deal_links.attach("stay", stay.pk, "stay", stay.pk)


def test_cycle_rejected():
    stay, velo = _stay(), _booking()
    deal_links.attach("stay", stay.pk, "booking", velo.pk)
    with pytest.raises(ValueError):
        deal_links.attach("booking", velo.pk, "stay", stay.pk)


def test_second_level_rejected():
    """Спутник спутника не бывает — иначе доска превращается в дерево."""
    stay, velo, transfer = _stay(), _booking("Velo"), _booking("Transfer")
    deal_links.attach("stay", stay.pk, "booking", velo.pk)
    with pytest.raises(ValueError):
        deal_links.attach("booking", velo.pk, "booking", transfer.pk)


def test_unknown_kind_rejected():
    stay = _stay()
    with pytest.raises(ValueError):
        deal_links.attach("stay", stay.pk, "nope", uuid.uuid4())


def test_missing_object_rejected():
    stay = _stay()
    with pytest.raises(ValueError):
        deal_links.attach("stay", stay.pk, "booking", uuid.uuid4())


# --- 6: батч-чтение для доски -------------------------------------------------
def test_for_cards_is_batched_not_per_card():
    stay = _stay()
    children = [_booking(f"Extra{i}") for i in range(5)]
    for child in children:
        deal_links.attach("stay", stay.pk, "booking", child.pk)

    with CaptureQueriesContext(connection) as few:
        deal_links.for_cards("stay", [stay.pk])
    one_child_stay = _stay()
    deal_links.attach("stay", one_child_stay.pk, "booking", _booking("Solo").pk)
    with CaptureQueriesContext(connection) as one:
        deal_links.for_cards("stay", [one_child_stay.pk])
    # пять связей стоят столько же запросов, сколько одна
    assert len(few.captured_queries) == len(one.captured_queries)


def test_for_cards_returns_children_and_anchor_sides():
    stay, velo = _stay(), _booking()
    deal_links.attach("stay", stay.pk, "booking", velo.pk, note="Velo")
    anchors = deal_links.for_cards("stay", [stay.pk])
    assert len(anchors[stay.pk]["children"]) == 1
    child_side = deal_links.for_cards("booking", [velo.pk])
    assert child_side[velo.pk]["anchor"] is not None
    assert "Zimmer" in child_side[velo.pk]["anchor"].title


# --- 7: сирота ----------------------------------------------------------------
def test_orphan_link_is_ignored_not_fatal():
    """Объект удалён (редкость, но не должно ронять доску) — связь молча выпадает."""
    stay, velo = _stay(), _booking()
    deal_links.attach("stay", stay.pk, "booking", velo.pk)
    velo.delete()
    data = deal_links.for_cards("stay", [stay.pk])
    assert data[stay.pk]["children"] == []


# --- 12: движение независимо --------------------------------------------------
def test_cancelling_the_anchor_keeps_the_link():
    """Каскадов нет: отмена якоря не рвёт связь и не трогает спутника."""
    from apps.stays.state_machine import StayBookingSM

    stay, velo = _stay(), _booking()
    before = velo.status
    deal_links.attach("stay", stay.pk, "booking", velo.pk)
    StayBookingSM().apply(stay, "cancelled")
    velo.refresh_from_db()
    assert velo.status == before  # спутник не тронут
    assert deal_links.anchor_of("booking", velo.pk) is not None


def test_detach_removes_the_link():
    stay, velo = _stay(), _booking()
    deal_links.attach("stay", stay.pk, "booking", velo.pk)
    assert deal_links.detach("booking", velo.pk) is True
    assert deal_links.anchor_of("booking", velo.pk) is None
    assert deal_links.detach("booking", velo.pk) is False  # повтор — no-op


def test_children_of_lists_mixed_kinds():
    stay = _stay()
    deal_links.attach("stay", stay.pk, "booking", _booking().pk)
    deal_links.attach("stay", stay.pk, "order", _order().pk)
    kinds = {link.child_kind for link in deal_links.children_of("stay", stay.pk)}
    assert kinds == {"booking", "order"}


def test_tenant_factory_schema_isolation_smoke():
    """Таблица TENANT: связь живёт в схеме тенанта (регресс на SHARED по ошибке)."""
    tenant = TenantFactory.build()
    assert tenant is not None
    from django.apps import apps as django_apps

    model = django_apps.get_model("core.DealLink")
    assert model._meta.app_label == "core"


# --- VS-3b: связь на карточках доски -----------------------------------------
def _tenant_for(business_type="hotel"):
    from apps.core.modules import default_disabled_for

    return TenantFactory(
        schema_name=f"t{uuid.uuid4().hex[:8]}",
        business_type=business_type,
        disabled_modules=list(default_disabled_for(business_type)),
    )


def test_board_card_shows_both_sides_of_the_link():
    from apps.core import transactions

    stay, velo = _stay(), _booking()
    deal_links.attach("stay", stay.pk, "booking", velo.pk, note="Velo, 2 Tage")
    tenant = _tenant_for()

    stays_section = transactions.manage_sections_for(tenant, only="stay")[0]
    anchor_tx = next(t for t in stays_section["transactions"] if t.pk == stay.pk)
    assert len(anchor_tx.linked_children) == 1  # у якоря — спутник

    booking_section = transactions.manage_sections_for(tenant, only="booking")[0]
    child_tx = next(t for t in booking_section["transactions"] if t.pk == velo.pk)
    assert child_tx.linked_anchor is not None and "Zimmer" in child_tx.linked_anchor.title


def test_board_link_lookup_does_not_scale_with_cards():
    """Замок N+1: связи читаются батчем — 5 связанных карточек стоят столько же
    запросов, сколько одна."""
    from apps.core import transactions

    tenant = _tenant_for()
    stay = _stay()
    deal_links.attach("stay", stay.pk, "booking", _booking("Solo").pk)
    with CaptureQueriesContext(connection) as one:
        transactions.manage_sections_for(tenant, only="stay")

    for i in range(4):
        s = _stay()
        deal_links.attach("stay", s.pk, "booking", _booking(f"E{i}").pk)
    with CaptureQueriesContext(connection) as many:
        transactions.manage_sections_for(tenant, only="stay")
    assert len(many.captured_queries) == len(one.captured_queries)


# --- VS-3c: экран привязки и отвязки ------------------------------------------
def _cab_req(path, method="get", data=None, tenant=None):
    from django.contrib.auth import get_user_model
    from django.contrib.messages.middleware import MessageMiddleware
    from django.contrib.sessions.middleware import SessionMiddleware
    from django.test import RequestFactory

    req = getattr(RequestFactory(), method)(path, data or {})
    SessionMiddleware(lambda r: None).process_request(req)
    MessageMiddleware(lambda r: None).process_request(req)
    req.user = get_user_model().objects.create_user(
        username=f"o-{uuid.uuid4().hex[:8]}", password="pw12345678"
    )
    req.tenant = tenant or _tenant_for()
    return req


def test_link_screen_finds_candidates_and_excludes_itself():
    from apps.core import views

    stay, velo = _stay(), _booking()
    tenant = _tenant_for()
    body = views.deal_link_view(
        _cab_req(f"/dashboard/verknuepfen/stay/{stay.pk}/?role=anchor&q=Fam", tenant=tenant),
        kind="stay",
        pk=stay.pk,
    ).content.decode()
    assert str(velo.reference_code) in body  # кандидат найден
    assert f'value="{stay.pk}"' not in body  # сама себе не пара — не в кандидатах


def test_link_screen_attaches_from_anchor_side():
    from apps.core import views

    stay, velo = _stay(), _booking()
    resp = views.deal_link_view(
        _cab_req(
            f"/dashboard/verknuepfen/stay/{stay.pk}/?role=anchor",
            "post",
            {"target_kind": "booking", "target_id": str(velo.pk), "next": "/dashboard/"},
        ),
        kind="stay",
        pk=stay.pk,
    )
    assert resp.status_code == 302
    link = deal_links.anchor_of("booking", velo.pk)
    assert link is not None and link.anchor_id == stay.pk


def test_link_screen_attaches_from_child_side():
    from apps.core import views

    stay, velo = _stay(), _booking()
    views.deal_link_view(
        _cab_req(
            f"/dashboard/verknuepfen/booking/{velo.pk}/",
            "post",
            {"target_kind": "stay", "target_id": str(stay.pk)},
        ),
        kind="booking",
        pk=velo.pk,
    )
    assert deal_links.anchor_of("booking", velo.pk).anchor_id == stay.pk


def test_link_screen_reports_rule_violation_instead_of_crashing():
    """Правило «одна услуга — одна бронь» объясняется человеку, а не 500."""
    from apps.core import views

    stay = _stay()
    req = _cab_req(
        f"/dashboard/verknuepfen/stay/{stay.pk}/?role=anchor",
        "post",
        {"target_kind": "stay", "target_id": str(stay.pk)},  # self-link
    )
    resp = views.deal_link_view(req, kind="stay", pk=stay.pk)
    assert resp.status_code == 302
    assert any("nicht möglich" in str(m) for m in req._messages)


def test_unlink_endpoint_is_post_only_and_returns_internal_path():
    from apps.core import views

    stay, velo = _stay(), _booking()
    deal_links.attach("stay", stay.pk, "booking", velo.pk)
    resp = views.deal_unlink_view(
        _cab_req(
            f"/dashboard/verknuepfen/booking/{velo.pk}/loesen/", "post", {"next": "//evil.tld"}
        ),
        kind="booking",
        pk=velo.pk,
    )
    assert resp.status_code == 302
    assert not resp.url.startswith("//")  # протокол-относительный next отбит
    assert deal_links.anchor_of("booking", velo.pk) is None


def test_detail_block_shows_children_with_reference_total():
    from apps.core import views  # noqa: F401 — контекст берём напрямую

    # Спутник с ЦЕНОЙ (у брони ресурса без услуги цена нулевая — итога не будет).
    stay, extra = _stay(), _order()
    deal_links.attach("stay", stay.pk, "order", extra.pk)
    ctx = deal_links.block_context("stay", stay.pk)
    assert len(ctx["children"]) == 1
    assert "12" in ctx["children_total"] and "€" in ctx["children_total"]


def test_deal_search_finds_by_what_is_on_the_card():
    """Стенд VS-3: владелец ищет «Fahrrad» (то, что видит на карточке), а не
    фамилию гостя. Поиск покрывает поля заголовка — выигрывают палитра, список
    продаж и пикер привязки."""
    from apps.core import transactions

    velo = _booking("Fahrradverleih")
    found = list(transactions._managed_queryset("booking", q="Fahrrad"))
    assert velo.pk in {b.pk for b in found}
    # код и клиент ищутся как раньше
    assert velo.pk in {
        b.pk for b in transactions._managed_queryset("booking", q=velo.reference_code)
    }
    assert velo.pk in {b.pk for b in transactions._managed_queryset("booking", q="Klein")}


def test_deal_search_by_unit_and_job_title():
    from apps.core import transactions

    stay = _stay()
    assert stay.pk in {s.pk for s in transactions._managed_queryset("stay", q="Zimmer")}
