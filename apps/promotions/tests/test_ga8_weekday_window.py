"""KA-12 GA-8 (Gastro): окно «дни недели / часы» в полной форме акции, пресет
Mittagstisch Mo–Fr 11–15, повтор пропускает дни вне правила и закрытые дни,
наследник сохраняет цели и окно."""

import datetime
from datetime import timedelta

import pytest
from django.utils import timezone

from apps.promotions.forms import PromotionForm
from apps.promotions.models import Promotion
from apps.promotions.presets import preset_initial
from apps.promotions.tasks import _next_window, roll_due_recurring
from apps.promotions.tests.factories import PromotionFactory

pytestmark = pytest.mark.django_db
TZ = timezone.get_current_timezone()


def _at(day, hour):
    return timezone.make_aware(datetime.datetime.combine(day, datetime.time(hour)), TZ)


def _form_data(**extra):
    now = timezone.now()
    data = {
        "title_de": "Mittagstisch",
        "promo_type": "discount",
        "discount_percent": "10",
        "starts_at": (now + timedelta(hours=1)).strftime("%Y-%m-%dT%H:%M"),
        "ends_at": (now + timedelta(hours=5)).strftime("%Y-%m-%dT%H:%M"),
        "recurrence": "daily",
        "max_per_customer": "1",
        "reservation_ttl_hours": "4",
        "rules_present": "1",
    }
    data.update(extra)
    return data


def test_form_saves_and_clears_window_keeping_other_rules():
    promo = PromotionFactory(target_rules={"resource_id": "abc"})
    form = PromotionForm(
        _form_data(rule_weekdays=["0", "1", "2", "3", "4"], rule_hour_from="11", rule_hour_to="15"),
        instance=promo,
    )
    assert form.is_valid(), form.errors
    promo = form.save()
    assert promo.target_rules == {
        "resource_id": "abc",
        "weekdays": [0, 1, 2, 3, 4],
        "hour_from": 11,
        "hour_to": 15,
    }
    form = PromotionForm(_form_data(), instance=promo)
    assert form.is_valid(), form.errors
    assert form.save().target_rules == {"resource_id": "abc"}


def test_form_without_sentinel_keeps_window():
    promo = PromotionFactory(target_rules={"weekdays": [0], "hour_from": 11})
    data = _form_data()
    data.pop("rules_present")
    form = PromotionForm(data, instance=promo)
    assert form.is_valid(), form.errors
    assert form.save().target_rules == {"weekdays": [0], "hour_from": 11}


def test_all_seven_days_means_no_weekday_rule():
    form = PromotionForm(_form_data(rule_weekdays=[str(d) for d in range(7)]))
    assert form.is_valid(), form.errors
    assert "weekdays" not in form.save().target_rules


def test_lunch_preset_is_weekdays_eleven_to_fifteen():
    initial = preset_initial("restaurant", "mittag")
    assert initial["rule_weekdays"] == ["0", "1", "2", "3", "4"]
    assert (initial["rule_hour_from"], initial["rule_hour_to"]) == (11, 15)


def test_friday_rolls_to_monday():
    friday = datetime.date(2026, 10, 30)
    starts, ends = _at(friday, 11), _at(friday, 15)
    new_starts, _ends = _next_window(
        starts, ends, "daily", ends + timedelta(hours=1), rules={"weekdays": [0, 1, 2, 3, 4]}
    )
    assert timezone.localtime(new_starts).date() == datetime.date(2026, 11, 2)


def test_closed_day_is_skipped(monkeypatch):
    from apps.core import closures

    monday = datetime.date(2026, 11, 2)
    monkeypatch.setattr(closures, "is_closed", lambda day, tenant=None: day == monday)
    friday = datetime.date(2026, 10, 30)
    new_starts, _e = _next_window(
        _at(friday, 11),
        _at(friday, 15),
        "daily",
        _at(friday, 16),
        rules={"weekdays": [0, 1, 2, 3, 4]},
    )
    assert timezone.localtime(new_starts).date() == datetime.date(2026, 11, 3)


def test_junk_rules_fall_back_to_next_day():
    friday = datetime.date(2026, 10, 30)
    new_starts, _e = _next_window(
        _at(friday, 11), _at(friday, 15), "daily", _at(friday, 16), rules={"weekdays": "Mo"}
    )
    assert timezone.localtime(new_starts).date() == datetime.date(2026, 10, 31)


def test_heir_keeps_window_and_target():
    from apps.booking.models import Service

    service = Service.objects.create(name="Haarschnitt", duration_minutes=30, price_cents=3000)
    friday = datetime.date(2026, 10, 30)
    PromotionFactory(
        status="ended",
        recurrence="daily",
        starts_at=_at(friday, 11),
        ends_at=_at(friday, 15),
        service=service,
        target_rules={"weekdays": [0, 1, 2, 3, 4], "hour_from": 11, "hour_to": 15},
    )
    roll_due_recurring(_at(friday, 16))
    heir = Promotion.objects.get(status="scheduled")
    assert heir.service_id == service.pk
    assert heir.target_rules["weekdays"] == [0, 1, 2, 3, 4]
    assert timezone.localtime(heir.starts_at).weekday() == 0
