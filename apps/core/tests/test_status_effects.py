"""FB-3 Вариант B Phase 2: резолверы эффектов статусов (для кастом-статусов).

Резолверы зеркалят встроенные on_transition (те же source/source_ref/amount/vat) →
идемпотентность finance защищает от двойного списания. apply_custom_effects — ролевой
диспетчер (revenue при done-флаге; restore+unredeem+reversal при роли cancelled).
"""

from decimal import Decimal
from types import SimpleNamespace

import pytest

from apps.core import status_effects
from apps.core.status_registry import StatusDescriptor

pytestmark = pytest.mark.django_db


def _entries(source, ref):
    from apps.finance.models import RevenueEntry

    return RevenueEntry.objects.filter(source=source, source_ref=ref)


# --- revenue per kind (стаб: резолвер читает только атрибуты) ------------------


def test_revenue_order_idempotent():
    o = SimpleNamespace(
        id="o1", total=Decimal("8.00"), currency="EUR", customer=None, reference_code="R1"
    )
    status_effects.record_revenue_for("order", o)
    e = _entries("order", "o1")
    assert e.count() == 1 and e.first().amount == Decimal("8.00")
    status_effects.record_revenue_for("order", o)  # повтор → без дубля (source_ref)
    assert _entries("order", "o1").count() == 1


@pytest.mark.parametrize(
    ("kind", "source", "vat"),
    [("booking", "booking", "19.00"), ("stay", "stay", "7.00"), ("ticket", "event", "19.00")],
)
def test_revenue_cents_kinds_with_vat(kind, source, vat):
    inst = SimpleNamespace(id=f"{kind}1", total_cents=5000, customer=None, reference_code="R")
    status_effects.record_revenue_for(kind, inst)
    e = _entries(source, f"{kind}1").first()
    assert e is not None and e.amount == Decimal("50.00") and e.vat_rate == Decimal(vat)


def test_revenue_booking_zero_skipped():
    inst = SimpleNamespace(id="b0", total_cents=0, customer=None, reference_code="R")
    status_effects.record_revenue_for("booking", inst)
    assert _entries("booking", "b0").count() == 0


def test_revenue_reservation_price_times_qty():
    promo = SimpleNamespace(new_price=Decimal("4.00"), currency="EUR")
    inst = SimpleNamespace(
        id="res1", promotion=promo, quantity=3, customer=None, reference_code="R"
    )
    status_effects.record_revenue_for("reservation", inst)
    assert _entries("reservation", "res1").first().amount == Decimal("12.00")


def test_job_revenue_is_noop():
    status_effects.record_revenue_for("job", SimpleNamespace(id="j1"))
    from apps.finance.models import RevenueEntry

    assert not RevenueEntry.objects.filter(source__in=("job",)).exists()


# --- reversal (order нетится точным встроенным ref) ---------------------------


def test_reversal_order_nets_to_zero():
    o = SimpleNamespace(
        id="rv1", total=Decimal("8.00"), currency="EUR", customer=None, reference_code="R"
    )
    status_effects.record_revenue_for("order", o)
    status_effects.record_reversal_for("order", o)
    from apps.finance.models import RevenueEntry

    net = sum(
        e.amount for e in RevenueEntry.objects.filter(source="order", source_ref__startswith="rv1")
    )
    assert net == Decimal("0.00")
    assert _entries("order", "rv1:return").first().amount == Decimal("-8.00")


# --- restore_stock (order — реальный заказ) -----------------------------------


def test_restore_stock_order_increments_and_ledgers():
    from apps.catalog.tests.factories import ProductFactory
    from apps.orders.services import create_order

    p = ProductFactory(base_price=Decimal("5.00"), stock_quantity=20)
    order = create_order(items=[(p, 3)], name="X", email="x@t.de")
    p.refresh_from_db()
    before = p.stock_quantity
    status_effects.restore_stock_for("order", order)
    p.refresh_from_db()
    assert p.stock_quantity == before + 3  # вернулись 3 шт


# --- диспетчер apply_custom_effects (monkeypatch резолверов) ------------------


@pytest.fixture
def _capture(monkeypatch):
    calls = []
    monkeypatch.setattr(status_effects, "record_revenue_for", lambda k, i: calls.append(("rev", k)))
    monkeypatch.setattr(
        # Ревью 2026-08-25: restore_stock_for принимает роль ПОКИДАЕМОГО статуса
        # (job возвращает только резерв, не израсходованное).
        status_effects,
        "restore_stock_for",
        lambda k, i, src_role=None: calls.append(("stock", k)),
    )
    monkeypatch.setattr(status_effects, "unredeem_for", lambda i: calls.append("unredeem"))
    monkeypatch.setattr(
        status_effects, "record_reversal_for", lambda k, i: calls.append(("reversal", k))
    )
    return calls


def _desc(role, revenue=False):
    return StatusDescriptor(
        code="c", role=role, stage="done", revenue_recognized=revenue, builtin=False
    )


def test_dispatch_done_records_revenue(_capture):
    status_effects.apply_custom_effects("order", object(), None, _desc("done", revenue=True))
    assert _capture == [("rev", "order")]


def test_dispatch_active_fires_nothing(_capture):
    status_effects.apply_custom_effects("order", object(), None, _desc("active"))
    assert _capture == []


def test_dispatch_cancel_restores_and_unredeems(_capture):
    status_effects.apply_custom_effects("booking", object(), _desc("active"), _desc("cancelled"))
    assert _capture == [("stock", "booking"), "unredeem"]


def test_dispatch_cancel_after_revenue_reverses(_capture):
    src = _desc("done", revenue=True)
    status_effects.apply_custom_effects("order", object(), src, _desc("cancelled"))
    assert _capture == [("stock", "order"), "unredeem", ("reversal", "order")]


def test_dispatch_skips_cancel_effects_when_src_already_cancelled(_capture):
    """SM-3: сделка, УЖЕ стоящая в cancelled-роли, при входе в другой cancelled-статус
    не возвращает склад/лимит/ваучер второй раз (возвраты не идемпотентны). Второй
    слой той же защиты — custom_edges дропает cancel↔cancel рёбра."""
    src = StatusDescriptor(code="storniert_alt", role="cancelled", stage="terminal", builtin=False)
    status_effects.apply_custom_effects("reservation", object(), src, _desc("cancelled"))
    assert _capture == []


def test_dispatch_job_done_role_commits_stock(monkeypatch):
    """SM-3 (зеркало G11): вход job в кастом done-роль списывает Teile — builtin
    вешает commit_stock на литерал t.dst=='done', кастом-статус его миновал бы
    (счёт выставлен, склад не тронут). commit_stock идемпотентен (stock_committed)."""
    calls = []
    monkeypatch.setattr("apps.jobs.services.commit_stock", lambda j: calls.append(j))
    status_effects.apply_custom_effects("job", object(), None, _desc("done"))
    assert len(calls) == 1
    # для других kind done-роль склад не трогает
    calls.clear()
    status_effects.apply_custom_effects("order", object(), None, _desc("done"))
    assert calls == []


@pytest.mark.django_db
def test_dispatch_ticket_cancel_stops_installment_plan():
    """SM-3 (зеркало R10e): кастом-отмена билета стопит активную рассрочку —
    иначе beat продолжил бы off-session списания по отменённому билету."""
    from datetime import timedelta

    from django.utils import timezone

    from apps.events.models import Event, InstallmentPlan
    from apps.events.services import book_ticket

    event = Event.objects.create(
        title="Kurs",
        starts_at=timezone.now() + timedelta(days=7),
        status=Event.STATUS_PUBLISHED,
        price_cents=30000,
        capacity=10,
    )
    ticket = book_ticket(event, name="A", email="a@test.de", quantity=1)
    plan = InstallmentPlan.objects.create(ticket=ticket, total_cents=30000, count=3)

    src = _desc("active")
    dst = StatusDescriptor(code="abgesagt", role="cancelled", stage="terminal", builtin=False)
    status_effects.apply_custom_effects("ticket", ticket, src, dst)
    plan.refresh_from_db()
    assert plan.status == InstallmentPlan.STATUS_CANCELLED


# --- Phase 3b: хук apply() — эффекты ТОЛЬКО для кастом-статуса -----------------


def test_apply_hook_fires_for_custom_dst_only(monkeypatch):
    """apply() зовёт apply_custom_effects ТОЛЬКО для кастом-статуса (builtin=False);
    встроенный dst → no-op (эффекты уже в on_transition)."""
    import uuid
    from datetime import datetime, timedelta

    from django.utils import timezone

    from apps.booking import services
    from apps.booking.models import Resource
    from apps.core import fsm, status_registry
    from apps.core.status_registry import StatusDescriptor

    resource = Resource.objects.create(name=f"Tisch {uuid.uuid4().hex[:6]}")
    start = timezone.make_aware(datetime(2026, 7, 1, 12, 0))
    booking = services.book(resource, start=start, end=start + timedelta(hours=1), name="Gast")

    calls = []
    monkeypatch.setattr(
        status_effects, "apply_custom_effects", lambda k, i, s, d: calls.append((k, d.code))
    )
    custom = StatusDescriptor(code="wip", role="active", stage="in_progress", builtin=False)
    orig = status_registry.resolve
    monkeypatch.setattr(
        status_registry, "resolve", lambda k, s, t=None: custom if s == "wip" else orig(k, s, t)
    )

    class SM(fsm.StateMachine):
        kind = "booking"
        transitions = [
            fsm.Transition("pending", "wip", "x"),
            fsm.Transition("wip", "confirmed", "y"),
        ]

    SM().apply(booking, "wip")  # кастом dst → хук сработал
    assert calls == [("booking", "wip")]
    calls.clear()
    SM().apply(booking, "confirmed")  # встроенный dst → no-op
    assert calls == []


# --- Phase 3b-2: кастом-active статус держит ёмкость (anti-oversell) -----------


def test_custom_active_status_blocks_stay_capacity(monkeypatch):
    """FB-3 Вариант B: бронь в кастом-active статусе занимает номер (range_available=False),
    как built-in confirmed. Threading active_statuses_for в oversell-запросы."""
    from datetime import timedelta

    from django.utils import timezone

    from apps.core import status_registry
    from apps.stays import availability, services
    from apps.stays.models import StayBooking, StayUnit
    from apps.tenants.tests.factories import TenantFactory

    tenant = TenantFactory(
        site_config={
            "status_defs": {
                "stay": [
                    {
                        "code": "beim_lieferanten",
                        "role": "active",
                        "stage": "in_progress",
                        "blocks_capacity": True,
                    }
                ]
            }
        }
    )
    monkeypatch.setattr(status_registry, "_current_tenant", lambda: tenant)

    unit = StayUnit.objects.create(name="Z1", price_cents=8000, quantity=1)
    arrival = timezone.localdate() + timedelta(days=10)
    dep = arrival + timedelta(days=2)
    booking = services.book_stay(unit, arrival=arrival, departure=dep, name="G")
    # переведём в кастом-active статус напрямую (легальный переход даст Phase 4)
    StayBooking.objects.filter(pk=booking.pk).update(status="beim_lieferanten")
    assert availability.range_available(unit, arrival, dep) is False  # номер занят кастом-active
    # контроль: снимем занятость (терминальный кастом не блокирует) → свободно
    StayBooking.objects.filter(pk=booking.pk).update(status="cancelled")
    assert availability.range_available(unit, arrival, dep) is True


# --- Phase 4: кастом-переходы через apply() (end-to-end) -----------------------


def test_custom_transition_reachable_via_apply(monkeypatch):
    """Phase 4: кастом-статус ДОСТИЖИМ через apply() (граф тенанта поверх FSM); держит
    ёмкость; allowed_targets включает кастом-ребро; нелегальный переход → IllegalTransition."""
    import uuid
    from datetime import datetime, timedelta

    import pytest as _pt
    from django.utils import timezone

    from apps.booking import services
    from apps.booking.models import Resource
    from apps.booking.state_machine import BookingSM
    from apps.core import status_registry
    from apps.core.fsm import IllegalTransition
    from apps.tenants.tests.factories import TenantFactory

    tenant = TenantFactory(
        site_config={
            "status_defs": {
                "booking": [
                    {
                        "code": "beim_lieferanten",
                        "role": "active",
                        "stage": "in_progress",
                        "blocks_capacity": True,
                    }
                ]
            },
            "status_edges": {
                "booking": [
                    {"src": "confirmed", "dst": "beim_lieferanten"},
                    {"src": "beim_lieferanten", "dst": "fulfilled"},
                ]
            },
        }
    )
    monkeypatch.setattr(status_registry, "_current_tenant", lambda: tenant)

    resource = Resource.objects.create(name=f"R {uuid.uuid4().hex[:6]}")
    start = timezone.make_aware(datetime(2026, 8, 1, 12, 0))
    end = start + timedelta(hours=1)
    b = services.book(resource, start=start, end=end, name="G")
    BookingSM().apply(b, "confirmed")  # built-in
    BookingSM().apply(b, "beim_lieferanten")  # кастом-ребро confirmed→custom легален
    b.refresh_from_db()
    assert b.status == "beim_lieferanten"
    # держит слот (кастом-active в oversell-запросе)
    assert services.overlapping(resource, start, end).filter(pk=b.pk).exists()
    # allowed_targets из кастом-статуса включает кастом-ребро → fulfilled
    assert "fulfilled" in BookingSM().allowed_targets("beim_lieferanten")
    # нелегальный переход (нет built-in и нет кастом-ребра) → IllegalTransition
    with _pt.raises(IllegalTransition):
        BookingSM().apply(b, "no_show")
    # кастом → built-in fulfilled (легально, on_transition встроенного fulfilled)
    BookingSM().apply(b, "fulfilled")
    b.refresh_from_db()
    assert b.status == "fulfilled"


# --- Phase 5: редактор кастом-статусов (кабинет) ------------------------------


def _mgr_req(method, data, tenant):
    from django.contrib.auth import get_user_model
    from django.contrib.messages.middleware import MessageMiddleware
    from django.contrib.sessions.middleware import SessionMiddleware
    from django.test import RequestFactory

    req = getattr(RequestFactory(), method)("/dashboard/status-manager/booking/", data or {})
    SessionMiddleware(lambda r: None).process_request(req)
    MessageMiddleware(lambda r: None).process_request(req)
    req.user = get_user_model()(is_active=True)
    req.tenant = tenant
    return req


def test_status_manager_editor_save_and_render(settings):
    """Phase 5: редактор создаёт кастом-статус (роль→флаги) + ребро; рендерит их обратно."""
    settings.ROOT_URLCONF = "config.urls_tenant"
    from apps.core.views import status_manager, status_manager_save
    from apps.tenants.tests.factories import TenantFactory

    t = TenantFactory(site_config={})
    resp = status_manager_save(
        _mgr_req(
            "post",
            {
                "new_label": "Beim Lieferanten",
                "new_role": "active",
                "edge": ["confirmed|beim_lieferanten"],
                "next": "/dashboard/booking/",
            },
            t,
        ),
        "booking",
    )
    assert resp.status_code == 302 and resp.url == "/dashboard/booking/"
    t.refresh_from_db()
    d = t.site_config["status_defs"]["booking"][0]
    assert d["code"] == "beim_lieferanten" and d["role"] == "active"
    assert d["blocks_capacity"] is True and d["stage"] == "in_progress"  # флаги из роли
    assert {"src": "confirmed", "dst": "beim_lieferanten"} in t.site_config["status_edges"][
        "booking"
    ]
    # редактор рендерит новый статус + чекбокс ребра (checked)
    body = status_manager(_mgr_req("get", {}, t), "booking").content.decode()
    assert "Beim Lieferanten" in body
    assert 'value="confirmed|beim_lieferanten"' in body


# --- SM-3: редактор и apply() для job/ticket/reservation ----------------------


@pytest.mark.parametrize("kind", ["job", "ticket", "reservation"])
def test_status_manager_open_for_all_six_kinds(settings, kind):
    """SM-3 (решение владельца 2026-08-10): свои статусы работают на всех шести
    направлениях — редактор отвечает 200 и сохраняет деф+ребро."""
    settings.ROOT_URLCONF = "config.urls_tenant"
    from apps.core import status_registry
    from apps.core.views import status_manager, status_manager_save
    from apps.tenants.tests.factories import TenantFactory

    t = TenantFactory(site_config={})
    first_builtin = next(iter(status_registry.descriptors(kind)))
    resp = status_manager_save(
        _mgr_req(
            "post",
            {
                "new_label": "Mein Status",
                "new_role": "active",
                "edge": [f"{first_builtin}|mein_status"],
            },
            t,
        ),
        kind,
    )
    assert resp.status_code == 302
    t.refresh_from_db()
    d = t.site_config["status_defs"][kind][0]
    assert d["code"] == "mein_status" and d["role"] == "active"
    assert {"src": first_builtin, "dst": "mein_status"} in t.site_config["status_edges"][kind]
    body = status_manager(_mgr_req("get", {}, t), kind).content.decode()
    assert "Mein Status" in body


def test_status_manager_reservation_builtin_labels_readable(settings):
    """SM-3: у Reservation нет choices — подписи встроенных статусов в редакторе
    берутся из словаря transactions (не сырые коды `pending`/`fulfilled`)."""
    settings.ROOT_URLCONF = "config.urls_tenant"
    from apps.core.views import status_manager
    from apps.tenants.tests.factories import TenantFactory

    t = TenantFactory(
        site_config={
            "status_defs": {
                "reservation": [{"code": "warte_zahlung", "role": "active", "stage": "in_progress"}]
            }
        }
    )
    body = status_manager(_mgr_req("get", {}, t), "reservation").content.decode()
    assert "Reserviert" in body  # pending
    assert "Eingelöst" in body  # fulfilled


def test_status_manager_cancel_role_hides_danger_edges(settings):
    """SM-3 (UX-честность): рёбер ИЗ cancelled-роли не бывает (слой чтения их
    отбросит) — редактор не рисует ни блок «Führt zu» у кастом-отмены, ни
    отменённые источники (включая un-cancel в active-кастом)."""
    settings.ROOT_URLCONF = "config.urls_tenant"
    from apps.core.views import status_manager
    from apps.tenants.tests.factories import TenantFactory

    t = TenantFactory(
        site_config={
            "status_defs": {
                "booking": [
                    {"code": "abgesagt_kulanz", "role": "cancelled", "stage": "terminal"},
                    {"code": "warte_zahlung", "role": "active", "stage": "in_progress"},
                ]
            }
        }
    )
    body = status_manager(_mgr_req("get", {}, t), "booking").content.decode()
    assert 'value="abgesagt_kulanz|cancelled"' not in body  # из кастом-отмены выхода нет
    assert 'value="abgesagt_kulanz|warte_zahlung"' not in body
    assert 'value="cancelled|abgesagt_kulanz"' not in body  # из builtin-danger тоже
    assert 'value="cancelled|warte_zahlung"' not in body  # un-cancel не предлагается
    # легальные рёбра предлагаются: вход в кастомы из живых статусов, выход в отмену
    assert 'value="pending|abgesagt_kulanz"' in body
    assert 'value="warte_zahlung|cancelled"' in body


def test_editor_ticket_done_role_holds_seat(settings):
    """SM-3: свой «завершённый» статус БИЛЕТА держит место (асимметрия attended:
    done-роль у ticket = blocks_capacity, в отличие от booking/stay.fulfilled)."""
    settings.ROOT_URLCONF = "config.urls_tenant"
    from apps.core.views import status_manager_save
    from apps.tenants.tests.factories import TenantFactory

    t = TenantFactory(site_config={})
    status_manager_save(
        _mgr_req("post", {"new_label": "Teilgenommen VIP", "new_role": "done"}, t), "ticket"
    )
    t.refresh_from_db()
    d = t.site_config["status_defs"]["ticket"][0]
    assert d["role"] == "done" and d["blocks_capacity"] is True
    # у order done-роль место не держит (как builtin picked_up)
    t2 = TenantFactory(site_config={})
    status_manager_save(
        _mgr_req("post", {"new_label": "Verpackt", "new_role": "done"}, t2), "order"
    )
    t2.refresh_from_db()
    assert t2.site_config["status_defs"]["order"][0]["blocks_capacity"] is False


def test_editor_resave_preserves_advanced_flags(settings):
    """SM-3: пере-сохранение редактора НЕ теряет продвинутые флаги существующего
    статуса (counts_in_reports ставится только через site_config API — PMS-кейс
    отеля), пока роль не менялась; смена роли → дефолты новой роли."""
    settings.ROOT_URLCONF = "config.urls_tenant"
    from apps.core.views import status_manager_save
    from apps.tenants.tests.factories import TenantFactory

    t = TenantFactory(
        site_config={
            "status_defs": {
                "stay": [
                    {
                        "code": "anzahlung",
                        "label": "Anzahlung erhalten",
                        "role": "active",
                        "stage": "in_progress",
                        "blocks_capacity": True,
                        "counts_in_reports": True,
                    }
                ]
            }
        }
    )
    status_manager_save(
        _mgr_req(
            "post",
            {
                "custom_code": ["anzahlung"],
                "label_anzahlung": "Anzahlung da",
                "role_anzahlung": "active",
            },
            t,
        ),
        "stay",
    )
    t.refresh_from_db()
    d = t.site_config["status_defs"]["stay"][0]
    assert d["label"] == "Anzahlung da"  # label обновился
    assert d["counts_in_reports"] is True  # флаг НЕ потерян
    # смена роли → дефолты новой роли (counts сброшен осознанно)
    status_manager_save(
        _mgr_req(
            "post",
            {
                "custom_code": ["anzahlung"],
                "label_anzahlung": "Anzahlung da",
                "role_anzahlung": "done",
            },
            t,
        ),
        "stay",
    )
    t.refresh_from_db()
    d = t.site_config["status_defs"]["stay"][0]
    assert d["role"] == "done" and d["counts_in_reports"] is False


@pytest.mark.django_db
def test_transition_rule_saved_before_custom_does_not_hide_it(monkeypatch):
    """SM-3: правило переходов (Вариант A), сохранённое ДО создания кастом-статуса,
    НЕ прячет его кнопку с доски — кастом-цели вне правил (их курирует
    status-manager), а normalize_transitions вычищал бы кастом-код из правила при
    каждом сохранении настроек. Кастом-отмена — danger (красная кнопка)."""
    from apps.core import status_registry, transactions, transition_rules
    from apps.tenants.tests.factories import TenantFactory

    tenant = TenantFactory(
        site_config={
            "status_defs": {
                "booking": [
                    {"code": "warte_zahlung", "role": "active", "stage": "in_progress"},
                    {"code": "abgesagt_kulanz", "role": "cancelled", "stage": "terminal"},
                ]
            },
            "status_edges": {
                "booking": [
                    {"src": "confirmed", "dst": "warte_zahlung"},
                    {"src": "confirmed", "dst": "abgesagt_kulanz"},
                ]
            },
            # правило создано «до» кастома: из confirmed показывать только fulfilled
            "transitions": {"booking": {"confirmed": ["fulfilled"]}},
        }
    )
    monkeypatch.setattr(status_registry, "_current_tenant", lambda: tenant)

    subset = transition_rules.subset_for(tenant, "booking")
    actions = transactions.allowed_actions_for("booking", "confirmed", subset)
    by_target = {a["target"]: a for a in actions}
    assert "warte_zahlung" in by_target  # кастом-цель видима вопреки правилу
    assert "abgesagt_kulanz" in by_target
    assert by_target["abgesagt_kulanz"]["danger"] is True  # кастом-отмена красная
    assert "no_show" in by_target  # builtin danger — всегда
    assert "fulfilled" in by_target
    # панель правил предлагает ТОЛЬКО builtin-цели (кастомы — в status-manager)
    rows = transition_rules.editor_rows(tenant, "booking")
    all_dsts = {t["dst"] for r in rows for t in r["targets"]}
    assert "warte_zahlung" not in all_dsts and "abgesagt_kulanz" not in all_dsts


@pytest.mark.django_db
def test_job_custom_status_reachable_via_apply(monkeypatch):
    """SM-3 e2e: свой статус job («Beim Lieferanten») достижим через apply()
    (путь доски/kanban_action) и возвращается в builtin-граф дальше."""
    from apps.core import status_registry
    from apps.jobs import services as job_services
    from apps.jobs.state_machine import JobSM
    from apps.tenants.tests.factories import TenantFactory

    tenant = TenantFactory(
        site_config={
            "status_defs": {
                "job": [{"code": "beim_lieferanten", "role": "active", "stage": "in_progress"}]
            },
            "status_edges": {
                "job": [
                    {"src": "accepted", "dst": "beim_lieferanten"},
                    {"src": "beim_lieferanten", "dst": "done"},
                ]
            },
        }
    )
    monkeypatch.setattr(status_registry, "_current_tenant", lambda: tenant)

    job = job_services.create_job(title="Zaun", name="Kunde", email="k@test.de")
    JobSM().apply(job, "quoted")
    JobSM().apply(job, "accepted")
    JobSM().apply(job, "beim_lieferanten")  # кастом-ребро
    job.refresh_from_db()
    assert job.status == "beim_lieferanten"
    assert "done" in JobSM().allowed_targets("beim_lieferanten")
    JobSM().apply(job, "done")  # обратно в builtin-граф (commit_stock и пр. — on_transition)
    job.refresh_from_db()
    assert job.status == "done"
