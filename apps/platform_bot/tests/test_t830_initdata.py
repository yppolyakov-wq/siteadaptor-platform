"""T-8.30: проверка подписи Telegram Mini App (план docs/t8-30-miniapp-plan-2026-10-20.md)."""

import hashlib
import hmac
import json
import logging
import uuid
from urllib.parse import urlencode

import pytest
from django.core.cache.backends.locmem import LocMemCache

from apps.platform_bot import webapp_auth
from apps.platform_bot.webapp_auth import InitDataError, verify

TOKEN = "123456:TEST-FAKE-TOKEN"
NOW = 1700000010
USER = '{"id":42,"first_name":"A","language_code":"de"}'
FIELDS = {"auth_date": "1700000000", "query_id": "AAHtest", "user": USER}
# Зафиксировано один раз независимой реализацией (hmac/hashlib в отдельном процессе).
GOLDEN = "8c87b637b80168637e9e8f62ca090a427778f5d3d7eda236261768e0e75a7339"


@pytest.fixture(autouse=True)
def _private_cache(monkeypatch):
    store = LocMemCache(f"tgapp-test-{uuid.uuid4()}", {})
    monkeypatch.setattr(webapp_auth, "cache", store)
    return store


def _ref_hash(fields, token=TOKEN):
    """Независимая эталонная реализация (не через модуль)."""
    dcs = "\n".join(f"{k}={fields[k]}" for k in sorted(fields) if k != "hash")
    secret = hmac.new(b"WebAppData", token.encode(), hashlib.sha256).digest()
    return hmac.new(secret, dcs.encode(), hashlib.sha256).hexdigest()


def _signed(fields=None, token=TOKEN, order=None):
    fields = dict(FIELDS if fields is None else fields)
    fields["hash"] = _ref_hash(fields, token)
    keys = order or list(fields)
    return urlencode([(k, fields[k]) for k in keys])


def test_golden_vector():
    assert _ref_hash(FIELDS) == GOLDEN
    out = verify(_signed(), TOKEN, now=NOW)
    assert out == {"uid": 42, "language_code": "de", "start_param": ""}


def test_order_independent_and_signature_field_included():
    fields = {**FIELDS, "signature": "abc", "start_param": "go"}
    raw = _signed(
        fields, order=["user", "hash", "signature", "auth_date", "start_param", "query_id"]
    )
    assert verify(raw, TOKEN, now=NOW)["start_param"] == "go"


def _tamper(raw, key, value):
    parts = dict(p.split("=", 1) for p in raw.split("&"))
    parts[key] = value
    return "&".join(f"{k}={v}" for k, v in parts.items())


@pytest.mark.parametrize(
    "mutate",
    [
        lambda raw: _tamper(raw, "user", "%7B%22id%22%3A43%7D"),
        lambda raw: _tamper(raw, "auth_date", "1700000005"),
        lambda raw: raw + "&extra=1",
        lambda raw: "&".join(p for p in raw.split("&") if not p.startswith("query_id=")),
        lambda raw: _tamper(raw, "hash", GOLDEN.upper()),
    ],
    ids=["user-id", "auth-date", "added-field", "dropped-field", "uppercase-hash"],
)
def test_tampering_is_rejected(mutate):
    with pytest.raises(InitDataError) as exc:
        verify(mutate(_signed()), TOKEN, now=NOW)
    assert exc.value.code == "bad_hash"


def test_wrong_algorithm_and_wrong_token_rejected():
    fields = dict(FIELDS)
    dcs = "\n".join(f"{k}={fields[k]}" for k in sorted(fields))
    login_widget = hmac.new(hashlib.sha256(TOKEN.encode()).digest(), dcs.encode(), hashlib.sha256)
    raw = urlencode([*fields.items(), ("hash", login_widget.hexdigest())])
    with pytest.raises(InitDataError, match="bad_hash"):
        verify(raw, TOKEN, now=NOW)
    with pytest.raises(InitDataError, match="bad_hash"):
        verify(_signed(token="999:OTHER"), TOKEN, now=NOW)


@pytest.mark.parametrize(
    "raw,code",
    [
        ("", "malformed"),
        ("auth_date=1&auth_date=2&hash=x", "malformed"),
        ("auth_date=1700000000&user=x", "malformed"),
        ("a=" + "x" * 5000, "malformed"),
        ("no-equals-sign", "malformed"),
    ],
)
def test_malformed(raw, code):
    with pytest.raises(InitDataError) as exc:
        verify(raw, TOKEN, now=NOW)
    assert exc.value.code == code


@pytest.mark.parametrize("user", ["not-json", '{"id":"42"}', '{"id":0}', '{"id":true}', "[]"])
def test_bad_user(user):
    with pytest.raises(InitDataError, match="bad_user"):
        verify(_signed({**FIELDS, "user": user}), TOKEN, now=NOW)


@pytest.mark.parametrize("now,ok", [(1700000300, True), (1700000301, False), (1699999969, False)])
def test_time_window(now, ok):
    raw = _signed()
    if ok:
        assert verify(raw, TOKEN, now=now)["uid"] == 42
    else:
        with pytest.raises(InitDataError, match="expired"):
            verify(raw, TOKEN, now=now)


def test_replay_rejected_and_failure_does_not_burn():
    raw = _signed()
    with pytest.raises(InitDataError, match="expired"):
        verify(raw, TOKEN, now=NOW + 1000)  # провал — подпись не отмечена
    assert verify(raw, TOKEN, now=NOW)["uid"] == 42
    with pytest.raises(InitDataError, match="replay"):
        verify(raw, TOKEN, now=NOW)


def test_no_token():
    with pytest.raises(InitDataError, match="no_token"):
        verify(_signed(), "", now=NOW)


def test_init_data_never_logged(caplog):
    raw = _signed({**FIELDS, "user": json.dumps({"id": 42, "first_name": "Geheimname"})})
    caplog.set_level(logging.DEBUG)
    verify(raw, TOKEN, now=NOW)
    with pytest.raises(InitDataError):
        verify(raw, TOKEN, now=NOW)
    assert "Geheimname" not in caplog.text and GOLDEN not in caplog.text


def test_non_ascii_hash_is_malformed_not_500():
    """Ревью: compare_digest бросает TypeError на не-ASCII str — был бы 500."""
    with pytest.raises(webapp_auth.InitDataError) as exc:
        webapp_auth.verify("auth_date=1&hash=%C3%A9", "1:x", now=1)
    assert exc.value.code == "malformed"
