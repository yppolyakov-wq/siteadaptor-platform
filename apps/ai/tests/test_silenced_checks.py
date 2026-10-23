"""Владелец принял ai.W004 (тест ИИ вне ЕС) — деплой не печатает его на каждом шаге."""

import pytest
from django.core import checks
from django.test import override_settings

pytestmark = pytest.mark.django_db


@override_settings(
    AI_ENABLED=True, AI_REQUIRE_EU=False, DEBUG=False, SILENCED_SYSTEM_CHECKS=["ai.W004"]
)
def test_w004_can_be_silenced():
    ids = {m.id for m in checks.run_checks() if not m.is_silenced()}
    assert "ai.W004" not in ids
