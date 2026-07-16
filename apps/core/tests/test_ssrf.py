"""Egress-фильтр для owner-URL (HIGH-2): validate_public_url."""

import socket

import pytest

from apps.core.ssrf import SsrfError, validate_public_url


def test_blocks_loopback_link_local_private():
    for url in (
        "http://127.0.0.1/",
        "http://169.254.169.254/latest/meta-data/",  # облачные метаданные
        "http://10.0.0.1/",
        "http://192.168.1.1/",
        "http://[::1]/",
        "http://0.0.0.0/",
    ):
        with pytest.raises(SsrfError):
            validate_public_url(url)


def test_blocks_non_http_scheme():
    for url in ("file:///etc/passwd", "ftp://host/x", "gopher://host/"):
        with pytest.raises(SsrfError):
            validate_public_url(url)


def test_allows_public_host(monkeypatch):
    monkeypatch.setattr(
        socket,
        "getaddrinfo",
        lambda *a, **k: [(socket.AF_INET, socket.SOCK_STREAM, 0, "", ("93.184.216.34", 80))],
    )
    url = "https://calendar.example.com/feed.ics"
    assert validate_public_url(url) == url


def test_blocks_public_host_resolving_to_private(monkeypatch):
    # DNS, указывающий на внутренний адрес, тоже отклоняется (не только литеральные IP).
    monkeypatch.setattr(
        socket,
        "getaddrinfo",
        lambda *a, **k: [(socket.AF_INET, socket.SOCK_STREAM, 0, "", ("10.1.2.3", 80))],
    )
    with pytest.raises(SsrfError):
        validate_public_url("http://internal.evil.example/")
