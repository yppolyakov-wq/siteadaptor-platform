"""UA4-3: богатая карточка услуги — attributes/faq (garbage-safe) + primary_action."""

from apps.booking.models import (
    Service,
    normalize_service_attributes,
    normalize_service_faq,
)


def test_normalize_attributes_keeps_clean_strings():
    assert normalize_service_attributes(["  A  ", "B", "", 5, None, {"x": 1}]) == ["A", "B"]


def test_normalize_attributes_caps_count():
    assert len(normalize_service_attributes([str(i) for i in range(50)])) == 12


def test_normalize_attributes_non_list_is_safe():
    assert normalize_service_attributes(None) == []
    assert normalize_service_attributes("notalist") == []  # не итерируем как строку
    assert normalize_service_attributes({"a": 1}) == []


def test_normalize_faq_keeps_questions_with_nonempty_q():
    raw = [
        {"q": " Wie? ", "a": " So. "},
        {"q": "", "a": "нет вопроса"},  # пустой q → выброшен
        {"a": "no q"},  # нет q → выброшен
        "garbage",
        {"q": "Nur Frage"},  # a может отсутствовать
    ]
    assert normalize_service_faq(raw) == [
        {"q": "Wie?", "a": "So."},
        {"q": "Nur Frage", "a": ""},
    ]


def test_normalize_faq_non_list_is_safe():
    assert normalize_service_faq(None) == []
    assert normalize_service_faq("x") == []


def test_service_list_properties():
    s = Service(
        name="X",
        attributes=["A", "", "B"],
        faq=[{"q": "Q1", "a": "A1"}, {"q": ""}],
    )
    assert s.attributes_list == ["A", "B"]
    assert s.faq_list == [{"q": "Q1", "a": "A1"}]


def test_primary_action_field_feeds_resolver():
    """UA4-3 + реш.2: поле primary_action читается резолвером archetypes."""
    from apps.core.archetypes import primary_service_action

    class _T:
        site_config = {}

        def is_module_active(self, key):
            return key == "jobs"

    assert primary_service_action(Service(name="X", primary_action="request"), _T()) == "request"
    assert primary_service_action(Service(name="X", primary_action=""), _T()) == "booking"

