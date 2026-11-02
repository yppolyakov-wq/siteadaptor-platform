"""SP-3 (аудит пространства 2026-11-02): экран ресурсов — свёрнутые карточки со сводкой.

У 9 столов ресторана экран растягивался до ~5800 px: каждое правило дня — строкой,
все формы раскрыты. Теперь одинаковые окна склеены («Mo–Su 11:00–22:00»), карточка
— <details> со сводкой; формы остаются в DOM (W0), после сохранения раскрыта та же.
"""

import uuid
from datetime import time

import pytest
from django.contrib.auth import get_user_model
from django.contrib.messages.middleware import MessageMiddleware
from django.contrib.sessions.middleware import SessionMiddleware
from django.test import RequestFactory
from django.utils import translation

from apps.booking import hours_summary, views
from apps.booking.models import AvailabilityRule, Resource
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _urlconf(settings):
    settings.ROOT_URLCONF = "config.urls_tenant"


@pytest.fixture(autouse=True)
def _english():
    # Подписи дней — переводимые msgid календаря («Mo/Tu/…»); язык фиксируем явно.
    with translation.override("en"):
        yield


def _resource(days=range(7), start=time(11), end=time(22)):
    r = Resource.objects.create(
        name=f"Tisch {uuid.uuid4().hex[:4]}", type=Resource.TYPE_TABLE, capacity=1, seats=4
    )
    for d in days:
        AvailabilityRule.objects.create(
            resource=r, weekday=d, start_time=start, end_time=end, slot_minutes=30
        )
    return r


def _req(method="get", data=None, path="/dashboard/booking/ressourcen/"):
    request = getattr(RequestFactory(), method)(path, data or {})
    SessionMiddleware(lambda r: None).process_request(request)
    MessageMiddleware(lambda r: None).process_request(request)
    request.user = get_user_model().objects.create_user(
        username=f"u-{uuid.uuid4().hex[:8]}", password="pw1234567"
    )
    request.tenant = TenantFactory.build(business_type="restaurant", disabled_modules=[])
    return request


def test_identical_windows_merge_into_day_ranges():
    r = _resource()
    AvailabilityRule.objects.create(
        resource=r, weekday=5, start_time=time(12), end_time=time(23), slot_minutes=30
    )
    groups = hours_summary.rule_groups(r.rules.all())
    assert [g["days"] for g in groups] == ["Mo–Su", "Sa"]
    assert len(groups[0]["rules"]) == 7  # удаление по-прежнему поштучно
    assert hours_summary.summary(groups) == "Mo–Su 11:00–22:00 · Sa 12:00–23:00"


def test_non_consecutive_days_listed_short_runs_kept():
    r = _resource(days=[0, 1, 3, 4, 5])
    assert hours_summary.rule_groups(r.rules.all())[0]["days"] == "Mo, Tu, Th–Sa"


def test_cards_are_collapsed_with_summary_and_forms_stay_in_dom():
    _resource()
    _resource()
    body = views.resources(_req()).content.decode()
    assert body.count("data-resource-card") == 2
    assert "data-resource-card open" not in body  # несколько — свёрнуты
    assert "Mo–Su 11:00–22:00" in body  # сводка часов в заголовке
    assert 'value="resource_settings"' in body and "data-table-seats" in body  # W0


def test_after_save_the_same_card_is_open():
    r = _resource()
    _resource()
    resp = views.resources(
        _req(
            "post",
            {
                "action": "resource_settings",
                "resource": str(r.pk),
                "seats_present": "1",
                "seats": "6",
                "capacity": "1",
                "min_seats": "1",
                "sort_order": "0",
            },
        )
    )
    assert resp.status_code == 302 and resp.url.endswith(f"?open={r.pk}#res-{r.pk}")
    body = views.resources(_req(data={"open": str(r.pk)})).content.decode()
    assert f'id="res-{r.pk}"' in body
    card = body.split(f'id="res-{r.pk}"')[1].split(">")[0]
    assert "open" in card


def test_foreign_open_param_is_ignored():
    _resource()
    _resource()
    body = views.resources(_req(data={"open": "<script>x"})).content.decode()
    assert "data-resource-card open" not in body and "<script>x" not in body
