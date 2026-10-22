"""KA-H1 (2026-10-22): защита записывающих адресов кабинета.

Нашла инвентаризация KA-0:
* `status_manager_save` не имел НИ `@login_required`, НИ `@require_POST` — аноним
  простым GET по ссылке стирал свои статусы и переходы бизнеса;
* `invoice_mahnung` (поднимает ступень напоминания и шлёт письмо клиенту) и
  `set_presence_view` меняли данные по GET.

Плюс замок класса: каждая функция-вьюха под кабинетными префиксами обёрнута
`login_required` — замок `test_orphan_decorators` ловит декоратор, «съеденный»
хелпером, но не вьюху, у которой декоратора не было никогда.
"""

import uuid

import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser
from django.contrib.messages.middleware import MessageMiddleware
from django.contrib.sessions.middleware import SessionMiddleware
from django.test import RequestFactory
from django.urls import get_resolver
from django.urls.resolvers import URLResolver

from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db

CABINET_PREFIXES = ("dashboard/", "catalog/", "promotions/", "imports/", "crm/")
# Осознанные исключения: вьюхи под кабинетным префиксом, которые обязаны работать
# без входа. Сейчас таких нет — новая запись требует причины рядом.
PUBLIC_UNDER_CABINET = frozenset()


def _req(method, path, data=None, *, user=True, tenant=None):
    request = getattr(RequestFactory(), method)(path, data or {})
    SessionMiddleware(lambda r: None).process_request(request)
    MessageMiddleware(lambda r: None).process_request(request)
    if user:
        o = uuid.uuid4().hex[:8]
        request.user = get_user_model().objects.create_user(
            username=f"h1-{o}", email=f"h1-{o}@t.de", password="pw12345678"
        )
    else:
        request.user = AnonymousUser()
    request.tenant = tenant
    return request


# --- status_manager_save -----------------------------------------------------------------


@pytest.mark.parametrize("method", ["get", "post"])
def test_anonymous_cannot_save_statuses(settings, method):
    settings.ROOT_URLCONF = "config.urls_tenant"
    from apps.core.views import status_manager_save

    before = {"status_defs": {"booking": [{"code": "x1", "role": "active", "label": "X"}]}}
    tenant = TenantFactory(site_config=dict(before))
    resp = status_manager_save(
        _req(method, "/dashboard/status-manager/booking/save/", user=False, tenant=tenant),
        kind="booking",
    )
    assert resp.status_code in (302, 405)
    if resp.status_code == 302:
        assert "login" in resp["Location"]
    tenant.refresh_from_db()
    assert tenant.site_config == before


def test_status_save_by_get_is_rejected(settings):
    settings.ROOT_URLCONF = "config.urls_tenant"
    from apps.core.views import status_manager_save

    before = {"status_defs": {"booking": [{"code": "x1", "role": "active", "label": "X"}]}}
    tenant = TenantFactory(site_config=dict(before))
    resp = status_manager_save(
        _req("get", "/dashboard/status-manager/booking/save/", tenant=tenant), kind="booking"
    )
    assert resp.status_code == 405
    tenant.refresh_from_db()
    assert tenant.site_config == before


# --- invoice_mahnung / set_presence -------------------------------------------------------


def test_mahnung_by_get_has_no_effect():
    from apps.finance import views as finance_views
    from apps.finance.tests.test_erp34_bills import _issued_invoice, _tenant
    from apps.notifications.models import Notification

    tenant = _tenant()
    inv = _issued_invoice()
    resp = finance_views.invoice_mahnung(
        _req("get", "/dashboard/finance/", tenant=tenant), pk=inv.pk
    )
    assert resp.status_code == 405
    inv.refresh_from_db()
    assert inv.mahn_level == 0
    assert not Notification.objects.filter(type="invoice_mahnung").exists()


def test_presence_by_get_has_no_effect(settings):
    settings.ROOT_URLCONF = "config.urls_tenant"
    from apps.core import views as core_views

    tenant = TenantFactory(site_config={"presence": {"mode": "on"}})
    resp = core_views.set_presence_view(_req("get", "/dashboard/presence/", tenant=tenant))
    assert resp.status_code == 405
    tenant.refresh_from_db()
    assert tenant.site_config["presence"] == {"mode": "on"}


# --- замок класса ----------------------------------------------------------------------


def _walk(resolver, prefix=""):
    for p in resolver.url_patterns:
        if isinstance(p, URLResolver):
            yield from _walk(p, prefix + str(p.pattern))
        else:
            yield prefix + str(p.pattern), p


def _guarded(func, seen=None):
    """Обёрнута ли функция проверкой входа (`login_required` → `user_passes_test`)."""
    seen = seen if seen is not None else set()
    if id(func) in seen:
        return False
    seen.add(id(func))
    code = getattr(func, "__code__", None)
    if code and ("is_authenticated" in code.co_names or "redirect_to_login" in code.co_names):
        return True
    for cell in getattr(func, "__closure__", None) or ():
        try:
            value = cell.cell_contents
        except ValueError:  # pragma: no cover — пустая ячейка
            continue
        if callable(value) and _guarded(value, seen):
            return True
    wrapped = getattr(func, "__wrapped__", None)
    return bool(wrapped and _guarded(wrapped, seen))


def test_guard_detector_sees_login_required():
    from django.contrib.auth.decorators import login_required
    from django.views.decorators.http import require_POST

    def bare(request):
        return None

    assert not _guarded(bare)
    assert not _guarded(require_POST(bare))
    assert _guarded(login_required(bare))
    assert _guarded(require_POST(login_required(bare)))
    assert _guarded(login_required(require_POST(bare)))


def test_every_cabinet_view_requires_login():
    naked = []
    for path, pattern in _walk(get_resolver("config.urls_tenant")):
        if not path.startswith(CABINET_PREFIXES):
            continue
        callback = pattern.callback
        if getattr(callback, "view_class", None):  # RedirectView и т.п. — без данных
            continue
        if pattern.name in PUBLIC_UNDER_CABINET:
            continue
        if not _guarded(callback):
            naked.append(f"{path} ({pattern.name})")
    assert not naked, "вьюхи кабинета без @login_required:\n" + "\n".join(naked)
