"""T-8.30: вход Mini App на публичном хосте (план docs/t8-30-miniapp-plan-2026-10-20.md)."""

import json
import time
import uuid
from urllib.parse import urlencode

import pytest
from django.contrib.auth import get_user_model
from django.core.cache.backends.locmem import LocMemCache
from django.test import RequestFactory

from apps.core import tg_login
from apps.core.models import Membership
from apps.platform_bot import links, miniapp, webapp_auth
from apps.platform_bot.tests.test_t830_initdata import _ref_hash
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db
TOKEN = "123456:TEST-FAKE-TOKEN"
UID = 4242


@pytest.fixture(autouse=True)
def on(settings, monkeypatch):
    settings.TELEGRAM_PLATFORM_BOT_ENABLED = True
    settings.TELEGRAM_PLATFORM_BOT_TOKEN = TOKEN
    settings.TELEGRAM_PLATFORM_BOT_USERNAME = "PlattformBot"
    settings.ROOT_URLCONF = "config.urls_public"
    store = LocMemCache(f"tgapp-views-{uuid.uuid4()}", {})
    for mod in (webapp_auth, miniapp, tg_login):
        monkeypatch.setattr(mod, "cache", store)
    return store


def _tenant(name="Krume"):
    slug = f"ma-{uuid.uuid4().hex[:6]}"
    return TenantFactory(schema_name=slug.replace("-", "_"), slug=slug, name=name)


def _owner(role=Membership.ROLE_OWNER, active=True):
    o = uuid.uuid4().hex[:8]
    user = get_user_model().objects.create_user(username=f"ma-{o}", password="pw12345678")
    user.is_active = active
    user.save()
    Membership.objects.create(user=user, role=role)
    return user


def _init_data(uid=UID, auth_date=None, lang="de"):
    fields = {
        "auth_date": str(auth_date or int(time.time())),
        "query_id": uuid.uuid4().hex,  # уникальный хеш — без «повтора» между запросами
        "user": json.dumps({"id": uid, "first_name": "A", "language_code": lang}),
    }
    fields["hash"] = _ref_hash(fields, TOKEN)
    return urlencode(fields)


def _post(view, data, **headers):
    req = RequestFactory().post(
        "/tg/app/auth/",
        urlencode(data),
        content_type="application/x-www-form-urlencoded",
        **headers,
    )
    resp = view(req)
    return resp.status_code, json.loads(resp.content)


def _auth(**kw):
    return _post(miniapp.app_auth, {"init_data": _init_data(**kw)})


def test_single_business_hands_off_to_tenant():
    t = _tenant()
    user = _owner()
    links.bind(UID, t, user_pk=user.pk)
    status, body = _auth()
    assert status == 200
    assert body["next"].startswith(f"https://{t.slug}.") and "/tg/start/" in body["next"]
    token = body["next"].rstrip("/").rsplit("/", 1)[-1]
    payload = tg_login.peek(t.schema_name, token)
    assert payload["user_pk"] == user.pk and payload["uid"] == UID


def test_unlinked_user_gets_no_token():
    status, body = _auth(uid=999001)
    assert status == 200 and body["error"] == "unlinked" and "next" not in body


def test_restricted_user_refused(monkeypatch):
    t = _tenant()
    links.bind(UID, t, user_pk=_owner().pk)
    monkeypatch.setattr("apps.platform_bot.rights.is_restricted", lambda uid: True)
    assert _auth()[1]["error"] == "restricted"


def test_demoted_owner_falls_back_to_email_login():
    t = _tenant()
    user = _owner()
    links.bind(UID, t, user_pk=user.pk)
    Membership.objects.filter(user=user).update(role=Membership.ROLE_STAFF)
    status, body = _auth()
    assert body["error"] == "no_owner" and "/anmelden/link/" in body["login_url"]


def test_two_owners_without_marker_refused():
    t = _tenant()
    _owner()
    _owner()
    links.bind(UID, t)  # без user_pk (регистрация через бот)
    assert _auth()[1]["error"] == "no_owner"


def test_blocked_link_counts_as_unlinked():
    t = _tenant()
    links.bind(UID, t, user_pk=_owner().pk)
    links.mark_blocked(UID)
    assert _auth()[1]["error"] == "unlinked"


def test_many_businesses_chooser_and_ticket_single_use():
    a, b = _tenant("A"), _tenant("B")
    owner = _owner()
    links.bind(UID, a, user_pk=owner.pk)
    links.bind(UID, b, user_pk=owner.pk)
    status, body = _auth()
    assert {c["name"] for c in body["choose"]} == {"A", "B"} and "next" not in body
    link_id = next(c["id"] for c in body["choose"] if c["name"] == "B")
    status, chosen = _post(miniapp.app_choose, {"ticket": body["ticket"], "link": link_id})
    assert status == 200 and f"https://{b.slug}." in chosen["next"]
    status, again = _post(miniapp.app_choose, {"ticket": body["ticket"], "link": link_id})
    assert status == 403 and again["error"] == "ticket"


def test_chooser_rejects_foreign_link():
    a, b = _tenant("A"), _tenant("B")
    owner = _owner()
    links.bind(UID, a, user_pk=owner.pk)
    links.bind(UID, b, user_pk=owner.pk)
    other = links.bind(555, _tenant("C"), user_pk=owner.pk)
    body = _auth()[1]
    status, out = _post(miniapp.app_choose, {"ticket": body["ticket"], "link": str(other.pk)})
    assert status == 403 and "next" not in out


def test_bad_signature_and_replay():
    status, body = _post(miniapp.app_auth, {"init_data": "auth_date=1&hash=00"})
    assert status == 403 and body["error"] in ("bad_hash", "malformed")
    t = _tenant()
    links.bind(UID, t, user_pk=_owner().pk)
    raw = _init_data()
    assert _post(miniapp.app_auth, {"init_data": raw})[0] == 200
    # T-8.30f: повтор с ДРУГОГО адреса — отказ (с того же — см. test_t830f_reopen)
    status, body = _post(miniapp.app_auth, {"init_data": raw}, REMOTE_ADDR="10.9.9.9")
    assert status == 403 and body["error"] == "replay"


def test_bot_off_503(settings):
    settings.TELEGRAM_PLATFORM_BOT_ENABLED = False
    assert _auth()[0] == 503


def test_foreign_origin_403():
    status, body = _post(
        miniapp.app_auth, {"init_data": _init_data()}, HTTP_ORIGIN="https://evil.example"
    )
    assert status == 403 and body["error"] == "origin"


def test_wrong_content_type_415():
    req = RequestFactory().post(
        "/tg/app/auth/", json.dumps({"init_data": "x"}), content_type="application/json"
    )
    assert miniapp.app_auth(req).status_code == 415


def test_auth_is_post_only():
    assert miniapp.app_auth(RequestFactory().get("/tg/app/auth/")).status_code == 405


def test_ip_rate_limit():
    codes = [_post(miniapp.app_auth, {"init_data": "x=1"})[0] for _ in range(31)]
    assert codes[-1] == 429


def test_entry_page_frameable_only_by_telegram_web():
    resp = miniapp.app_entry(RequestFactory().get("/tg/app/"))
    assert resp.status_code == 200
    assert resp["Content-Security-Policy"] == "frame-ancestors https://web.telegram.org"
    assert getattr(resp, "xframe_options_exempt", False)
    body = resp.content.decode()
    assert "telegram-web-app.js" in body and "data-miniapp" in body


def test_cabinet_link_without_marker_does_not_guess_owner():
    """Ревью M-2: метку стёрли — чат бывшего владельца не входит под новым."""
    t = _tenant()
    user = _owner()
    links.bind(UID, t)  # связь из кабинета, но без метки owner_user_pk
    assert _auth()[1]["error"] == "no_owner"
    links.bind(UID, t, via="signup")
    status, body = _auth()
    assert "/tg/start/" in body["next"]
    token = body["next"].rstrip("/").rsplit("/", 1)[-1]
    assert tg_login.peek(t.schema_name, token)["user_pk"] == user.pk
