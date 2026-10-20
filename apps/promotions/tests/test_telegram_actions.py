"""T-8.10h H-7e: «/aktionen» — статус и ⏸/▶/⏹ только через FSM, права на каждом нажатии.

План — docs/t8-10h-h7-owner-bot-ux-plan-2026-10-20.md §2.
"""

import pytest

from apps.promotions import telegram_actions as ta
from apps.promotions import telegram_promo as tp
from apps.promotions.models import Promotion
from apps.promotions.tests.test_telegram_promo import OWNER, _cb, _draft, _msg, tg  # noqa: F401

pytestmark = pytest.mark.django_db


def _published(tg):  # noqa: F811
    token, _p = _draft(tg)
    assert _cb(tg, f"tp:ok:{token}") == "published"
    return Promotion.objects.get()


def _datas(entry):
    return [
        b.get("callback_data") or b.get("url")
        for row in (entry["markup"] or {}).get("inline_keyboard", [])
        for b in row
    ]


def test_command_lists_promotions(tg):  # noqa: F811
    promo = _published(tg)
    upd = tp.slim_update(_msg("/aktionen"))
    assert tp._handle(tg["bot"], tg["tenant"], "public", str(OWNER), upd) == "actions_menu"
    assert f"ta:s:{promo.pk}" in _datas(tg["sent"][-1])


def test_empty_list(tg):  # noqa: F811
    upd = tp.slim_update(_msg("/aktionen"))
    assert tp._handle(tg["bot"], tg["tenant"], "public", str(OWNER), upd) == "actions_empty"


def test_card_buttons_follow_status(tg):  # noqa: F811
    promo = _published(tg)
    assert _cb(tg, f"ta:s:{promo.pk}") == "action_card"
    datas = _datas(tg["sent"][-1])
    assert f"ta:p:{promo.pk}" in datas and f"ta:e:{promo.pk}" in datas
    assert f"ta:a:{promo.pk}" not in datas
    assert any(str(d).endswith(f"/promotions/{promo.pk}/aushang.pdf") for d in datas)


def test_pause_resume_via_fsm(tg):  # noqa: F811
    promo = _published(tg)
    assert _cb(tg, f"ta:p:{promo.pk}") == "action_paused"
    promo.refresh_from_db()
    assert promo.status == "paused"
    # двойное нажатие — без повторных эффектов
    assert _cb(tg, f"ta:p:{promo.pk}") == "action_card"
    assert "Schon erledigt" in tg["sent"][-1]["text"]
    assert _cb(tg, f"ta:a:{promo.pk}") == "action_active"
    promo.refresh_from_db()
    assert promo.status == "active"


def test_end_needs_confirmation(tg):  # noqa: F811
    promo = _published(tg)
    assert _cb(tg, f"ta:e:{promo.pk}") == "end_confirm"
    promo.refresh_from_db()
    assert promo.status == "active"
    assert f"ta:E:{promo.pk}" in _datas(tg["sent"][-1])
    assert _cb(tg, f"ta:E:{promo.pk}") == "action_ended"
    promo.refresh_from_db()
    assert promo.status == "ended"
    assert f"tp:rp:{promo.pk}" in _datas(tg["sent"][-1])  # закончилась — можно повторить
    # старая кнопка ⏸ после завершения — недопустимый переход словами, статус цел
    assert _cb(tg, f"ta:p:{promo.pk}") == "action_card"
    assert "Nicht möglich" in tg["sent"][-1]["text"]
    promo.refresh_from_db()
    assert promo.status == "ended"


def test_resume_respects_activation_limit(tg, monkeypatch):  # noqa: F811
    from apps.promotions import limits

    promo = _published(tg)
    _cb(tg, f"ta:p:{promo.pk}")

    def deny(*a, **k):
        raise limits.ActivationLimit(5)

    monkeypatch.setattr(limits, "activate", deny)
    assert _cb(tg, f"ta:a:{promo.pk}") == "limit"
    promo.refresh_from_db()
    assert promo.status == "paused"


def test_foreign_sender_denied(tg):  # noqa: F811
    promo = _published(tg)
    assert _cb(tg, f"ta:p:{promo.pk}", sender=999, chat=999) == "denied"
    promo.refresh_from_db()
    assert promo.status == "active"


def test_unknown_promo(tg):  # noqa: F811
    assert _cb(tg, "ta:s:00000000-0000-0000-0000-000000000000") == "action_missing"


@pytest.mark.parametrize("data", ["ta:x:00000000-0000-0000-0000-000000000000", "ta:p:1", "ta:p:"])
def test_bad_callbacks_skip(data):
    assert not ta.CALLBACK_RE.match(data)


def test_platform_router_accepts_actions(monkeypatch):
    import uuid

    from django.core.cache.backends.locmem import LocMemCache

    from apps.platform_bot import routing

    monkeypatch.setattr(routing, "cache", LocMemCache(f"r-{uuid.uuid4()}", {}))
    inner = f"ta:p:{uuid.uuid4()}"
    ref = routing.wrap(5, "shop1", inner)
    assert routing.resolve(5, ref) == ("shop1", inner)
    assert routing.resolve(6, ref) is None


def test_expired_paused_promo_cannot_be_resumed(tg):  # noqa: F811
    from datetime import timedelta

    from django.utils import timezone

    promo = _published(tg)
    _cb(tg, f"ta:p:{promo.pk}")
    Promotion.objects.filter(pk=promo.pk).update(ends_at=timezone.now() - timedelta(hours=1))
    assert _cb(tg, f"ta:s:{promo.pk}") == "action_card"
    assert f"ta:a:{promo.pk}" not in _datas(tg["sent"][-1])
    assert _cb(tg, f"ta:a:{promo.pk}") == "action_card"
    assert "Abgelaufen" in tg["sent"][-1]["text"]
    promo.refresh_from_db()
    assert promo.status == "paused"


def test_archived_promo_is_missing(tg):  # noqa: F811
    promo = _published(tg)
    Promotion.objects.filter(pk=promo.pk).update(status="archived")
    assert _cb(tg, f"ta:E:{promo.pk}") == "action_missing"
    assert _cb(tg, f"ta:w:{promo.pk}") == "action_missing"


def test_platform_callback_denied_for_unlinked_user(tg):  # noqa: F811
    promo = _published(tg)
    callback = {"id": "c", "from_id": 4242, "chat_id": 4242, "message_id": 1}
    assert (
        tp.handle_platform_callback(tg["bot"], "public", callback, f"ta:p:{promo.pk}") == "denied"
    )
    promo.refresh_from_db()
    assert promo.status == "active"
