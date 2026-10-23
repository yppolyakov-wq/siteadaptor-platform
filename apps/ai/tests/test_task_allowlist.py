"""AI-1 (решение владельца 2026-10-23): ИИ включается ПО ЗАДАЧАМ.

Список `AI_TASKS_ENABLED` — белый: задача не из списка не выполняется (новая задача
выключена, пока её не внесут). Переписка с клиентом (`inbox_reply_draft`) по
умолчанию выключена — пока ключ ИИ не европейский."""

import pytest
from django.conf import settings as dj_settings

from apps.ai import api
from apps.ai.errors import AIConfigError, AIDisabled
from apps.ai.providers import fake

pytestmark = pytest.mark.django_db


def test_default_allowlist_keeps_catalog_and_promo_but_not_chat():
    tasks = set(dj_settings.AI_TASKS_ENABLED)
    assert {"site_import_extract", "promo_photo_draft", "promo_text_check"} <= tasks
    assert "inbox_reply_draft" not in tasks


def test_task_not_in_allowlist_is_disabled(ai_on):
    ai_on.AI_TASKS_ENABLED = ["promo_text_check"]
    assert api.is_enabled() is True
    assert api.is_enabled("promo_text_check") is True
    assert api.is_enabled("inbox_reply_draft") is False


def test_generate_refuses_task_outside_allowlist(ai_on):
    from apps.ai import registry

    registry.register("ai1_probe", registry.TaskSpec())
    ai_on.AI_TASKS_ENABLED = []
    with pytest.raises(AIDisabled):
        api.generate("ai1_probe", "x")
    assert fake.CALLS == []


def test_smoke_tasks_always_allowed(ai_on):
    ai_on.AI_TASKS_ENABLED = []
    assert api.generate("smoke", "x").text == "fake:smoke"


def test_unknown_task_still_config_error(ai_on):
    ai_on.AI_TASKS_ENABLED = []
    with pytest.raises(AIConfigError):
        api.generate("nope", "x")


def test_global_switch_off_disables_every_task(ai_on):
    ai_on.AI_ENABLED = False
    ai_on.AI_TASKS_ENABLED = ["promo_text_check"]
    assert api.is_enabled("promo_text_check") is False


def test_privacy_paragraph_only_when_chat_task_enabled(ai_on):
    from apps.tenants.tests.factories import TenantFactory

    tenant = TenantFactory.build(disabled_modules=[])
    ai_on.AI_ROUTE_FAST = ai_on.AI_ROUTE_STRONG = ["anthropic"]  # AI-2: получатель в тексте
    ai_on.AI_TASKS_ENABLED = ["promo_text_check"]
    assert tenant._privacy_ai_paragraph() == ""
    ai_on.AI_TASKS_ENABLED = ["inbox_reply_draft"]
    assert "KI" in tenant._privacy_ai_paragraph()


def test_check_warns_on_unknown_task_name(settings):
    from apps.ai.checks import check_ai_routes

    settings.AI_TASKS_ENABLED = ["promo_text_chek"]
    ids = [p.id for p in check_ai_routes()]
    assert "ai.W005" in ids


def test_inbox_and_deal_card_gates_follow_chat_task(ai_on):
    from apps.core import deal_card
    from apps.inbox import views as inbox_views

    ai_on.AI_TASKS_ENABLED = ["promo_text_check"]
    assert inbox_views._ai_reply_enabled() is False
    assert deal_card._ai_enabled() is False
    ai_on.AI_TASKS_ENABLED = ["inbox_reply_draft"]
    assert inbox_views._ai_reply_enabled() is True
    assert deal_card._ai_enabled() is True


def test_promo_photo_and_text_check_are_separate(ai_on):
    from apps.promotions import views as promo_views

    ai_on.AI_TASKS_ENABLED = ["promo_text_check"]
    assert promo_views._ai_text_check_enabled() is True
    assert promo_views._ai_photo_enabled() is False
    ai_on.AI_TASKS_ENABLED = ["promo_photo_draft"]
    assert promo_views._ai_text_check_enabled() is False
    assert promo_views._ai_photo_enabled() is True
