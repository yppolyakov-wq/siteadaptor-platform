"""SEC-A5 (аудит безопасности 2026-11-01): `app_signup` принимает повтор initData только с
адреса первого входа — как `app_auth`. Иначе перехваченная строка initData, отправленная с
любого IP, положила бы Telegram жертвы в сессию атакующего, и после его регистрации чат
жертвы стал бы владельцем чужого бизнеса (`links.complete_pending`)."""

import pytest

from apps.platform_bot import miniapp
from apps.platform_bot.tests.test_t830_miniapp_views import (  # noqa: F401
    UID,
    _init_data,
    _post,
    on,  # noqa: F401
)

pytestmark = pytest.mark.django_db


def _signup(init_data, ip):
    import json
    from importlib import import_module
    from urllib.parse import urlencode

    from django.conf import settings as dj_settings
    from django.contrib.messages.middleware import MessageMiddleware
    from django.test import RequestFactory

    req = RequestFactory().post(
        "/tg/app/registrieren/",
        urlencode({"init_data": init_data}),
        content_type="application/x-www-form-urlencoded",
        HTTP_X_TG_APP="1",
        REMOTE_ADDR=ip,
    )
    req.session = import_module(dj_settings.SESSION_ENGINE).SessionStore()
    MessageMiddleware(lambda r: None).process_request(req)
    resp = miniapp.app_signup(req)
    return resp.status_code, json.loads(resp.content)


def test_replayed_init_data_from_other_ip_is_refused(on, monkeypatch):  # noqa: F811
    monkeypatch.setattr("apps.platform_bot.web_signup.allowed", lambda uid: True)
    init_data = _init_data()
    status, _body = _post(miniapp.app_auth, {"init_data": init_data}, REMOTE_ADDR="10.0.0.1")
    assert status == 200  # первый вход — с адреса жертвы
    status, body = _signup(init_data, "10.9.9.9")  # перехваченная строка с другого адреса
    assert status == 403 and body["error"] == "replay"


def test_replayed_init_data_from_same_ip_is_accepted(on, monkeypatch):  # noqa: F811
    monkeypatch.setattr("apps.platform_bot.web_signup.allowed", lambda uid: True)
    init_data = _init_data()
    _post(miniapp.app_auth, {"init_data": init_data}, REMOTE_ADDR="10.0.0.1")
    status, body = _signup(init_data, "10.0.0.1")
    assert status == 200 and body["next"] == "/aktion-starten/"


def test_chooser_ticket_carries_grace(on):  # noqa: F811
    from apps.core import tg_login
    from apps.core.models import Membership
    from apps.platform_bot import links
    from apps.platform_bot.tests.test_t830_miniapp_views import _owner, _tenant

    user = _owner(Membership.ROLE_OWNER)
    for _ in range(2):
        links.bind(UID, _tenant(), user_pk=user.pk)
    status, body = _post(miniapp.app_auth, {"init_data": _init_data()}, REMOTE_ADDR="10.0.0.1")
    assert status == 200 and body.get("ticket")
    ticket = on.get(miniapp._ticket_key(body["ticket"]))
    assert ticket["grace"]  # сессия через выбор бизнеса гасится повтором initData
    status, body = _post(miniapp.app_choose, {"ticket": body["ticket"], "link": ticket["links"][0]})
    token = body["next"].rstrip("/").rsplit("/", 1)[-1]
    schema = links.OwnerTelegramLink.objects.get(pk=ticket["links"][0]).tenant.schema_name
    assert tg_login.peek(schema, token)["grace"] == ticket["grace"]
