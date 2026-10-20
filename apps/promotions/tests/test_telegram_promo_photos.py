"""T-8.10h H-7a: фото после превью — в тот же черновик; «📷 Foto hinzufügen» / «🗑».

План — docs/t8-10h-h7-owner-bot-ux-plan-2026-10-20.md §2.
"""

import pytest

from apps.promotions import quick
from apps.promotions import telegram_promo as tp
from apps.promotions.tests.test_telegram_promo import OWNER, _draft, _msg, tg  # noqa: F401

pytestmark = pytest.mark.django_db


def _photo(tg, file_id, caption="", group=""):  # noqa: F811
    extra = {"photo": [{"file_id": file_id}]}
    if group:
        extra["media_group_id"] = group
    upd = tp.slim_update(_msg(caption, **extra))
    return tp._handle(tg["bot"], tg["tenant"], "public", str(OWNER), upd)


def _buttons(entry):
    return [b for row in entry["markup"]["inline_keyboard"] for b in row]


def test_photo_after_preview_joins_same_draft(tg):  # noqa: F811
    token, _preview = _draft(tg)
    assert _photo(tg, "P1") == "photo_added"
    draft = tp.load_draft("public", str(OWNER), token)
    assert draft["photo_ids"] == ["P1"]
    assert "📷 1" in tg["sent"][-1]["text"]  # превью переотправлено с фото


def test_photo_limit_and_duplicates(tg):  # noqa: F811
    token, _preview = _draft(tg)
    for i in range(quick.MAX_PHOTOS):
        assert _photo(tg, f"P{i}") == "photo_added"
    assert _photo(tg, "P0") == "photo_dup"
    assert _photo(tg, "EXTRA") == "photo_full"
    assert len(tp.load_draft("public", str(OWNER), token)["photo_ids"]) == quick.MAX_PHOTOS


def _press(tg, data):  # noqa: F811
    callback = {
        "id": "c",
        "from": {"id": OWNER},
        "message": {"chat": {"id": OWNER}, "message_id": 1},
        "data": data,
    }
    return tp._dispatch_callback(tg["bot"], callback, tg["tenant"], "public")


def test_album_after_preview_sends_preview_once(tg):  # noqa: F811
    token, _preview = _draft(tg)
    assert _press(tg, f"tp:ph:{token}") == "photo_wait"
    before = len(tg["sent"])
    for i in range(3):
        assert _photo(tg, f"A{i}", group="G1") == "photo_added"
    assert len(tg["sent"]) == before + 1
    assert tp.load_draft("public", str(OWNER), token)["photo_ids"] == ["A0", "A1", "A2"]


def test_photo_with_caption_starts_new_draft(tg):  # noqa: F811
    token, _preview = _draft(tg)
    _photo(tg, "N1", caption="Kaffee 1,50 € heute bis 23 Uhr")
    assert tp.load_draft("public", str(OWNER), token).get("photo_ids") in ([], None)


def test_preview_has_photo_buttons_and_remove_clears(tg):  # noqa: F811
    token, preview = _draft(tg)
    datas = [b.get("callback_data", "") for b in _buttons(preview)]
    assert f"tp:ph:{token}" in datas
    assert f"tp:px:{token}" not in datas  # убирать нечего
    _photo(tg, "P1")
    assert f"tp:px:{token}" in [b.get("callback_data", "") for b in _buttons(tg["sent"][-1])]
    callback = {
        "id": "c",
        "from": {"id": OWNER},
        "message": {"chat": {"id": OWNER}, "message_id": 1},
        "data": f"tp:px:{token}",
    }
    assert tp._dispatch_callback(tg["bot"], callback, tg["tenant"], "public") == "photos_removed"
    assert tp.load_draft("public", str(OWNER), token)["photo_ids"] == []


def test_add_photo_button_points_next_photos_to_that_draft(tg):  # noqa: F811
    first, _p = _draft(tg)
    second, _p = _draft(tg, "Kuchen 3 € heute bis 23 Uhr")
    callback = {
        "id": "c",
        "from": {"id": OWNER},
        "message": {"chat": {"id": OWNER}, "message_id": 1},
        "data": f"tp:ph:{first}",
    }
    assert tp._dispatch_callback(tg["bot"], callback, tg["tenant"], "public") == "photo_wait"
    _photo(tg, "P9")
    assert tp.load_draft("public", str(OWNER), first)["photo_ids"] == ["P9"]
    assert not tp.load_draft("public", str(OWNER), second).get("photo_ids")


def test_photo_of_other_bot_not_mixed(tg):  # noqa: F811
    token, _preview = _draft(tg)
    draft = tp.load_draft("public", str(OWNER), token)
    draft["bot"] = "platform"
    tg["cache"].set(tp._draft_key("public", str(OWNER), token), draft, 60)
    assert _photo(tg, "P1") != "photo_added"


def test_hint_mentions_photos(tg):  # noqa: F811
    upd = tp.slim_update(_msg("hallo"))
    assert tp._handle(tg["bot"], tg["tenant"], "public", str(OWNER), upd) == "hint"
    assert "📷" in tg["sent"][-1]["text"]


def test_platform_router_accepts_photo_buttons():
    assert tp.CALLBACK_RE.match("tp:ph:" + "a" * 16)
    assert tp.CALLBACK_RE.match("tp:px:" + "a" * 16)
    assert not tp.CALLBACK_RE.match("tp:zz:" + "a" * 16)


def test_new_album_with_late_caption_does_not_leak_into_old_draft(tg):  # noqa: F811
    """Ревью H-7a: подпись альбома пришла на 3-м фото — первые два не уходят в старый черновик."""
    old, _preview = _draft(tg)
    assert _photo(tg, "N1", group="G2") == "album_wait"
    assert _photo(tg, "N2", group="G2") == "album_wait"
    _photo(tg, "N3", caption="Kuchen 3 € heute bis 23 Uhr", group="G2")
    assert not tp.load_draft("public", str(OWNER), old).get("photo_ids")
    new = tg["cache"].get(tp._last_key("public", str(OWNER)))
    assert new != old
    assert set(tp.load_draft("public", str(OWNER), new)["photo_ids"]) == {"N1", "N2", "N3"}


def test_captioned_album_sends_single_preview(tg):  # noqa: F811
    before = len(tg["sent"])
    _photo(tg, "C1", caption="Kuchen 3 € heute bis 23 Uhr", group="G3")
    _photo(tg, "C2", group="G3")
    _photo(tg, "C3", group="G3")
    assert len(tg["sent"]) == before + 1


def test_photo_after_confirm_claim_is_not_attached(tg):  # noqa: F811
    token, _preview = _draft(tg)
    assert tp.claim("public", token)
    assert _photo(tg, "LATE") != "photo_added"
    assert not tp.load_draft("public", str(OWNER), token).get("photo_ids")


def test_new_draft_disarms_photo_button(tg):  # noqa: F811
    first, _p = _draft(tg)
    _press(tg, f"tp:ph:{first}")
    _draft(tg, "Kuchen 3 € heute bis 23 Uhr")
    _photo(tg, "A1", group="G4")
    assert not tp.load_draft("public", str(OWNER), first).get("photo_ids")
