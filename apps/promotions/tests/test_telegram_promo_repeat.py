"""T-8.10b B-3: `/wiederholen` — повтор прошлой акции из Telegram."""

from decimal import Decimal

import pytest

from apps.promotions import telegram_promo as tp
from apps.promotions.models import Promotion
from apps.promotions.tests.test_telegram_promo import OWNER, _cb, _msg, tg  # noqa: F401

pytestmark = pytest.mark.django_db


def _promo(title, status="ended", **kw):
    return Promotion.objects.create(
        title={"de": title}, status=status, price_override=Decimal("2.50"), **kw
    )


def test_repeat_menu_lists_three_past_promotions(tg):  # noqa: F811
    for i in range(4):
        _promo(f"Alt {i}")
    _promo("Läuft", status="active")
    slim = tp.slim_update(_msg("/wiederholen"))
    assert tp._handle(tg["bot"], tg["tenant"], "public", str(OWNER), slim) == "repeat_menu"
    rows = tg["sent"][-1]["markup"]["inline_keyboard"]
    assert len(rows) == 3
    assert all(r[0]["callback_data"].startswith("tp:rp:") for r in rows)
    assert not any("Läuft" in r[0]["text"] for r in rows)
    assert all(len(r[0]["callback_data"].encode()) <= 64 for r in rows)


def test_repeat_menu_empty(tg):  # noqa: F811
    slim = tp.slim_update(_msg("/nochmal"))
    assert tp._handle(tg["bot"], tg["tenant"], "public", str(OWNER), slim) == "repeat_empty"


def test_repeat_callback_builds_preview_and_publishes_copy(tg):  # noqa: F811
    old = _promo("Erdbeerkuchen", compare_at_price=Decimal("3.90"))
    assert _cb(tg, f"tp:rp:{old.pk}") == "preview"
    preview = tg["sent"][-1]
    assert "Erdbeerkuchen" in preview["text"] and "2,50" in preview["text"]
    ok = next(
        b
        for b in preview["markup"]["inline_keyboard"][0]
        if b.get("callback_data", "")[:6] == "tp:ok:"
    )
    assert _cb(tg, ok["callback_data"]) == "published"
    new = Promotion.objects.exclude(pk=old.pk).get()
    assert new.status == "active" and new.price_override == Decimal("2.50")
    assert new.compare_at_price == Decimal("3.90")
    old.refresh_from_db()
    assert old.status == "ended"


def test_repeat_callback_rejects_active_or_unknown(tg):  # noqa: F811
    active = _promo("Läuft", status="active")
    assert _cb(tg, f"tp:rp:{active.pk}") == "repeat_missing"
    assert _cb(tg, "tp:rp:00000000-0000-0000-0000-000000000000") == "repeat_missing"
    assert _cb(tg, "tp:rp:not-a-uuid") == "skip"


def test_repeat_callback_from_stranger_denied(tg):  # noqa: F811
    old = _promo("Alt")
    assert _cb(tg, f"tp:rp:{old.pk}", sender=1) == "denied"


def test_malformed_uuid_is_skipped_not_raised(tg):  # noqa: F811
    assert _cb(tg, "tp:rp:" + "-" * 36) == "skip"


def test_repeat_callbacks_are_rate_limited(tg, monkeypatch):  # noqa: F811
    old = _promo("Alt")
    monkeypatch.setattr(tp, "RATE_LIMIT", 2)
    assert _cb(tg, f"tp:rp:{old.pk}") == "preview"
    assert _cb(tg, f"tp:rp:{old.pk}") == "preview"
    assert _cb(tg, f"tp:rp:{old.pk}") == "limited"


def test_menu_puts_open_ended_last_and_dedupes_titles(tg):  # noqa: F811
    from datetime import timedelta

    from django.utils import timezone

    now = timezone.now()
    _promo("Ohne Ende", status="paused")
    _promo("Kuchen", ends_at=now - timedelta(days=1))
    _promo("Kuchen", ends_at=now - timedelta(days=2))
    _promo("Brot", ends_at=now - timedelta(days=3))
    tp._handle(tg["bot"], tg["tenant"], "public", str(OWNER), tp.slim_update(_msg("/wiederholen")))
    texts = [r[0]["text"] for r in tg["sent"][-1]["markup"]["inline_keyboard"]]
    assert texts == ["🔁 Kuchen", "🔁 Brot", "🔁 Ohne Ende"]


def test_repeat_preview_mentions_template_photos(tg):  # noqa: F811
    old = _promo("Alt", images=[{"path": "x.jpg", "is_primary": True}])
    _cb(tg, f"tp:rp:{old.pk}")
    assert "📷" in tg["sent"][-1]["text"]
