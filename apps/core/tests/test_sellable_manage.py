"""FB-8: единый кабинетный список продаваемых сущностей (Angebote).

Обзор всех sellable-kind в одном месте: секции по активным модулям (с items), тумблер
видимости (product/service/stay/combo — простой is_active; event публикуется через FSM),
переход к РОДНОЙ форме. jobs — НЕ sellable. Единый CRUD НЕ делаем.
"""

from datetime import timedelta
from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from django.contrib.messages.middleware import MessageMiddleware
from django.contrib.sessions.middleware import SessionMiddleware
from django.http import Http404
from django.test import RequestFactory
from django.utils import timezone

from apps.booking.models import Service
from apps.catalog.tests.factories import ProductFactory
from apps.core import sellable_manage as sm
from apps.core.views import sellable_manage, sellable_visibility
from apps.events.models import Event
from apps.stays.models import StayUnit
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db

_ALL = ["catalog", "booking", "stays", "events"]


@pytest.fixture(autouse=True)
def _urlconf(settings):
    settings.ROOT_URLCONF = "config.urls_tenant"


def _req(method="get", path="/dashboard/angebote/", data=None, tenant=None):
    req = getattr(RequestFactory(), method)(path, data or {})
    SessionMiddleware(lambda r: None).process_request(req)
    MessageMiddleware(lambda r: None).process_request(req)
    req.user = get_user_model()(is_active=True)
    if tenant is not None:
        req.tenant = tenant
    return req


def _service():
    return Service.objects.create(name="Haarschnitt", price_cents=3000)


def _stay():
    return StayUnit.objects.create(name="Zimmer 1", price_cents=8000)


def _event(status=Event.STATUS_PUBLISHED):
    return Event.objects.create(
        title="Workshop",
        starts_at=timezone.now() + timedelta(days=3),
        status=status,
        price_cents=2000,
        capacity=10,
    )


# --- секции -------------------------------------------------------------------


def test_sections_cover_active_kinds_with_items():
    t = TenantFactory(enabled_modules=_ALL)
    ProductFactory(base_price=Decimal("5.00"))
    _service()
    _stay()
    _event()
    kinds = {s["kind"] for s in sm.sellable_manage_sections_for(t)}
    assert kinds == {"product", "service", "stay", "event"}  # combo пуст → секции нет


def test_section_gated_by_module_and_hides_empty():
    # booking/stays/events отключены → в списке только catalog-товар (гейт по модулю).
    t = TenantFactory(disabled_modules=["booking", "stays", "events"])
    ProductFactory(base_price=Decimal("3.00"))
    _service()  # booking выкл → услуга не в списке
    sections = sm.sellable_manage_sections_for(t)
    assert {s["kind"] for s in sections} == {"product"}
    # у товара 1 позиция; пустые kind (combo) не появляются
    assert sections[0]["count"] == 1


def test_managed_row_fields():
    t = TenantFactory(enabled_modules=["stays"])
    unit = _stay()
    section = sm.sellable_manage_sections_for(t)[0]
    row = section["items"][0]
    assert row.kind == "stay" and row.pk == unit.pk
    assert row.name == "Zimmer 1"
    assert row.is_visible is True and row.can_toggle is True
    assert "unterkunft" in row.edit_url or "units" in row.edit_url  # ведёт на родной экран


def test_event_row_is_status_not_toggle():
    t = TenantFactory(enabled_modules=["events"])
    _event(status=Event.STATUS_DRAFT)
    row = sm.sellable_manage_sections_for(t)[0]["items"][0]
    assert row.can_toggle is False  # событие публикуется через FSM, не тумблером
    assert row.is_visible is False  # draft → не опубликовано
    assert row.status_label  # показываем статус


# --- add_options --------------------------------------------------------------


def test_add_options_for_active_kinds():
    t = TenantFactory(disabled_modules=["events"])  # events выкл
    kinds = {a["kind"] for a in sm.add_options(t)}
    assert "product" in kinds and "stay" in kinds
    assert "event" not in kinds  # events выкл → нет кнопки создания


# --- toggle -------------------------------------------------------------------


def test_toggle_visibility_flips_and_event_404():
    unit = _stay()
    assert unit.is_active is True
    sm.toggle_visibility("stay", unit.pk)
    unit.refresh_from_db()
    assert unit.is_active is False
    sm.toggle_visibility("stay", unit.pk)
    unit.refresh_from_db()
    assert unit.is_active is True
    with pytest.raises(Http404):
        sm.toggle_visibility("event", _event().pk)  # событие — не тумблер


# --- вьюхи --------------------------------------------------------------------


def test_view_renders_sections():
    t = TenantFactory(enabled_modules=_ALL)
    ProductFactory(base_price=Decimal("5.00"), name={"de": "Brot"})
    _service()
    body = sellable_manage(_req(tenant=t)).content.decode()
    assert "Angebote" in body
    assert "Brot" in body and "Haarschnitt" in body
    assert "Leistungen" in body  # заголовок секции услуг


def test_visibility_view_flips_and_redirects():
    t = TenantFactory(enabled_modules=["stays"])
    unit = _stay()
    resp = sellable_visibility(_req("post", tenant=t), "stay", unit.pk)
    assert resp.status_code == 302 and resp.url.endswith("/angebote/")
    unit.refresh_from_db()
    assert unit.is_active is False


def test_view_renders_cards_by_default():
    """ST-5a: без classic_ui — карточный грид (aspect-фото, card-партиал)."""
    t = TenantFactory(enabled_modules=_ALL)
    ProductFactory(base_price=Decimal("5.00"), name={"de": "Brot"})
    body = sellable_manage(_req(tenant=t)).content.decode()
    assert "grid grid-cols-2" in body and "aspect-video" in body
    assert "divide-y divide-gray-100" not in body  # старый список скрыт
    assert "sellable-visibility" in body or "Sichtbar" in body  # тумблер жив


def test_view_classic_keeps_row_list():
    """ST-5a: classic_ui=True — прежний divide-y список (Р7, легаси цел)."""
    t = TenantFactory(enabled_modules=_ALL, site_config={"classic_ui": True})
    ProductFactory(base_price=Decimal("5.00"), name={"de": "Brot"})
    body = sellable_manage(_req(tenant=t)).content.decode()
    assert "divide-y divide-gray-100" in body
    assert "aspect-video" not in body
