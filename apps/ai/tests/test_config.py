"""AI-CFG: настройки ИИ из админки сильнее `.env`; без строки в БД — прежнее поведение.

План docs/ai-cfg-admin-settings-plan-2026-10-23.md §3.
"""

import pytest
from django.test import override_settings

from apps.ai import api, config, routing
from apps.ai.models import AIConfig

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _fresh_cache():
    config.reset_cache()
    yield
    config.reset_cache()


def _admin(**values):
    AIConfig.objects.update_or_create(pk=1, defaults={"values": values})
    config.reset_cache()


@override_settings(AI_ENABLED=True, AI_TASKS_ENABLED=["promo_text_check"])
def test_without_admin_row_settings_win_as_before():
    assert api.is_enabled("promo_text_check")
    with override_settings(AI_ENABLED=False):
        assert not api.is_enabled("promo_text_check")


@override_settings(AI_ENABLED=True, AI_TASKS_ENABLED=["promo_text_check"])
def test_admin_value_wins_over_env_and_missing_key_falls_back():
    _admin(AI_TASKS_ENABLED=[])
    assert not api.is_enabled("promo_text_check")  # [] = «все выключены», не «как .env»
    _admin(AI_ENABLED=False)
    assert not api.is_enabled()
    _admin()
    assert api.is_enabled("promo_text_check")


@override_settings(AI_ROUTE_FAST=["mistral"], ANTHROPIC_MODEL_FAST="")
def test_routes_and_models_come_from_admin():
    _admin(AI_ROUTE_FAST=["anthropic"], ANTHROPIC_MODEL_FAST="claude-haiku-5-5")
    assert routing.configured("fast") == ["anthropic"]
    assert routing.model_for("anthropic", "fast") == "claude-haiku-5-5"


@override_settings(AI_REQUIRE_EU=True)
def test_env_eu_rule_is_a_floor_admin_cannot_weaken():
    _admin(AI_REQUIRE_EU=False)
    assert config.require_eu() is True


@override_settings(AI_REQUIRE_EU=False)
def test_admin_can_tighten_eu_rule():
    _admin(AI_REQUIRE_EU=True)
    assert config.require_eu() is True
    _admin()
    assert config.require_eu() is False


@override_settings(AI_ENABLED=True)
def test_override_beats_admin():
    _admin(AI_ENABLED=False)
    with config.override(AI_ENABLED=True):
        assert api.is_enabled()
    assert not api.is_enabled()


def test_save_returns_diff_and_drops_unknown_keys():
    diff = config.save({"AI_ENABLED": True, "SECRET_KEY": "x"})
    assert diff == {"AI_ENABLED": [None, True]}
    assert AIConfig.objects.get(pk=1).values == {"AI_ENABLED": True}
    assert config.sources()["AI_ENABLED"] == "admin"
    assert config.sources()["AI_SEARCH_ENABLED"] == "env"


def test_every_spec_key_exists_in_settings():
    from django.conf import settings

    for key in config.SPECS:
        assert hasattr(settings, key), key


def test_reader_survives_without_database():
    """Префлайт деплоя до миграций / тест без БД — значения .env, без падения."""
    config.reset_cache()
    from unittest import mock

    with mock.patch("apps.ai.models.AIConfig.objects") as objects:
        objects.filter.side_effect = RuntimeError("no table")
        assert config.get("AI_ENABLED", "fallback") is not None
