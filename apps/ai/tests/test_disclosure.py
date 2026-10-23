"""AI-2 (решение владельца 2026-10-23): Datenschutz говорит, куда РЕАЛЬНО уходят данные.

Тестовая фаза на прямом Anthropic API (США): текст называет получателя, страну и
основание передачи; с маршрутом ЕС — «Server in der EU». Выключенный ИИ — ни слова."""

import pytest

from apps.ai import disclosure
from apps.ai.providers import FAKE_ROUTES, ROUTE_NAMES
from apps.ai.registry import TASKS

pytestmark = pytest.mark.django_db


@pytest.fixture
def anthropic_on(ai_on):
    ai_on.AI_ROUTE_FAST = ["anthropic"]
    ai_on.AI_ROUTE_STRONG = ["anthropic"]
    ai_on.AI_REQUIRE_EU = False
    ai_on.AI_TASKS_ENABLED = ["site_import_extract", "promo_photo_draft", "promo_text_check"]
    return ai_on


def test_platform_section_names_anthropic_usa_and_scc(anthropic_on):
    text = disclosure.platform_section()
    assert "Anthropic PBC" in text and "USA" in text and "Art. 46" in text
    assert "Data Privacy Framework" not in text
    assert "Fotos" in text  # Aufgabe Foto-Vorschlag beschrieben


def test_platform_section_eu_route(ai_on, settings):
    ai_on.AI_ROUTE_FAST = ["mistral"]
    ai_on.AI_ROUTE_STRONG = ["mistral"]
    settings.MISTRAL_MODEL_FAST = settings.MISTRAL_MODEL_STRONG = "mistral-x"
    text = disclosure.platform_section()
    assert "Mistral AI SAS" in text and "USA" not in text


def test_disabled_ai_gives_no_text(settings):
    settings.AI_ENABLED = False
    assert disclosure.platform_section() == ""


def test_secondary_gate_off_task_not_mentioned(anthropic_on):
    anthropic_on.AI_TASKS_ENABLED = ["search_phrase_filters"]
    anthropic_on.AI_SEARCH_ENABLED = False
    assert disclosure.platform_section() == ""


def test_tenant_paragraph_route_aware(anthropic_on):
    from apps.tenants.tests.factories import TenantFactory

    tenant = TenantFactory.build(disabled_modules=[])
    assert tenant._privacy_ai_paragraph() == ""  # Chat aus → kein Absatz
    anthropic_on.AI_TASKS_ENABLED = ["inbox_reply_draft"]
    text = tenant._privacy_ai_paragraph()
    assert "USA" in text and "in der EU" not in text and "Art. 28 DSGVO" in text


def test_every_task_is_described():
    missing = set(TASKS) - set(disclosure.TASK_DATA) - {"smoke", "smoke_strong"}
    assert not {t for t in missing if not t.startswith(("t_", "ai1_"))}


def test_every_route_has_a_processor():
    assert set(ROUTE_NAMES) - set(FAKE_ROUTES) <= set(disclosure.PROCESSORS)


def test_platform_page_shows_section(anthropic_on, settings):
    from django.test import RequestFactory

    from apps.tenants import views

    settings.ROOT_URLCONF = "config.urls_public"
    body = views.platform_legal(RequestFactory().get("/datenschutz/"), "datenschutz")
    assert "data-privacy-ai" in body.content.decode()


def test_mixed_routes_say_eu_and_usa(anthropic_on, settings):
    anthropic_on.AI_ROUTE_FAST = ["mistral", "anthropic"]
    settings.MISTRAL_MODEL_FAST = settings.MISTRAL_MODEL_STRONG = "mistral-x"
    text = disclosure.platform_section()
    assert "teils auf Servern in der EU, teils in den USA" in text


def test_non_eu_route_hidden_when_eu_required(anthropic_on, settings):
    anthropic_on.AI_REQUIRE_EU = True
    anthropic_on.AI_ROUTE_FAST = ["mistral", "anthropic"]
    anthropic_on.AI_ROUTE_STRONG = ["mistral"]
    settings.MISTRAL_MODEL_FAST = settings.MISTRAL_MODEL_STRONG = "mistral-x"
    text = disclosure.platform_section()
    assert "Anthropic" not in text and "USA" not in text
