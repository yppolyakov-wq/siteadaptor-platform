"""VS-2 (решения владельца 2026-08-20): главная рабочая страница продаж.

План — `docs/verkaeufe-v2-plan-2026-08-20.md`:
- одно направление → ряда вкладок нет, заголовок = имя направления;
- колонка = СТАТУС, колонки одной стадии — под общей полосой-группой;
- карточка отвечает «когда это и на сколько» (дата события, гости, срок сметы),
  доска сортируется по дате события, в шапке колонки — честная сумма.
"""

import uuid
from datetime import timedelta
from decimal import Decimal

import pytest
from django.contrib.messages.middleware import MessageMiddleware
from django.contrib.sessions.middleware import SessionMiddleware
from django.test import RequestFactory
from django.utils import timezone

from apps.core import transactions, views
from apps.core.pipeline import STAGES
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _urlconf(settings):
    settings.ROOT_URLCONF = "config.urls_tenant"


class _User:
    is_authenticated = True
    is_active = True
    username = "owner"


def _tenant(business_type="catering", **kw):
    from apps.core.modules import default_disabled_for

    kw.setdefault("disabled_modules", list(default_disabled_for(business_type)))
    return TenantFactory(schema_name=f"t{uuid.uuid4().hex[:8]}", business_type=business_type, **kw)


def _req(path="/dashboard/verkaeufe/", tenant=None, **kw):
    req = RequestFactory().get(path)
    SessionMiddleware(lambda r: None).process_request(req)
    MessageMiddleware(lambda r: None).process_request(req)
    req.user = _User()
    req.tenant = tenant if tenant is not None else _tenant(**kw)
    return req


def _job(**kw):
    from apps.jobs import services

    kw.setdefault("title", "Firmenfeier")
    kw.setdefault("name", "Miriam Klein")
    kw.setdefault("email", "mk@test.de")
    return services.create_job(**kw)


# --- VS-2a: одинокая вкладка --------------------------------------------------
def test_single_direction_has_no_tab_row():
    """У 13 из 16 типов направление одно — ряд вкладок из одного элемента был
    чистым шумом; заголовок теперь называет само направление."""
    body = views.verkaeufe(_req()).content.decode()
    assert "data-sales-tabs" not in body
    assert '<h1 class="text-xl font-bold mb-3">Aufträge</h1>' in body


def test_two_directions_keep_tabs_with_active_counts():
    from apps.core import sales_page

    hotel = _tenant(business_type="hotel")
    tabs = sales_page.tab_descriptors(hotel, "stay")
    assert [t["kind"] for t in tabs] == ["stay", "booking"]
    assert all(t["count"] is not None for t in tabs)  # счётчик активных сделок
    body = views.verkaeufe(_req(tenant=hotel)).content.decode()
    assert "data-sales-tabs" in body


# --- VS-2b: колонка = статус, группы = стадии ---------------------------------
def test_columns_are_statuses_grouped_by_stage():
    """«Angebot gesendet» (ждём клиента) и «Beauftragt» (подтверждено) больше не
    лежат в одной колонке — но обе остаются в группе «In Bearbeitung»."""
    tenant = _tenant()
    section = transactions.manage_sections_for(tenant, only="job")[0]
    by_status = {c["status"]: c for c in section["columns"]}
    assert {"quoted", "accepted"} <= set(by_status)
    assert by_status["quoted"]["stage"] == by_status["accepted"]["stage"] == "in_progress"
    assert [g["stage"] for g in section["groups"]] == list(STAGES)
    in_progress = next(g for g in section["groups"] if g["stage"] == "in_progress")
    assert {c["status"] for c in in_progress["columns"]} >= {"quoted", "accepted"}


def test_board_markup_carries_status_dropzones():
    """Drag стал однозначным: зона несёт целевой СТАТУС (раньше — стадию, и JS
    выбирал «первый допустимый переход в неё»)."""
    _job()
    body = views.verkaeufe(_req("/dashboard/verkaeufe/?view=board")).content.decode()
    assert 'data-drop-status="quoted"' in body
    assert 'data-status="new"' in body  # карточка знает свой статус
    assert 'data-target="' in body  # кнопка перехода = цель drop-зоны


def test_custom_status_gets_its_own_column():
    """SM-3: свой статус владельца — своя колонка в группе своей роли."""
    tenant = _tenant(
        site_config={
            "status_defs": {
                "job": [
                    {
                        "code": "vorbereitung",
                        "label": "In Vorbereitung",
                        "role": "active",
                        "stage": "in_progress",
                    }
                ]
            }
        }
    )
    section = transactions.manage_sections_for(tenant, only="job")[0]
    col = next((c for c in section["columns"] if c["status"] == "vorbereitung"), None)
    assert col is not None and col["custom"] is True
    assert col["label"] == "In Vorbereitung" and col["stage"] == "in_progress"


# --- VS-2c: «что горит и где деньги» -----------------------------------------
def test_card_shows_event_date_and_guests():
    """Поля волны AF-1 (event_date/guest_count) наконец видны на доске."""
    job = _job()
    job.event_date = timezone.localdate() + timedelta(days=3)
    job.guest_count = 80
    job.save(update_fields=["event_date", "guest_count", "updated_at"])
    tx = transactions.transaction_for("job", job)
    assert tx.when == job.event_date and "80" in tx.when_note

    body = views.verkaeufe(_req("/dashboard/verkaeufe/?view=board")).content.decode()
    assert "80" in body and job.event_date.strftime("%d.%m.") in body


def test_board_sorts_by_event_date_not_creation():
    """Завтрашний корпоратив выше свадьбы в сентябре, даже если создан позже."""
    today = timezone.localdate()
    far = _job(title="Hochzeit")
    far.event_date = today + timedelta(days=90)
    far.save(update_fields=["event_date", "updated_at"])
    soon = _job(title="Firmenfeier morgen")
    soon.event_date = today + timedelta(days=1)
    soon.save(update_fields=["event_date", "updated_at"])

    section = transactions.manage_sections_for(_tenant(), only="job", board_order=True)[0]
    titles = [t.title for t in section["transactions"]]
    assert titles.index("Firmenfeier morgen") < titles.index("Hochzeit")


def test_jobs_without_date_go_last_not_first():
    today = timezone.localdate()
    _job(title="Ohne Datum")
    dated = _job(title="Mit Datum")
    dated.event_date = today + timedelta(days=5)
    dated.save(update_fields=["event_date", "updated_at"])
    section = transactions.manage_sections_for(_tenant(), only="job", board_order=True)[0]
    titles = [t.title for t in section["transactions"]]
    assert titles.index("Mit Datum") < titles.index("Ohne Datum")


def test_quote_deadline_badge_marks_overdue_on_the_server():
    """Просрочка считается на сервере: карточку перерисовывает kanban_action со
    своим контекстом — переменная шаблона `today` туда бы не доехала."""
    job = _job()
    job.valid_until = timezone.localdate() - timedelta(days=1)
    job.save(update_fields=["valid_until", "updated_at"])
    assert transactions.transaction_for("job", job).deadline_overdue is True

    job.valid_until = timezone.localdate() + timedelta(days=5)
    job.save(update_fields=["valid_until", "updated_at"])
    assert transactions.transaction_for("job", job).deadline_overdue is False


def test_column_sum_is_a_db_aggregate_not_loaded_cards():
    """Сумма в шапке колонки — по БД: при лимите карточек она обязана остаться
    честной (тот же урок, что у счётчиков V4)."""
    from apps.catalog.tests.factories import ProductFactory
    from apps.orders.services import create_order

    product = ProductFactory(base_price=Decimal("10.00"))
    for _ in range(3):
        create_order(items=[(product, 1)], name="Max", email="m@test.de")
    tenant = _tenant(business_type="bakery")
    section = transactions.manage_sections_for(tenant, only="order", limit=1)[0]
    col = next(c for c in section["columns"] if c["status"] == "new")
    assert col["count"] == 3
    assert "30" in col["sum_display"]  # 3 × 10,00 €, а не по одной загруженной


def test_no_sum_where_the_total_is_not_an_exact_db_field():
    """У booking/ticket итог считается в Python (цена+extras−скидка) — агрегат по
    price_cents врал бы, поэтому суммы в шапке просто нет."""
    section = transactions.manage_sections_for(_tenant(business_type="friseur"), only="booking")[0]
    assert all(c["sum_display"] == "" for c in section["columns"])
