"""SEC-G2b: allauth видит настоящий IP клиента за Caddy.

Без ALLAUTH_TRUSTED_PROXY_COUNT allauth брал REMOTE_ADDR = адрес Caddy, и лимиты
входа (10 неудачных/мин на IP) действовали на всех пользователей сразу. Значение 1
безопасно только потому, что Caddy ПЕРЕЗАПИСЫВАЕТ X-Forwarded-For одним значением —
этот замок держит обе половины условия.
"""

from __future__ import annotations

import re
from pathlib import Path

from django.test import RequestFactory, override_settings

ROOT = Path(__file__).resolve().parents[3]


def test_production_trusts_exactly_one_proxy():
    src = (ROOT / "config" / "settings" / "production.py").read_text()
    assert re.search(
        r'ALLAUTH_TRUSTED_PROXY_COUNT = env\.int\("ALLAUTH_TRUSTED_PROXY_COUNT", default=1\)', src
    )


def test_every_caddy_proxy_block_overwrites_forwarded_for():
    caddy = (ROOT / "caddy" / "Caddyfile").read_text()
    blocks = caddy.count("reverse_proxy web:8000")
    assert blocks >= 1
    assert caddy.count("header_up X-Forwarded-For {http.request.remote.host}") == blocks


@override_settings(ALLAUTH_TRUSTED_PROXY_COUNT=1)
def test_allauth_takes_the_client_address_set_by_caddy():
    from allauth.core.internal.httpkit import get_client_ip

    req = RequestFactory().get("/", REMOTE_ADDR="172.18.0.5", HTTP_X_FORWARDED_FOR="203.0.113.7")
    assert get_client_ip(req) == "203.0.113.7"
    # проба контейнера изнутри — без заголовка, фолбэк на REMOTE_ADDR, не исключение
    assert get_client_ip(RequestFactory().get("/", REMOTE_ADDR="127.0.0.1")) == "127.0.0.1"
