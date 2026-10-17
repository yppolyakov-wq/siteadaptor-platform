"""T-8.27a: `safe_fetch` — проверка каждого хопа, фактического пира, размера, типа, порта.

Без внешней сети: локальный HTTP-сервер на 127.0.0.1. Проверку пира тест по умолчанию
разрешает для loopback (иначе до сервера не дойти), резолвинг подменён так, что любые
имена «публичны»; отдельные замки включают настоящую проверку пира."""

import ipaddress
import socket
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest
import requests

from apps.core import ssrf
from apps.core.ssrf import SsrfError, safe_fetch, safe_get

ROUTES = {}


class _Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def do_GET(self):
        status, headers, body = ROUTES.get(self.path, (404, {}, b""))
        self.send_response(status)
        for key, value in headers.items():
            self.send_header(key, value)
        if "Content-Length" not in headers:
            self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


@pytest.fixture
def server(monkeypatch):
    srv = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
    thread = threading.Thread(target=srv.serve_forever, daemon=True)
    thread.start()
    real_check = ssrf._check_peer

    def allow_loopback(ip):
        if ip.is_loopback:
            return
        real_check(ip)

    monkeypatch.setattr(ssrf, "_check_peer", allow_loopback)
    # «Публичный» резолвинг для проверки до коннекта; коннект идёт на настоящий хост.
    # Только проверке до коннекта (`ssrf._resolve`): сам коннект идёт на 127.0.0.1.
    monkeypatch.setattr(
        ssrf,
        "_resolve",
        lambda host, port: (
            [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", port))]
            if host == "127.0.0.1"
            else socket.getaddrinfo(host, port, proto=socket.IPPROTO_TCP)
        ),
    )
    ROUTES.clear()
    yield f"http://127.0.0.1:{srv.server_address[1]}"
    srv.shutdown()
    srv.server_close()


def _html(body=b"<html>ok</html>"):
    return (200, {"Content-Type": "text/html; charset=utf-8"}, body)


def test_fetch_returns_body_and_final_url(server):
    ROUTES["/a"] = (302, {"Location": "/b"}, b"")
    ROUTES["/b"] = _html()
    got = safe_fetch(server + "/a", allowed_ports=None)
    assert got.ok and got.url.endswith("/b") and got.text() == "<html>ok</html>"


def test_redirect_to_private_ip_rejected_each_hop(server):
    """Раньше `safe_get` следовал редиректу сам — фид уводил на внутренний адрес."""
    ROUTES["/feed"] = (302, {"Location": "http://10.0.0.1/secret"}, b"")
    with pytest.raises(SsrfError):
        safe_fetch(server + "/feed", allowed_ports=None)


def test_safe_get_no_longer_follows_unvalidated_redirects(server):
    ROUTES["/feed.ics"] = (301, {"Location": "http://169.254.169.254/latest/"}, b"")
    with pytest.raises(SsrfError):
        safe_get(server + "/feed.ics")


def test_safe_get_still_returns_text_and_raises_on_error_status(server):
    ROUTES["/ok.ics"] = (200, {"Content-Type": "text/calendar"}, b"BEGIN:VCALENDAR")
    assert safe_get(server + "/ok.ics") == "BEGIN:VCALENDAR"
    with pytest.raises(requests.HTTPError):
        safe_get(server + "/missing.ics")


def test_peer_ip_mismatch_after_connect_rejected(server, monkeypatch):
    """DNS-rebinding: проверка резолвинга видела публичный адрес, а сокет подключился к
    внутреннему — транспорт обязан это поймать ПОСЛЕ коннекта."""
    monkeypatch.setattr(ssrf, "_check_peer", _real_check)
    ROUTES["/x"] = _html()
    with pytest.raises(SsrfError):
        safe_fetch(server + "/x", allowed_ports=None)


def _real_check(ip):
    if ssrf._is_blocked(ip):
        raise SsrfError("blocked")


def test_body_over_limit_aborts(server):
    ROUTES["/big"] = _html(b"x" * 5000)
    with pytest.raises(SsrfError):
        safe_fetch(server + "/big", allowed_ports=None, max_bytes=1000)


def test_body_over_limit_without_content_length_aborts(server):
    ROUTES["/chunked"] = (200, {"Content-Type": "text/html", "Content-Length": ""}, b"y" * 5000)
    with pytest.raises(SsrfError):
        safe_fetch(server + "/chunked", allowed_ports=None, max_bytes=1000)


def test_content_type_not_allowed_rejected(server):
    ROUTES["/bin"] = (200, {"Content-Type": "application/octet-stream"}, b"\x00\x01")
    with pytest.raises(SsrfError):
        safe_fetch(server + "/bin", allowed_ports=None)
    ROUTES["/img"] = (200, {"Content-Type": "image/webp"}, b"RIFF")
    assert safe_fetch(server + "/img", allowed_ports=None, accept=("image/",)).ok


def test_non_standard_port_rejected(server):
    ROUTES["/x"] = _html()
    with pytest.raises(SsrfError):
        safe_fetch(server + "/x")  # порт сервера ≠ 80/443


def test_redirect_loop_capped(server):
    ROUTES["/loop"] = (302, {"Location": "/loop"}, b"")
    with pytest.raises(SsrfError):
        safe_fetch(server + "/loop", allowed_ports=None, max_redirects=3)


def test_error_status_returned_without_body(server):
    got = safe_fetch(server + "/nope", allowed_ports=None)
    assert got.status == 404 and got.body == b"" and not got.ok


def test_environment_proxy_is_ignored(server, monkeypatch):
    """С прокси из окружения «пиром» был бы прокси, а цель — непроверенной."""
    monkeypatch.setenv("HTTP_PROXY", "http://10.0.0.9:3128")
    ROUTES["/x"] = _html()
    assert safe_fetch(server + "/x", allowed_ports=None).ok


def test_ipv4_mapped_ipv6_is_blocked():
    assert ssrf._is_blocked(ipaddress.ip_address("::ffff:10.0.0.1"))
    assert ssrf._is_blocked(ipaddress.ip_address("::ffff:127.0.0.1"))
    assert not ssrf._is_blocked(ipaddress.ip_address("::ffff:93.184.216.34"))
