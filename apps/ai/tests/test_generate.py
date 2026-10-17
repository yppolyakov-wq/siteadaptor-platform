"""AI-0: контракт `generate` — выключатель, реестр, схема, картинки."""

import pytest

from apps.ai import api
from apps.ai.errors import AIConfigError, AIDisabled, AISchemaError
from apps.ai.models import AIUsage
from apps.ai.providers import fake

pytestmark = pytest.mark.django_db

SCHEMA = {
    "type": "object",
    "required": ["title", "price"],
    "properties": {"title": {"type": "string"}, "price": {"type": "number"}},
}
JPEG = b"\xff\xd8\xff\xe0" + b"0" * 100


def test_disabled_raises_without_network_or_usage(settings):
    settings.AI_ENABLED = False
    with pytest.raises(AIDisabled):
        api.generate("smoke", "hallo")
    assert fake.CALLS == []
    assert AIUsage.objects.count() == 0


def test_unknown_task_is_config_error(ai_on):
    with pytest.raises(AIConfigError):
        api.generate("nope", "x")


def test_text_result_and_ai_generated_flag(ai_on):
    r = api.generate("smoke", "hallo")
    assert r.text == "fake:smoke" and r.data is None
    assert r.ai_generated is True and r.route == "fake" and not r.fallback_used


def test_schema_valid_returns_data(ai_on):
    r = api.generate("smoke", "x", schema=SCHEMA)
    assert r.data == {"title": "fake", "price": 0}
    assert fake.CALLS[0][1].json_mode is True
    assert "JSON" in fake.CALLS[0][1].system


def test_bad_json_retries_once_then_succeeds(ai_on):
    fake.script("fake", ["bad_json", "ok"])
    r = api.generate("smoke", "x", schema=SCHEMA)
    assert r.data["title"] == "fake"
    assert len(fake.CALLS) == 2
    # Повтор несёт описание ошибки схемы, а не содержимое ответа.
    assert "invalid" in fake.CALLS[1][1].prompt
    assert "not json" not in fake.CALLS[1][1].prompt


def test_bad_json_twice_raises_schema_error_and_no_fallback(ai_on):
    ai_on.AI_ROUTE_FAST = ["fake", "fake_b"]
    fake.script("fake", ["bad_json", "bad_json"])
    with pytest.raises(AISchemaError):
        api.generate("smoke", "x", schema=SCHEMA)
    assert [name for name, _ in fake.CALLS] == ["fake", "fake"]


def test_images_rejected_for_task_without_images(ai_on):
    from apps.ai import registry

    registry.register("t_noimg", registry.TaskSpec(tier="fast"))
    with pytest.raises(AIConfigError):
        api.generate("t_noimg", "x", images=[JPEG])


@pytest.mark.parametrize(
    "data",
    [b"GIF89a" + b"0" * 10, b"<svg></svg>", b"\xff\xd8\xff" + b"0" * (5 * 1024 * 1024)],
)
def test_image_signature_and_size_checked(ai_on, data):
    with pytest.raises(AIConfigError):
        api.generate("smoke", "x", images=[data])
    assert fake.CALLS == []


def test_image_passed_with_sniffed_type(ai_on):
    api.generate("smoke", "x", images=[JPEG])
    (img,) = fake.CALLS[0][1].images
    assert img.mime == "image/jpeg"


def test_registry_conflict_is_error():
    from apps.ai import registry

    with pytest.raises(ValueError):
        registry.register("smoke", registry.TaskSpec(tier="strong"))
