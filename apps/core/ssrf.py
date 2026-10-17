"""Защита от SSRF для URL, задаваемых владельцем (iCal-фиды, будущий отправитель
вебхуков).

Владелец в мультитенанте — low-trust: без фильтрации он может заставить сервер
сходить GET'ом на облачные метаданные (169.254.169.254), loopback или внутренние
сервисы. `validate_public_url` резолвит хост и отклоняет все приватные/loopback/
link-local/reserved/multicast адреса; `safe_get` дополнительно ограничивает схему,
таймаут и размер ответа.

T-8.27a: `safe_fetch` — общий транспорт для чужих URL (iCal, импорт сайта клиента):
редиректы НЕ следуются автоматически — каждый хоп проверяется заново; адрес, к
которому реально подключился сокет, сверяется ПОСЛЕ коннекта (закрывает
DNS-rebinding: проверка резолвинга и коннект — разные запросы к DNS); прокси из
окружения не используются (иначе «пир» = прокси, а цель не проверяется); лимиты
размера, времени, типа содержимого и портов.
"""

import ipaddress
import socket
import time
from dataclasses import dataclass
from urllib.parse import urljoin, urlparse

import requests
from django.utils.translation import gettext as _
from requests.adapters import HTTPAdapter
from urllib3.connection import HTTPConnection, HTTPSConnection
from urllib3.connectionpool import HTTPConnectionPool, HTTPSConnectionPool

_ALLOWED_SCHEMES = {"http", "https"}
_MAX_BYTES = 2 * 1024 * 1024  # 2 МБ — календарные фиды небольшие
_TIMEOUT = 10


class SsrfError(ValueError):
    """URL отклонён политикой egress (приватный адрес / запрещённая схема)."""


def _is_blocked(ip: ipaddress._BaseAddress) -> bool:
    mapped = getattr(ip, "ipv4_mapped", None)  # ::ffff:10.0.0.1 — тот же внутренний адрес
    if mapped is not None:
        ip = mapped
    return (
        ip.is_private
        or ip.is_loopback
        or ip.is_link_local
        or ip.is_multicast
        or ip.is_reserved
        or ip.is_unspecified
    )


def _resolve(host: str, port: int):
    return socket.getaddrinfo(host, port, proto=socket.IPPROTO_TCP)


def validate_public_url(raw: str) -> str:
    """Проверить URL: схема http(s) + ВСЕ резолвленные IP публичны. Вернуть URL или
    бросить SsrfError."""
    parsed = urlparse((raw or "").strip())
    if parsed.scheme not in _ALLOWED_SCHEMES:
        raise SsrfError(_("Nur http/https-URLs sind erlaubt."))
    host = parsed.hostname
    if not host:
        raise SsrfError(_("Ungültige URL."))
    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    try:
        infos = _resolve(host, port)
    except OSError as exc:
        raise SsrfError(_("Host konnte nicht aufgelöst werden.")) from exc
    if not infos:
        raise SsrfError(_("Host konnte nicht aufgelöst werden."))
    for info in infos:
        ip = ipaddress.ip_address(info[4][0])
        if _is_blocked(ip):
            raise SsrfError(_("Interne Adresse (%(ip)s) ist nicht erlaubt.") % {"ip": ip})
    return raw


_REDIRECTS = {301, 302, 303, 307, 308}
DEFAULT_PORTS = (80, 443)


@dataclass(frozen=True)
class Fetched:
    """Ответ `safe_fetch`: итоговый URL (после проверенных редиректов), статус, тип."""

    url: str
    status: int
    content_type: str
    body: bytes
    encoding: str | None = None

    @property
    def ok(self) -> bool:
        return 200 <= self.status < 300

    def text(self) -> str:
        return self.body.decode(self.encoding or "utf-8", errors="replace")


def _check_peer(ip: ipaddress._BaseAddress) -> None:
    """Фактический адрес сокета после коннекта. Отдельная функция — тест подменяет её,
    чтобы гонять транспорт на локальном сервере (127.0.0.1)."""
    if _is_blocked(ip):
        raise SsrfError(_("Interne Adresse (%(ip)s) ist nicht erlaubt.") % {"ip": ip})


class _PeerCheckMixin:
    def _new_conn(self):
        sock = super()._new_conn()
        try:
            _check_peer(ipaddress.ip_address(sock.getpeername()[0]))
        except BaseException:
            sock.close()
            raise
        return sock


class _CheckedHTTPConnection(_PeerCheckMixin, HTTPConnection):
    pass


class _CheckedHTTPSConnection(_PeerCheckMixin, HTTPSConnection):
    pass


class _CheckedHTTPPool(HTTPConnectionPool):
    ConnectionCls = _CheckedHTTPConnection


class _CheckedHTTPSPool(HTTPSConnectionPool):
    ConnectionCls = _CheckedHTTPSConnection


class _CheckedAdapter(HTTPAdapter):
    def init_poolmanager(self, *args, **kwargs):
        super().init_poolmanager(*args, **kwargs)
        self.poolmanager.pool_classes_by_scheme = {
            "http": _CheckedHTTPPool,
            "https": _CheckedHTTPSPool,
        }


def _session() -> requests.Session:
    session = requests.Session()
    session.trust_env = False  # без прокси из окружения: пир обязан быть самой целью
    adapter = _CheckedAdapter(max_retries=0)
    session.mount("http://", adapter)
    session.mount("https://", adapter)
    return session


def _type_allowed(content_type: str, accept) -> bool:
    if not accept:
        return True
    for item in accept:
        if item.endswith("/") and content_type.startswith(item):
            return True
        if content_type == item:
            return True
    return False


def safe_fetch(
    url: str,
    *,
    accept=("text/html", "application/xhtml+xml"),
    max_bytes: int = _MAX_BYTES,
    timeout: int = _TIMEOUT,
    max_redirects: int = 5,
    allowed_ports=DEFAULT_PORTS,
    headers: dict | None = None,
    session: requests.Session | None = None,
) -> Fetched:
    """GET чужого URL под egress-политикой. Каждый хоп: схема http(s), порт из списка,
    все резолвленные IP публичны, фактический пир публичен. Ответ не-2xx возвращается
    со статусом без тела; 2xx — с телом, если тип из `accept` и размер ≤ `max_bytes`.
    Бросает SsrfError (политика) или requests-исключения (сеть)."""
    own = session is None
    session = session or _session()
    deadline = time.monotonic() + timeout * (max_redirects + 1)
    try:
        current = url
        for _hop in range(max_redirects + 1):
            parsed = urlparse(current)
            port = parsed.port or (443 if parsed.scheme == "https" else 80)
            if allowed_ports is not None and port not in allowed_ports:
                raise SsrfError(_("Port %(port)s ist nicht erlaubt.") % {"port": port})
            validate_public_url(current)
            if time.monotonic() > deadline:
                raise SsrfError(_("Zeitlimit überschritten."))
            resp = session.get(
                current,
                timeout=timeout,
                stream=True,
                allow_redirects=False,
                headers=headers or {},
            )
            try:
                if resp.status_code in _REDIRECTS and resp.headers.get("Location"):
                    current = urljoin(current, resp.headers["Location"])
                    continue
                content_type = (
                    (resp.headers.get("Content-Type") or "").split(";")[0].strip().lower()
                )
                if not 200 <= resp.status_code < 300:
                    return Fetched(current, resp.status_code, content_type, b"")
                if not _type_allowed(content_type, accept):
                    raise SsrfError(_("Inhaltstyp nicht erlaubt."))
                declared = resp.headers.get("Content-Length")
                if declared and declared.isdigit() and int(declared) > max_bytes:
                    raise SsrfError(_("Antwort zu groß."))
                chunks, total = [], 0
                for chunk in resp.iter_content(chunk_size=8192):
                    if not chunk:
                        continue
                    total += len(chunk)
                    if total > max_bytes:
                        raise SsrfError(_("Antwort zu groß."))
                    if time.monotonic() > deadline:
                        raise SsrfError(_("Zeitlimit überschritten."))
                    chunks.append(chunk)
                return Fetched(
                    current, resp.status_code, content_type, b"".join(chunks), resp.encoding
                )
            finally:
                resp.close()
        raise SsrfError(_("Zu viele Weiterleitungen."))
    finally:
        if own:
            session.close()


def safe_get(url: str, *, timeout: int = _TIMEOUT, max_bytes: int = _MAX_BYTES) -> str:
    """GET с egress-фильтром + лимитом размера (iCal-фиды). Текст ответа. Бросает
    SsrfError на заблокированный URL; не-2xx — как раньше, `requests.HTTPError`.
    T-8.27a: поверх `safe_fetch` — редиректы проверяются на каждом хопе (раньше
    requests следовал им сам, и фид мог увести на внутренний адрес)."""
    fetched = safe_fetch(url, accept=None, timeout=timeout, max_bytes=max_bytes, allowed_ports=None)
    if not fetched.ok:
        raise requests.HTTPError(f"HTTP {fetched.status}")
    return fetched.text()
