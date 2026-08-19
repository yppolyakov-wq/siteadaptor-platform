"""X8 (план x8-palette-data-plan-2026-08-19): Ctrl+K ищет по ДАННЫМ.

Инварианты: аноним не получает данные (класс X0), выключенный модуль не отдаёт
свою секцию, короткий запрос не ходит в БД, лимиты соблюдаются.
"""

from uuid import uuid4

import pytest
from django.contrib.auth import get_user_model
from django.test import RequestFactory

from apps.core import palette_search as ps
from apps.core.modules import default_disabled_for
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _urlconf(settings):
    settings.ROOT_URLCONF = "config.urls_tenant"


def _tenant(business_type="friseur", enable=()):
    off = [m for m in default_disabled_for(business_type) if m not in enable]
    return TenantFactory(
        slug=f"x8-{business_type[:8]}-{uuid4().hex[:4]}",
        name="X8",
        business_type=business_type,
        disabled_modules=off,
    )


def _user():
    return get_user_model().objects.create_user(
        username=f"x8-{uuid4().hex[:8]}", email=f"x8-{uuid4().hex[:8]}@t.de", password="pw12345678"
    )


def test_short_query_returns_nothing():
    assert ps.search(_tenant(), "") == []
    assert ps.search(_tenant(), "a") == []


def test_finds_deal_by_customer_name():
    """Сценарий №1 владельца: «найти заказ фрау Мюллер»."""
    from django.utils import timezone

    from apps.booking.models import Booking, Resource, Service
    from apps.crm.models import Customer

    t = _tenant("friseur", enable=("crm",))
    svc = Service.objects.create(name="Haarschnitt", duration_minutes=30)
    res = Resource.objects.create(name="Stuhl 1")
    cust = Customer.objects.create(name="Frau Müller", email="mueller@t.de")
    now = timezone.now()
    Booking.objects.create(
        service=svc, resource=res, customer=cust, start=now, end=now, reference_code="B-X8A"
    )

    sections = {s["key"]: s for s in ps.search(t, "müller")}
    assert "deals" in sections
    assert "B-X8A" in sections["deals"]["items"][0]["sub"]
    assert sections["deals"]["items"][0]["url"]
    # клиент тоже находится (модуль crm активен)
    assert "customers" in sections


def test_sellables_found_by_name():
    from apps.booking.models import Service

    t = _tenant("friseur")
    Service.objects.create(name="Färben", duration_minutes=60)
    sections = {s["key"]: s for s in ps.search(t, "färb")}
    assert [i["label"] for i in sections["sellables"]["items"]] == ["Färben"]


def test_crm_section_gated_by_module():
    from apps.crm.models import Customer

    Customer.objects.create(name="Frau Müller", email="m@t.de")
    t = _tenant("friseur")  # crm выключен пресетом архетипа
    assert not t.is_module_active("crm")
    assert "customers" not in {s["key"] for s in ps.search(t, "müller")}


def test_endpoint_requires_login():
    from django.contrib.auth.models import AnonymousUser

    from apps.core import views as core_views
    from config import urls_tenant  # noqa: F401

    req = RequestFactory().get("/dashboard/palette-search/", {"q": "test"})
    req.tenant, req.user = _tenant(), AnonymousUser()
    resp = core_views.palette_search(req)
    assert resp.status_code == 302  # редирект на логин, не 200 с данными


def test_endpoint_returns_json_sections():
    import json

    from apps.booking.models import Service
    from apps.core import views as core_views

    t = _tenant("friseur")
    Service.objects.create(name="Föhnen", duration_minutes=15)
    req = RequestFactory().get("/dashboard/palette-search/", {"q": "föhn"})
    req.tenant, req.user = t, _user()
    payload = json.loads(core_views.palette_search(req).content)
    labels = [i["label"] for sec in payload["sections"] for i in sec["items"]]
    assert "Föhnen" in labels
    # подписи секций — строки (lazy сериализован явно)
    assert all(isinstance(sec["label"], str) for sec in payload["sections"])


def test_total_cap_respected():
    from apps.booking.models import Service

    t = _tenant("friseur")
    for i in range(12):
        Service.objects.create(name=f"Test-Leistung {i}", duration_minutes=30)
    total = sum(len(s["items"]) for s in ps.search(t, "test-leistung"))
    assert 0 < total <= ps.TOTAL_CAP
