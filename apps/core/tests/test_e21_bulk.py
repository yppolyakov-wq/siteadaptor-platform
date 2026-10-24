"""KA-12 E2.1: массовая смена статуса из списка продаж + Lieferscheine пачкой.

Сервер не доверяет клиенту: пересечение переходов считается заново, цель вне
него отклоняет запрос целиком; опасная цель требует подтверждения и лимита;
каждый объект идёт штатным путём одиночной кнопки (`apply_action`)."""

import pytest
from django.contrib.auth.models import AnonymousUser
from django.contrib.messages.middleware import MessageMiddleware
from django.contrib.sessions.middleware import SessionMiddleware
from django.test import RequestFactory

from apps.core import bulk_actions, views
from apps.core.tests.test_kanban import _make_order, _User

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _urlconf(settings):
    settings.ROOT_URLCONF = "config.urls_tenant"


@pytest.fixture
def tenant():
    from apps.tenants.tests.factories import TenantFactory

    return TenantFactory.build(schema_name="public")


def _status(order):
    order.refresh_from_db()
    return order.status


def test_changes_all_selected_through_the_single_path(tenant):
    a, b = _make_order(), _make_order()
    res = bulk_actions.apply_bulk(tenant, "order", [a.pk, b.pk], "confirmed")
    assert res.changed == 2
    assert _status(a) == _status(b) == "confirmed"


def test_repeated_submit_changes_nothing_new(tenant):
    a = _make_order()
    bulk_actions.apply_bulk(tenant, "order", [a.pk], "confirmed")
    res = bulk_actions.apply_bulk(tenant, "order", [a.pk], "confirmed")
    assert res.changed == 0 and res.already == 1


def test_target_outside_intersection_refuses_everything(tenant):
    a, b = _make_order(), _make_order()
    bulk_actions.apply_bulk(tenant, "order", [a.pk], "confirmed")
    # a: confirmed → ready допустимо; b: new → ready нет
    with pytest.raises(bulk_actions.BulkRefused):
        bulk_actions.apply_bulk(tenant, "order", [a.pk, b.pk], "ready")
    assert _status(a) == "confirmed" and _status(b) == "new"


def test_danger_requires_confirm(tenant):
    a = _make_order()
    with pytest.raises(bulk_actions.BulkRefused):
        bulk_actions.apply_bulk(tenant, "order", [a.pk], "cancelled")
    assert _status(a) == "new"
    res = bulk_actions.apply_bulk(tenant, "order", [a.pk], "cancelled", confirm=True)
    assert res.changed == 1 and _status(a) == "cancelled"


def test_danger_is_capped(tenant, monkeypatch):
    monkeypatch.setattr(bulk_actions, "MAX_DANGER", 1)
    a, b = _make_order(), _make_order()
    with pytest.raises(bulk_actions.BulkRefused):
        bulk_actions.apply_bulk(tenant, "order", [a.pk, b.pk], "cancelled", confirm=True)
    assert _status(a) == _status(b) == "new"


def test_too_many_ids_refused(tenant):
    import uuid

    with pytest.raises(bulk_actions.BulkRefused):
        bulk_actions.apply_bulk(
            tenant, "order", [uuid.uuid4() for _ in range(bulk_actions.MAX_IDS + 1)], "confirmed"
        )


def test_junk_and_unknown_ids_are_ignored(tenant):
    import uuid

    a = _make_order()
    res = bulk_actions.apply_bulk(
        tenant, "order", ["x'; drop", "", str(uuid.uuid4()), str(a.pk), str(a.pk)], "confirmed"
    )
    assert res.changed == 1


def test_shipped_is_not_offered_in_bulk():
    from types import SimpleNamespace

    obj = SimpleNamespace(status="ready", is_delivery=True)
    targets = {a["target"] for a in bulk_actions.common_actions("order", [obj], None)}
    assert "shipped" not in targets


def test_partial_success_reports_skip_reason(tenant, monkeypatch):
    from apps.core import transactions
    from apps.core.fsm import PaymentRequired

    a, b = _make_order(), _make_order()
    real = transactions.apply_action

    def fake(kind, obj, target, **kw):
        if obj.pk == b.pk:
            raise PaymentRequired(type(obj), obj.status, target)
        return real(kind, obj, target, **kw)

    monkeypatch.setattr(transactions, "apply_action", fake)
    res = bulk_actions.apply_bulk(tenant, "order", [a.pk, b.pk], "confirmed")
    assert res.changed == 1 and sum(res.skipped.values()) == 1
    assert _status(a) == "confirmed" and _status(b) == "new"


def test_inactive_module_is_refused(tenant, monkeypatch):
    a = _make_order()
    monkeypatch.setattr(type(tenant), "is_module_active", lambda self, key: False)
    with pytest.raises(bulk_actions.BulkRefused):
        bulk_actions.apply_bulk(tenant, "order", [a.pk], "confirmed")


def _post(data, user=None):
    req = RequestFactory().post("/dashboard/verkaeufe/bulk/", data)
    SessionMiddleware(lambda r: None).process_request(req)
    MessageMiddleware(lambda r: None).process_request(req)
    req.user = user or _User()
    from apps.tenants.tests.factories import TenantFactory

    req.tenant = TenantFactory.build(schema_name="public")
    return req


def test_view_requires_login_and_post():
    resp = views.sales_bulk_action(_post({"kind": "order"}, user=AnonymousUser()))
    assert resp.status_code == 302 and "login" in resp["Location"]
    req = RequestFactory().get("/dashboard/verkaeufe/bulk/")
    req.user = _User()
    assert views.sales_bulk_action(req).status_code == 405


def test_view_applies_and_returns_to_next():
    a = _make_order()
    resp = views.sales_bulk_action(
        _post(
            {
                "kind": "order",
                "ids": [str(a.pk)],
                "action": "confirmed",
                "next": "/dashboard/verkaeufe/?tab=order&view=liste",
            }
        )
    )
    assert resp.status_code == 302
    assert resp["Location"] == "/dashboard/verkaeufe/?tab=order&view=liste"
    assert _status(a) == "confirmed"


@pytest.mark.parametrize(
    "bad", ["//evil.com/", "/\\evil.com/", "https://evil.com/", "/\t/evil.com/"]
)
def test_view_rejects_foreign_next(bad):
    a = _make_order()
    resp = views.sales_bulk_action(
        _post({"kind": "order", "ids": [str(a.pk)], "action": "confirmed", "next": bad})
    )
    assert "evil.com" not in resp["Location"]


def test_delivery_notes_one_pdf_page_per_order():
    from apps.orders import views as order_views

    orders = [_make_order() for _ in range(3)]
    req = _post({"ids": [str(o.pk) for o in orders]})
    resp = order_views.delivery_notes_pdf(req)
    assert resp.status_code == 200 and resp["Content-Type"] == "application/pdf"
    import re

    pages = re.findall(rb"/Type /Page[^s]", resp.content)
    assert len(pages) == 3


def test_delivery_notes_require_login():
    from apps.orders import views as order_views

    resp = order_views.delivery_notes_pdf(_post({"ids": []}, user=AnonymousUser()))
    assert resp.status_code == 302 and "login" in resp["Location"]


def test_refund_callback_runs_right_after_each_refund(tenant, monkeypatch):
    """Ревью: остаток наличными лежит в contextvar до СЛЕДУЮЩЕГО возврата — флеш
    обязан идти сразу после своей сделки, а не одним циклом в конце."""
    from apps.core import refunds, transactions

    a, b = _make_order(), _make_order()
    order_of_events = []

    def fake(kind, obj, target, **kw):
        order_of_events.append(("apply", obj.pk))
        return refunds.RefundResult.REFUNDED if obj.pk == a.pk else refunds.RefundResult.FAILED

    monkeypatch.setattr(transactions, "apply_action", fake)
    res = bulk_actions.apply_bulk(
        tenant,
        "order",
        [a.pk, b.pk],
        "confirmed",
        on_refund=lambda r: order_of_events.append(("flash", r)),
    )
    assert [e[0] for e in order_of_events] == ["apply", "flash", "apply", "flash"]
    assert res.check_codes == [b.reference_code]


def test_unexpected_error_skips_one_and_reports(tenant, monkeypatch):
    from apps.core import transactions

    a, b = _make_order(), _make_order()
    real = transactions.apply_action

    def fake(kind, obj, target, **kw):
        if obj.pk == a.pk:
            raise RuntimeError("boom")
        return real(kind, obj, target, **kw)

    monkeypatch.setattr(transactions, "apply_action", fake)
    res = bulk_actions.apply_bulk(tenant, "order", [a.pk, b.pk], "confirmed")
    assert res.changed == 1 and sum(res.skipped.values()) == 1
    assert _status(a) == "new" and _status(b) == "confirmed"
