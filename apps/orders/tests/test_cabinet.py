"""Track D / D2b: кабинет заказов — список/карточка/действия, письма по
статусам (Notification + БД-дедуп), оплата вручную, 360° в CRM."""

import uuid

import pytest
from django.contrib.auth import get_user_model
from django.contrib.messages.middleware import MessageMiddleware
from django.contrib.sessions.middleware import SessionMiddleware
from django.test import RequestFactory

from apps.catalog.tests.factories import ProductFactory
from apps.notifications.models import Notification
from apps.orders import services, views
from apps.orders.models import Order
from apps.orders.state_machine import OrderSM

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _tenant_urlconf(settings):
    settings.ROOT_URLCONF = "config.urls_tenant"


def _req(method="get", path="/dashboard/orders/", data=None):
    request = getattr(RequestFactory(), method)(path, data or {})
    SessionMiddleware(lambda r: None).process_request(request)
    MessageMiddleware(lambda r: None).process_request(request)
    owner = uuid.uuid4().hex[:8]
    request.user = get_user_model().objects.create_user(
        username=f"o-{owner}", email=f"o-{owner}@test.de", password="pw12345678"
    )
    return request


def _order(email=None):
    return services.create_order(
        items=[(ProductFactory(name={"de": "Brot"}), 2)],
        name="Kunde K",
        email=email or f"k-{uuid.uuid4().hex[:8]}@test.de",
    )


# --- письма ----------------------------------------------------------------------


def test_create_order_enqueues_customer_email():
    order = _order()
    notification = Notification.objects.get(dedupe_key=f"order:{order.id}:created:customer")
    assert notification.type == "order_created"
    assert order.reference_code in notification.payload["body"]


def test_transitions_enqueue_emails_with_dedupe():
    order = _order()
    sm = OrderSM()
    order = sm.apply(order, "confirmed")
    order = sm.apply(order, "ready")
    assert Notification.objects.filter(dedupe_key=f"order:{order.id}:confirmed:customer").exists()
    ready = Notification.objects.get(dedupe_key=f"order:{order.id}:ready:customer")
    assert "abholbereit" in ready.payload["body"].lower()
    # повтор того же статуса — no-op, дубль письма не создаётся (БД-дедуп)
    sm.apply(order, "ready")
    assert Notification.objects.filter(dedupe_key=f"order:{order.id}:ready:customer").count() == 1


# --- кабинет ---------------------------------------------------------------------


def _verkaeufe_req(data=None):
    """W10-6: список заказов живёт на Verkäufe — характеризация тела там."""
    from apps.tenants.tests.factories import TenantFactory

    req = _req(path="/dashboard/verkaeufe/", data={"tab": "order", "view": "liste", **(data or {})})
    req.tenant = TenantFactory.build(
        business_type="shop", disabled_modules=["events", "stays", "booking", "jobs"]
    )
    return req


def test_order_list_redirects_and_verkaeufe_liste_filters():
    """W10-6: легаси-список — 302 с сохранением GET; тело фильтрует на цели."""
    from apps.core import views as core_views

    order = _order()
    resp = views.order_list(_req())
    assert resp.status_code == 302
    assert resp["Location"] == "/dashboard/verkaeufe/?tab=order&view=liste"
    resp = views.order_list(_req(data={"status": "cancelled"}))
    assert "status=cancelled" in resp["Location"]

    body = core_views.verkaeufe(_verkaeufe_req()).content.decode()
    assert order.reference_code in body and "Brot" in body
    body = core_views.verkaeufe(_verkaeufe_req({"status": "cancelled"})).content.decode()
    assert order.reference_code not in body


def test_order_detail_shows_items_and_actions():
    order = _order()
    body = views.order_detail(_req(path=f"/dashboard/orders/{order.pk}/"), pk=order.pk)
    body = body.content.decode()
    assert order.reference_code in body
    # SH-2 (осознанная переписка): позиции незакрытого заказа теперь РЕДАКТИРУЕМЫ —
    # вместо строки «2× Brot» поле количества и название рядом.
    assert 'value="2"' in body and "Brot" in body
    assert 'name="action" value="items"' in body
    assert 'value="confirmed"' in body and 'value="cancelled"' in body
    assert 'value="ready"' not in body  # из new сразу в ready нельзя


def test_closed_order_detail_is_read_only():
    """SH-2: у закрытого заказа склад уже возвращён — правку не показываем."""
    from apps.orders.state_machine import OrderSM

    order = _order()
    OrderSM().apply(order, "cancelled")
    body = views.order_detail(_req(path=f"/dashboard/orders/{order.pk}/"), pk=order.pk)
    body = body.content.decode()
    # VF-2: строка позиции = «№ · название · кол-во × цена/шт · сумма»
    assert "Brot" in body and "2 ×" in body  # обычная строка-снимок
    assert 'name="action" value="items"' not in body


def test_order_action_transitions_and_payment():
    order = _order()
    response = views.order_action(
        _req("post", f"/dashboard/orders/{order.pk}/action/", {"action": "confirmed"}), pk=order.pk
    )
    assert response.status_code == 302
    order.refresh_from_db()
    assert order.status == "confirmed"

    views.order_action(
        _req("post", f"/dashboard/orders/{order.pk}/action/", {"action": "mark_paid"}), pk=order.pk
    )
    order.refresh_from_db()
    assert order.payment_state == "paid"

    # запрещённый переход не меняет статус
    views.order_action(
        _req("post", f"/dashboard/orders/{order.pk}/action/", {"action": "picked_up"}), pk=order.pk
    )
    order.refresh_from_db()
    assert order.status == "confirmed"


def test_crm_card_shows_orders():
    from apps.crm.views import customer_detail

    order = _order(email="kunde360@test.de")
    body = customer_detail(
        _req(path=f"/crm/{order.customer.pk}/"), pk=order.customer.pk
    ).content.decode()
    assert order.reference_code in body


def test_nav_includes_orders_when_active():
    from apps.core import modules
    from apps.core.templatetags.cabinet import HUB_TABS
    from apps.tenants.tests.factories import TenantFactory

    tenant = TenantFactory.build()
    keys = [s.key for s in modules.active_modules(tenant)]
    assert "orders" in keys
    # S2/W-CL: заказы — не пункт сайдбара и не таб board-хаба; вход — единая
    # страница продаж (vkладка kind=order у primary=catalog).
    spec = modules.get_module("orders")
    assert spec.nav_items == ()
    assert not any(t[0] == "orders:order-list" for t in HUB_TABS["board"])
    from apps.core import orders_view as ov

    assert ov.entry_url_name(tenant) == "verkaeufe"


# --- FB-4a: свои имена статусов заказа (кабинет-отображение) -----------------------


def test_status_labels_save_render_and_reset():
    """Сохранение своих имён через generic status-labels-save (W9-8: экран «Abläufe»;
    targeted-write, прочие ключи целы) + рендер в списке/детали; пустая форма снимает
    ключ (presence-minimal)."""
    from apps.core import views as core_views
    from apps.tenants.tests.factories import TenantFactory

    tenant = TenantFactory(site_config={"notify": {"customer": {"email": True}}})
    order = _order()
    req = _req("post", "/dashboard/status-labels/order/", {"label_new": "Eingegangen 📥"})
    req.tenant = tenant
    core_views.status_labels_save(req, "order")
    tenant.refresh_from_db()
    assert tenant.site_config["status_labels"]["order"]["new"] == "Eingegangen 📥"
    assert tenant.site_config["notify"] == {
        "customer": {"email": True}
    }  # прочие ключи целы (урок W0)

    # W10-6: рендер списка — на Verkäufe (легаси-вьюха теперь 302).
    from apps.core import views as core_views

    req = _req(path="/dashboard/verkaeufe/", data={"tab": "order", "view": "liste"})
    req.tenant = tenant
    assert "Eingegangen 📥" in core_views.verkaeufe(req).content.decode()
    req = _req(path=f"/dashboard/orders/{order.pk}/")
    req.tenant = tenant
    assert "Eingegangen 📥" in views.order_detail(req, order.pk).content.decode()
    # без кастома — дефолт (fallback тега). I18N-1 (2026-07-30): метки STATUSES
    # обёрнуты в gettext_lazy, поэтому сверяемся с ПЕРЕВЕДЁННЫМ значением реестра,
    # а не с английским литералом (раньше замок пинил непереведённость).
    req = _req(path="/dashboard/verkaeufe/", data={"tab": "order", "view": "liste"})
    req.tenant = TenantFactory(slug="t2")
    default_label = str(dict(Order.STATUSES)[Order.STATUS_NEW])
    assert default_label in core_views.verkaeufe(req).content.decode()

    req = _req("post", "/dashboard/status-labels/order/", {})
    req.tenant = tenant
    core_views.status_labels_save(req, "order")
    tenant.refresh_from_db()
    assert "status_labels" not in tenant.site_config


def test_normalize_status_labels_validation():
    """Мусор отброшен; неизвестные kind/статусы игнорируются; пусто → ключа нет
    (golden-паритет)."""
    from apps.tenants.siteconfig import normalize, normalize_status_labels

    assert normalize_status_labels(None) == {}
    assert normalize_status_labels({"order": {"new": "  Neu!  ", "bogus": "x"}}) == {
        "order": {"new": "Neu!"}
    }
    assert normalize_status_labels({"unknown_kind": {"new": "x"}}) == {}
    assert "status_labels" not in normalize({})
    out = normalize({"status_labels": {"order": {"ready": "Fertig zum Abholen"}}})
    assert out["status_labels"] == {"order": {"ready": "Fertig zum Abholen"}}


def test_order_items_one_line_with_unit_price():
    """VF-2 (фидбэк 2026-08-24): позиция одной строкой — порядковый номер,
    название, количество, цена за штуку, сумма по позиции."""
    order = _order()
    body = views.order_detail(_req(path=f"/dashboard/orders/{order.pk}/"), pk=order.pk)
    body = body.content.decode()
    item = order.items.first()
    # DE-грабля чисел (урок ST-1b): рендер локализует Decimal запятой.
    unit = str(item.unit_price).replace(".", ",")
    total = str(item.line_total).replace(".", ",")
    assert f"× {unit}" in body  # цена за штуку
    assert total in body  # сумма по позиции
