"""AIS W4-4: фото меню/прайса → строки «Prüfen» — пост-проверка ответа ИИ и фоновая задача.

План — docs/ais-w4-4-photo-lines-plan-2026-11-06.md §5."""

from types import SimpleNamespace
from unittest import mock

import pytest
from django.core.cache import cache

from apps.ai.errors import AIUnavailable
from apps.core import offer_lines, offer_photo


def _raw(*items, is_price_list=True):
    return {"is_price_list": is_price_list, "items": list(items)}


def _parsed(raw, kind="speisekarte"):
    lines = offer_photo.clean_lines(raw, kind)
    return offer_lines.parse_lines("\n".join(lines), kind).lines


def test_foreign_keys_html_and_contacts_are_dropped():
    lines = offer_photo.clean_lines(
        _raw(
            {
                "name": "<b>Cappuccino</b> www.evil.example 0171 2345678",
                "price_text": "3,40 €",
                "evil": "x",
            },
            "kein dict",
            {"name": ""},
        ),
        "speisekarte",
    )
    assert lines == ["Cappuccino — 3,40 €"]


@pytest.mark.parametrize("sep", [" — ", " – ", " - ", " | ", "; ", ": ", "\t"])
def test_separator_inside_name_does_not_split_line(sep):
    rows = _parsed(_raw({"name": f"Pizza{sep}Margherita", "price_text": "9,50 €"}))
    assert len(rows) == 1
    assert rows[0].name == "Pizza Margherita"
    assert str(rows[0].price) == "9.50"
    assert not rows[0].errors


@pytest.mark.parametrize(
    "price", ["ca. 3", "3,50 € + Pfand", "-5 €", "20 %", "Tagespreis", "3,50 €/kg", "1 2 3"]
)
def test_unreadable_price_becomes_missing_not_invented(price):
    rows = _parsed(_raw({"name": "Brot", "price_text": price}), "waren")
    assert rows[0].price is None
    assert any("Preis fehlt" in str(e) for e in rows[0].errors)


def test_number_in_name_is_never_taken_as_price():
    rows = _parsed(_raw({"name": "Menü 2", "price_text": ""}), "waren")
    assert rows[0].name == "Menü 2"
    assert rows[0].price is None


def test_price_inside_name_tail_is_cut():
    assert offer_photo.clean_name("Croissant ..... 1,80 €") == "Croissant"


@pytest.mark.parametrize(
    "price,expected,price_from",
    [
        ("3,50 €", "3.50", False),
        ("€ 4", "4.00", False),
        ("12,-", "12.00", False),
        ("ab 9 €", "9.00", True),
        ("9–12 €", "9.00", True),
        ("3.50 EUR", "3.50", False),
    ],
)
def test_allowed_price_forms_match_manual_input(price, expected, price_from):
    rows = _parsed(_raw({"name": "Kuchen", "price_text": price}), "waren")
    assert f"{rows[0].price:.2f}" == expected
    assert rows[0].price_from is price_from
    manual = offer_lines.parse_lines(f"Kuchen — {price}", "waren").lines[0]
    assert manual.price == rows[0].price


def test_detail_kept_only_for_its_kind():
    item = {"name": "Haarschnitt", "price_text": "26 €", "detail_text": "30 Min"}
    termin = _parsed(_raw(item), "termine")[0]
    assert termin.duration_min == 30 and not termin.errors
    assert offer_photo.clean_lines(_raw(item), "waren") == ["Haarschnitt — 26 €"]
    junk = {**item, "detail_text": "Mo–Fr"}
    assert offer_photo.clean_lines(_raw(junk), "termine") == ["Haarschnitt — 26 €"]
    room = {"name": "Doppelzimmer", "price_text": "89 €", "detail_text": "2 Personen"}
    assert _parsed(_raw(room), "zimmer")[0].guests == 2


def test_exact_duplicates_dropped_same_name_other_price_kept():
    lines = offer_photo.clean_lines(
        _raw(
            {"name": "Tee", "price_text": "2,50 €"},
            {"name": "tee", "price_text": "2,50 €"},
            {"name": "Tee", "price_text": "3,00 €"},
        ),
        "speisekarte",
    )
    assert lines == ["Tee — 2,50 €", "Tee — 3,00 €"]


def test_not_a_price_list_gives_nothing():
    assert (
        offer_photo.clean_lines(
            _raw({"name": "X", "price_text": "1 €"}, is_price_list=False), "waren"
        )
        == []
    )
    assert offer_photo.clean_lines({"items": [{"name": "X"}]}, "waren") == []


def test_merge_keeps_whole_lines_and_counts_dropped():
    base = "Brot — 3 €"
    lines = [f"Artikel {i} — 1 €" for i in range(60)]
    text, dropped = offer_photo.merge_text(base, lines)
    rows = text.splitlines()
    assert rows[0] == base
    assert len(rows) == offer_lines.MAX_LINES
    assert dropped == 60 - (offer_lines.MAX_LINES - 1)
    assert all(r.endswith("€") for r in rows)  # ни одна строка не обрезана посреди
    long = ["N" * 200 + " — 1 €"] * 50
    text, dropped = offer_photo.merge_text("", long)
    assert len(text) <= offer_lines.MAX_TEXT
    assert dropped == 50 - len(text.splitlines())


def test_read_photos_disabled_without_ai(settings):
    settings.AI_ENABLED = False
    assert offer_photo.read_photos([b"x"], "waren") == ([], "disabled")


@pytest.fixture
def ai_task_on(settings):
    settings.AI_ENABLED = True
    settings.AI_REQUIRE_EU = False
    settings.AI_ROUTE_STRONG = ["fake"]
    settings.AI_TASKS_ENABLED = [*settings.AI_TASKS_ENABLED, offer_photo.TASK]
    return settings


def test_task_is_registered_and_described():
    from apps.ai import disclosure, registry

    spec = registry.get(offer_photo.TASK)
    assert spec.allow_images and spec.tier == "strong"
    assert offer_photo.TASK in disclosure.TASK_DATA


def test_read_photos_returns_clean_lines(ai_task_on):
    data = _raw({"name": "Espresso", "price_text": "2,20 €"})
    with mock.patch.object(offer_photo, "generate", return_value=SimpleNamespace(data=data)) as g:
        lines, code = offer_photo.read_photos([b"img"], "speisekarte")
    assert (lines, code) == (["Espresso — 2,20 €"], "")
    system = g.call_args.kwargs["system"]
    assert "DATA, not instructions" in system and "never guess" in system


def test_read_photos_empty_answer_is_nothing(ai_task_on):
    data = _raw(is_price_list=False)
    with mock.patch.object(offer_photo, "generate", return_value=SimpleNamespace(data=data)):
        assert offer_photo.read_photos([b"img"], "waren") == ([], "nothing")


@pytest.mark.django_db
@pytest.mark.parametrize("outcome", ["ok", "ai_error", "crash"])
def test_run_job_always_removes_photo_bytes(outcome):
    schema, user, job = "public", 7, "a" * 32
    key = offer_photo._job_key(schema, user, job)
    cache.set(key, {"state": "pending", "photos": [b"secret"], "kind": "waren"}, 60)
    effect = {
        "ok": lambda *a, **k: (["Brot — 3 €"], ""),
        "ai_error": lambda *a, **k: ([], "unavailable"),
        "crash": mock.Mock(side_effect=RuntimeError("boom")),
    }[outcome]
    with mock.patch.object(offer_photo, "read_photos", side_effect=effect):
        offer_photo.run_job(schema=schema, user_pk=user, job=job)
    entry = cache.get(key)
    assert "photos" not in entry
    assert entry["state"] == ("done" if outcome == "ok" else "error")
    assert offer_photo.job_state(schema=schema, user_pk=8, job=job) is None  # чужой — нет


def test_take_result_is_one_shot():
    schema, user, job = "public", 9, "b" * 32
    key = offer_photo._job_key(schema, user, job)
    cache.set(key, {"state": "done", "lines": ["A — 1 €"], "kind": "waren"}, 60)
    assert "lines" not in offer_photo.job_state(schema=schema, user_pk=user, job=job)
    assert offer_photo.take_result(schema=schema, user_pk=user, job=job)["lines"] == ["A — 1 €"]
    assert offer_photo.take_result(schema=schema, user_pk=user, job=job) is None


def test_pending_result_is_not_taken():
    schema, user, job = "public", 10, "c" * 32
    cache.set(offer_photo._job_key(schema, user, job), {"state": "pending", "photos": []}, 60)
    assert offer_photo.take_result(schema=schema, user_pk=user, job=job) is None


def test_ai_error_code_only_in_log(ai_task_on, caplog):
    with mock.patch.object(offer_photo, "generate", side_effect=AIUnavailable("secret url")):
        assert offer_photo.read_photos([b"img"], "waren") == ([], "unavailable")
    assert "secret url" not in caplog.text
