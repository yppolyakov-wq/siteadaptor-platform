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


def test_list_rows_show_hours_summary_without_forms():
    """UX-D D3.2 (осознанная переписка SP-3): вместо свёрнутых карточек с формами —
    строки-ссылки на страницу ресурса; сводка часов осталась в строке."""
    _resource()
    _resource()
    body = views.resources(_req()).content.decode()
    assert body.count("data-resource-row") == 2
    assert "Mo–Su 11:00–22:00" in body  # сводка часов в строке
    assert 'value="resource_settings"' not in body and "data-resource-card" not in body


def test_after_save_the_resource_page_opens_on_the_action_tab():
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
    assert resp.status_code == 302 and resp.url.endswith(f"/ressourcen/{r.pk}/?tab=buchung")
    old = views.resources(_req(data={"open": str(r.pk)}))  # старая закладка ?open=
    assert old.status_code == 302 and old.url.endswith(f"/ressourcen/{r.pk}/")


def test_foreign_open_param_is_ignored():
    _resource()
    _resource()
    body = views.resources(_req(data={"open": "<script>x"})).content.decode()
    assert "<script>x" not in body  # мусор — обычный список, не 302 и не 500


def test_redirect_uses_canonical_pk_not_raw_post():
    # Ревью SP-3: UUID-парсер принимает «{…}» — в Location только канонический pk из БД.
    r = _resource()
    resp = views.resources(_req("post", {"action": "toggle", "resource": f"{{{r.pk}}}"}))
    assert resp.url.endswith(f"/ressourcen/{r.pk}/") and "{" not in resp.url


def test_rule_delete_keeps_card_open_and_survives_garbage_id():
    r = _resource(days=[0, 1])
    rule = r.rules.first()
    resp = views.resources(
        _req("post", {"action": "rule_delete", "rule": str(rule.pk), "resource": str(r.pk)})
    )
    assert resp.url.endswith(f"/ressourcen/{r.pk}/?tab=zeiten") and r.rules.count() == 1
    resp = views.resources(_req("post", {"action": "rule_delete", "rule": "nope"}))
    assert resp.status_code == 302
