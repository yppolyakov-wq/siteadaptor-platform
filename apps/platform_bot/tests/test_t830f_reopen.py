"""T-8.30f-1: повторное открытие Mini App той же initData (перезагрузка, потерянный ответ).

Повтор допускается до трёх входов, только с того же IP; решение принимается заново, а
прежний токен/билет гаснет — живым остаётся последний.
"""

import pytest

from apps.core import tg_login
from apps.platform_bot import links, miniapp, webapp_auth
from apps.platform_bot.tests.test_t830_miniapp_views import (  # noqa: F401
    TOKEN,
    UID,
    _init_data,
    _owner,
    _post,
    _tenant,
    on,
)

pytestmark = pytest.mark.django_db


def _token(body):
    return body["next"].rstrip("/").rsplit("/", 1)[-1]


def test_verify_allow_replay_marks_instead_of_raising():
    import time

    raw = _init_data()
    first = webapp_auth.verify(raw, TOKEN, now=int(time.time()), allow_replay=True)
    second = webapp_auth.verify(raw, TOKEN, now=int(time.time()), allow_replay=True)
    assert first["replay"] is False and second["replay"] is True
    assert first["digest"] == second["digest"]
    with pytest.raises(webapp_auth.InitDataError):
        webapp_auth.verify(raw, TOKEN, now=int(time.time()))


def test_reload_same_ip_gets_fresh_token_and_kills_previous():
    t = _tenant()
    links.bind(UID, t, user_pk=_owner().pk)
    raw = _init_data()
    s1, b1 = _post(miniapp.app_auth, {"init_data": raw})
    s2, b2 = _post(miniapp.app_auth, {"init_data": raw})
    assert s1 == s2 == 200 and _token(b1) != _token(b2)
    assert tg_login.peek(t.schema_name, _token(b1)) is None
    assert tg_login.peek(t.schema_name, _token(b2)) is not None


def test_at_most_three_logins_per_init_data():
    t = _tenant()
    links.bind(UID, t, user_pk=_owner().pk)
    raw = _init_data()
    codes = [_post(miniapp.app_auth, {"init_data": raw})[0] for _ in range(4)]
    assert codes == [200, 200, 200, 403]


def test_replay_from_other_ip_refused():
    t = _tenant()
    links.bind(UID, t, user_pk=_owner().pk)
    raw = _init_data()
    assert _post(miniapp.app_auth, {"init_data": raw})[0] == 200
    status, body = _post(miniapp.app_auth, {"init_data": raw}, REMOTE_ADDR="10.1.2.3")
    assert status == 403 and body["error"] == "replay"


def test_replay_decides_again_after_unlink():
    t = _tenant()
    links.bind(UID, t, user_pk=_owner().pk)
    raw = _init_data()
    assert "next" in _post(miniapp.app_auth, {"init_data": raw})[1]
    links.unbind(t)
    status, body = _post(miniapp.app_auth, {"init_data": raw})
    assert body["error"] == "unlinked" and "next" not in body


def test_replay_respects_restriction(monkeypatch):
    t = _tenant()
    links.bind(UID, t, user_pk=_owner().pk)
    raw = _init_data()
    _post(miniapp.app_auth, {"init_data": raw})
    monkeypatch.setattr("apps.platform_bot.rights.is_restricted", lambda uid: True)
    assert _post(miniapp.app_auth, {"init_data": raw})[1]["error"] == "restricted"


def test_replay_reissues_chooser_ticket_old_one_dead():
    a, b = _tenant("A"), _tenant("B")
    owner = _owner()
    links.bind(UID, a, user_pk=owner.pk)
    links.bind(UID, b, user_pk=owner.pk)
    raw = _init_data()
    first = _post(miniapp.app_auth, {"init_data": raw})[1]
    second = _post(miniapp.app_auth, {"init_data": raw})[1]
    link_id = first["choose"][0]["id"]
    status, _body = _post(miniapp.app_choose, {"ticket": first["ticket"], "link": link_id})
    assert status == 403
    status, body = _post(miniapp.app_choose, {"ticket": second["ticket"], "link": link_id})
    assert status == 200 and "next" in body


def test_expired_has_own_message():
    import time

    status, body = _post(
        miniapp.app_auth, {"init_data": _init_data(auth_date=int(time.time()) - 3600)}
    )
    assert status == 403 and body["error"] == "expired"
    assert "neu öffnen" in body["message"]


def test_page_has_retry_and_close():
    from django.test import RequestFactory

    body = miniapp.app_entry(RequestFactory().get("/tg/app/")).content.decode()
    assert "data-retry" in body and "data-close" in body
