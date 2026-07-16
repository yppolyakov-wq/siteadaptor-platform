"""Защита от SSRF для URL, задаваемых владельцем (iCal-фиды, будущий отправитель
вебхуков).

Владелец в мультитенанте — low-trust: без фильтрации он может заставить сервер
сходить GET'ом на облачные метаданные (169.254.169.254), loopback или внутренние
сервисы. `validate_public_url` резолвит хост и отклоняет все приватные/loopback/
link-local/reserved/multicast адреса; `safe_get` дополнительно ограничивает схему,
таймаут и размер ответа.

Остаточный вектор — DNS-rebinding (TOCTOU между резолвингом и коннектом requests):
для сильной защиты подключение нужно пинить к уже проверенному IP. Здесь резолвим
и валидируем ВСЕ адреса хоста до запроса — это закрывает реалистичные атаки
(метаданные/внутренние диапазоны); пиннинг — отдельным шагом при усилении.
"""

import ipaddress
import socket
from urllib.parse import urlparse

import requests

_ALLOWED_SCHEMES = {"http", "https"}
_MAX_BYTES = 2 * 1024 * 1024  # 2 МБ — календарные фиды небольшие
_TIMEOUT = 10


class SsrfError(ValueError):
    """URL отклонён политикой egress (приватный адрес / запрещённая схема)."""


def _is_blocked(ip: ipaddress._BaseAddress) -> bool:
    return (
        ip.is_private
        or ip.is_loopback
        or ip.is_link_local
        or ip.is_multicast
        or ip.is_reserved
        or ip.is_unspecified
    )


def validate_public_url(raw: str) -> str:
    """Проверить URL: схема http(s) + ВСЕ резолвленные IP публичны. Вернуть URL или
    бросить SsrfError."""
    parsed = urlparse((raw or "").strip())
    if parsed.scheme not in _ALLOWED_SCHEMES:
        raise SsrfError("Nur http/https-URLs sind erlaubt.")
    host = parsed.hostname
    if not host:
        raise SsrfError("Ungültige URL.")
    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    try:
        infos = socket.getaddrinfo(host, port, proto=socket.IPPROTO_TCP)
    except OSError as exc:
        raise SsrfError("Host konnte nicht aufgelöst werden.") from exc
    if not infos:
        raise SsrfError("Host konnte nicht aufgelöst werden.")
    for info in infos:
        ip = ipaddress.ip_address(info[4][0])
        if _is_blocked(ip):
            raise SsrfError(f"Interne Adresse ({ip}) ist nicht erlaubt.")
    return raw


def safe_get(url: str, *, timeout: int = _TIMEOUT, max_bytes: int = _MAX_BYTES) -> str:
    """GET с egress-фильтром + лимитом размера. Текст ответа. Бросает SsrfError на
    заблокированный URL, requests-исключения — как обычно."""
    validate_public_url(url)
    resp = requests.get(url, timeout=timeout, stream=True)
    resp.raise_for_status()
    chunks, total = [], 0
    for chunk in resp.iter_content(chunk_size=8192, decode_unicode=False):
        if not chunk:
            continue
        total += len(chunk)
        if total > max_bytes:
            resp.close()
            raise SsrfError("Antwort zu groß.")
        chunks.append(chunk)
    resp.close()
    return b"".join(chunks).decode(resp.encoding or "utf-8", errors="replace")
