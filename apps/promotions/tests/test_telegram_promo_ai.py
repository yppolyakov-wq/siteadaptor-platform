"""T-8.10b B-2: ИИ по фото в Telegram заполняет только ПУСТЫЕ описательные поля."""

import pytest

from apps.promotions import ai_draft
from apps.promotions import telegram_promo as tp
from apps.promotions.tests.test_telegram_promo import OWNER, _msg, tg  # noqa: F401
from apps.telegram import services

pytestmark = pytest.mark.django_db

AI_RESULT = {
    "recognised": True,
    "title": "Erdbeerkuchen",
    "description": "Frisch gebacken mit Sahne.",
    "item_noun": "Kuchen",
    "city_category": "",
    "city_tags": [],
    "product": None,
    "candidates": [],
    "warnings": [],
    # ИИ «предлагает» цены — они обязаны игнорироваться
    "new_price": "0.01",
    "percent": "99",
}


@pytest.fixture
def ai(monkeypatch, tg):  # noqa: F811
    calls = []
    monkeypatch.setattr("apps.ai.api.is_enabled", lambda: True)
    monkeypatch.setattr(services, "download_file", lambda token, fid: b"img")
    monkeypatch.setattr("apps.ai.images.reencode", lambda data, **kw: b"clean")

    def fake(photo, *, hint="", tenant=None):
        calls.append({"photo": photo, "hint": hint})
        return dict(AI_RESULT), ""

    monkeypatch.setattr(ai_draft, "draft_from_photo", fake)
    return calls


def _photo_update(text):
    return tp.slim_update(_msg(text, photo=[{"file_id": "F1"}]))


def _draft(tg):  # noqa: F811
    markup = tg["sent"][-1]["markup"]["inline_keyboard"][0]
    token = next(b for b in markup if b.get("callback_data", "").startswith("tp:"))
    return tp.load_draft("public", str(OWNER), token["callback_data"].split(":")[2])


def test_photo_without_caption_gets_title_and_description(tg, ai):  # noqa: F811
    upd = _photo_update("")
    assert tp._handle(tg["bot"], tg["tenant"], "public", str(OWNER), upd) == "preview"
    draft = _draft(tg)
    assert draft["title"] == "Erdbeerkuchen"
    assert draft["description"] == "Frisch gebacken mit Sahne."
    assert draft["ai_draft"] == "1"
    assert "✨" in tg["sent"][-1]["text"]
    # Числа — только из текста владельца
    assert draft["new_price"] == "" and draft["percent"] == ""
    assert ai[0]["photo"] == b"clean"  # провайдеру — перекодированная копия


def test_owner_text_wins_over_ai(tg, ai):  # noqa: F811
    upd = _photo_update("Brötchen 2,50 € heute\nVom Bäcker nebenan.")
    tp._handle(tg["bot"], tg["tenant"], "public", str(OWNER), upd)
    draft = _draft(tg)
    assert draft["title"] == "Brötchen"
    assert draft["description"] == "Vom Bäcker nebenan."
    assert draft["new_price"] == "2.50"
    assert ai[0]["hint"] == "Brötchen"


def test_ai_disabled_photo_without_caption_asks_for_title(tg, monkeypatch):  # noqa: F811
    monkeypatch.setattr("apps.ai.api.is_enabled", lambda: False)
    called = []
    monkeypatch.setattr(ai_draft, "draft_from_photo", lambda *a, **k: called.append(1))
    upd = _photo_update("")
    assert tp._handle(tg["bot"], tg["tenant"], "public", str(OWNER), upd) == "no_title"
    assert called == []


def test_unrecognised_photo_keeps_rule_draft(tg, ai, monkeypatch):  # noqa: F811
    monkeypatch.setattr(
        ai_draft, "draft_from_photo", lambda *a, **k: ({**AI_RESULT, "recognised": False}, "")
    )
    upd = _photo_update("")
    assert tp._handle(tg["bot"], tg["tenant"], "public", str(OWNER), upd) == "no_title"


def test_ai_error_never_breaks_the_draft(tg, ai, monkeypatch):  # noqa: F811
    def boom(*a, **k):
        raise RuntimeError("provider")

    monkeypatch.setattr(ai_draft, "draft_from_photo", boom)
    upd = _photo_update("Brötchen −30 % heute")
    assert tp._handle(tg["bot"], tg["tenant"], "public", str(OWNER), upd) == "preview"
    assert "ai_draft" not in _draft(tg)


def test_ai_marker_reaches_promotion_metadata(tg, ai):  # noqa: F811
    from apps.promotions.models import Promotion
    from apps.promotions.tests.test_telegram_promo import _cb

    monkeypatch_photos = tp.photos_from_telegram
    tp.photos_from_telegram = lambda token, ids: ([], False)
    try:
        tp._handle(tg["bot"], tg["tenant"], "public", str(OWNER), _photo_update("−20 % heute"))
        token = tg["sent"][-1]["markup"]["inline_keyboard"][0][0]["callback_data"].split(":")[2]
        assert _cb(tg, f"tp:ok:{token}") == "published"
    finally:
        tp.photos_from_telegram = monkeypatch_photos
    assert Promotion.objects.get().metadata.get("ai_draft") is True


def test_ai_claims_show_up_as_warnings(tg, ai, monkeypatch):  # noqa: F811
    monkeypatch.setattr(
        ai_draft, "draft_from_photo", lambda *a, **k: ({**AI_RESULT, "warnings": ["Bio"]}, "")
    )
    tp._handle(tg["bot"], tg["tenant"], "public", str(OWNER), _photo_update(""))
    assert "„Bio“" in tg["sent"][-1]["text"]
