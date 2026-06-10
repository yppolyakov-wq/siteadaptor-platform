"""Тесты rate-limit хелпера (Hardening H8). Идентификаторы — uuid, чтобы
счётчики не пересекались между тестами/прогонами (TTL ключей переживает тест).
"""

import uuid

from django.test import RequestFactory

from apps.core import ratelimit


def _ident():
    return uuid.uuid4().hex


def test_hit_allows_until_limit_then_blocks():
    ident = _ident()
    assert all(not ratelimit.hit("t", ident, limit=3, window=60) for _ in range(3))
    assert ratelimit.hit("t", ident, limit=3, window=60) is True
    assert ratelimit.hit("t", ident, limit=3, window=60) is True  # и дальше блок


def test_idents_are_independent():
    a, b = _ident(), _ident()
    for _ in range(4):
        ratelimit.hit("t", a, limit=3, window=60)
    assert ratelimit.hit("t", b, limit=3, window=60) is False


def test_scopes_are_independent():
    ident = _ident()
    for _ in range(4):
        ratelimit.hit("s1", ident, limit=3, window=60)
    assert ratelimit.hit("s2", ident, limit=3, window=60) is False


def test_client_ip_prefers_first_x_forwarded_for():
    req = RequestFactory().get("/", HTTP_X_FORWARDED_FOR="1.2.3.4, 5.6.7.8")
    assert ratelimit.client_ip(req) == "1.2.3.4"


def test_client_ip_falls_back_to_remote_addr():
    assert ratelimit.client_ip(RequestFactory().get("/")) == "127.0.0.1"
