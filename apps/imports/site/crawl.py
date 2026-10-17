"""Вежливый обход сайта клиента (T-8.27b): тот же сайт, robots.txt, sitemap, ≤N страниц.

Весь сетевой доступ — через `core.ssrf.safe_fetch` (проверка каждого хопа и пира);
транспорт инжектируется, тесты гоняют обход без сети. Тела страниц дальше не
хранятся: вызывающий берёт разобранное (`htmlparse.Page`)."""

from __future__ import annotations

import time
import xml.etree.ElementTree as ET
from collections import deque
from dataclasses import dataclass, field
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit
from urllib.robotparser import RobotFileParser

import requests
from django.conf import settings

from apps.core.ssrf import SsrfError, safe_fetch

from . import htmlparse

HTML_TYPES = ("text/html", "application/xhtml+xml")
_TRACKING_PREFIXES = ("utm_", "mc_")
_TRACKING_KEYS = {"fbclid", "gclid", "_ga", "ref"}
_SKIP_EXT = (
    ".pdf", ".jpg", ".jpeg", ".png", ".gif", ".webp", ".svg", ".zip", ".mp4", ".mp3",
    ".css", ".js", ".ico", ".xml", ".doc", ".docx", ".xls", ".xlsx",
)  # fmt: skip
# Признаки страниц с позициями: обходятся первыми.
HINTS = (
    "/product", "/produkt", "/shop", "/p/", "/artikel", "/leistung", "/speisekarte",
    "/menu", "/preise", "/angebot", "/sortiment", "/collections", "/kategorie",
)  # fmt: skip
SITEMAP_MAX_BYTES = 1024 * 1024
SITEMAP_MAX_LOCS = 5000
ROBOTS_MAX_BYTES = 200 * 1024
SEEN_MAX = 5000  # общий кап известных адресов (память воркера)
CRAWL_DELAY_MAX = 5.0  # Crawl-delay уважаем, но не дольше — иначе бюджет съедят паузы


@dataclass
class CrawlResult:
    pages: list = field(default_factory=list)
    log: list = field(default_factory=list)
    robots_blocked: bool = False
    error: str = ""
    # Обход неполный (бюджет, ошибки страниц, robots): «пропавшее» не значит «удалено».
    partial: bool = False


def _site(host: str) -> str:
    host = (host or "").lower().rstrip(".")
    return host[4:] if host.startswith("www.") else host


def normalize(url: str) -> str | None:
    """Канонический вид для дедупа: http(s), хост в нижнем регистре, без фрагмента и
    трекинговых параметров. None — не наш тип ссылки."""
    try:
        parts = urlsplit((url or "").strip())
    except ValueError:
        return None
    if parts.scheme not in ("http", "https") or not parts.hostname:
        return None
    try:
        port = parts.port
    except ValueError:  # http://site:99999/ — битая ссылка не роняет обход
        return None
    query = urlencode(
        [
            (k, v)
            for k, v in parse_qsl(parts.query)
            if not k.lower().startswith(_TRACKING_PREFIXES) and k.lower() not in _TRACKING_KEYS
        ]
    )
    hostname = parts.hostname.lower()
    if ":" in hostname:  # IPv6-литерал: скобки обратно, иначе адрес не разобрать
        hostname = f"[{hostname}]"
    netloc = hostname + (f":{port}" if port else "")
    return urlunsplit((parts.scheme, netloc, parts.path or "/", query, ""))


def same_site(url: str, host: str) -> bool:
    try:
        return _site(urlsplit(url).hostname or "") == _site(host)
    except ValueError:
        return False


def _hinted(url: str) -> bool:
    path = urlsplit(url).path.lower()
    return any(h in path for h in HINTS)


def parse_sitemap(text: str) -> tuple[list, list]:
    """Вернуть (страницы, вложенные sitemap). DOCTYPE/ENTITY — отказ (billion laughs)."""
    head = text[:4096].lower()
    if "<!doctype" in head or "<!entity" in text.lower():
        raise ValueError("sitemap with DTD rejected")
    root = ET.fromstring(text)
    locs = [
        (el.text or "").strip()
        for el in root.iter()
        if el.tag.endswith("loc") and (el.text or "").strip()
    ][:SITEMAP_MAX_LOCS]
    if root.tag.endswith("sitemapindex"):
        return [], locs
    return locs, []


class Crawler:
    def __init__(self, start_url: str, *, fetch=None, clock=time.monotonic, sleep=time.sleep):
        self.start = normalize(start_url)
        self.fetch = fetch or safe_fetch
        self.clock = clock
        self.sleep = sleep
        self.ua = settings.SITE_IMPORT_USER_AGENT
        self.max_pages = settings.SITE_IMPORT_MAX_PAGES
        self.max_bytes = settings.SITE_IMPORT_MAX_PAGE_BYTES
        self.budget = settings.SITE_IMPORT_TIME_BUDGET_S
        self.pause = settings.SITE_IMPORT_PAUSE_S
        self.result = CrawlResult()
        self.robots = None
        self.deadline = None

    def _get(self, url, *, accept, max_bytes):
        if self.deadline is not None and self.clock() >= self.deadline:
            raise SsrfError("time budget")
        return self.fetch(
            url,
            accept=accept,
            max_bytes=max_bytes,
            headers={"User-Agent": self.ua},
            deadline=self.deadline,
        )

    def _note(self, url, status, **extra):
        self.result.log.append({"url": url[:500], "status": status, **extra})

    def _load_robots(self, host_root: str):
        """RFC 9309: 4xx (кроме 401/403) — правил нет; 401/403/5xx/сеть — не обходим.
        Возвращает (robots|None, blocked)."""
        robots = RobotFileParser()
        try:
            got = self._get(host_root + "/robots.txt", accept=None, max_bytes=ROBOTS_MAX_BYTES)
        except SsrfError:
            return None, False  # сам корень проверит политику; robots не дошёл — правил нет
        except requests.RequestException:
            return None, True
        if got.status in (401, 403) or got.status >= 500:
            return None, True
        if not got.ok:
            return None, False  # нет robots.txt — правил нет
        robots.parse(got.text().splitlines())
        return robots, False

    def _allowed(self, url: str) -> bool:
        return self.robots is None or self.robots.can_fetch(self.ua, url)

    def _pause(self) -> float:
        delay = None
        if self.robots is not None:
            try:
                delay = self.robots.crawl_delay(self.ua)
            except (TypeError, ValueError):
                delay = None
        return min(max(float(delay or 0), self.pause or 0), CRAWL_DELAY_MAX)

    def _sitemap_urls(self, host_root: str, host: str) -> list:
        sources = list(self.robots.site_maps() or []) if self.robots else []
        sources = [s for s in sources if same_site(s, host)][:3] or [host_root + "/sitemap.xml"]
        urls, nested = [], []
        for src in sources:
            pages, children = self._read_sitemap(src)
            urls += pages
            nested += children
        for child in [c for c in nested if same_site(c, host)][:3]:  # один уровень индекса
            urls += self._read_sitemap(child)[0]
        return urls

    def _read_sitemap(self, url: str):
        try:
            got = self._get(url, accept=None, max_bytes=SITEMAP_MAX_BYTES)
            if not got.ok:
                return [], []
            return parse_sitemap(got.text())
        except (SsrfError, requests.RequestException, ValueError, ET.ParseError):
            return [], []

    def run(self) -> CrawlResult:
        if not self.start:
            self.result.error = "invalid_url"
            return self.result
        started = self.clock()
        self.deadline = started + self.budget  # один срок на robots, sitemap и страницы
        host = urlsplit(self.start).hostname
        root = f"{urlsplit(self.start).scheme}://{urlsplit(self.start).netloc}"
        self.robots, blocked = self._load_robots(root)
        if blocked or not self._allowed(self.start):
            self.result.robots_blocked = True
            return self.result
        hinted, other = deque(), deque()
        seen = {self.start}

        def enqueue(raw):
            if len(seen) >= SEEN_MAX:
                return
            url = normalize(raw)
            if not url or url in seen or not same_site(url, host):
                return
            if urlsplit(url).path.lower().endswith(_SKIP_EXT):
                return
            seen.add(url)
            (hinted if _hinted(url) else other).append(url)

        queue_first = deque([self.start])
        for url in self._sitemap_urls(root, host):
            enqueue(url)
        while (queue_first or hinted or other) and len(self.result.pages) < self.max_pages:
            if self.clock() >= self.deadline:
                self._note("", "time_budget")
                self.result.partial = True
                break
            url = (queue_first or hinted or other).popleft()
            if not self._allowed(url):
                self._note(url, "robots")
                continue
            try:
                got = self._get(url, accept=HTML_TYPES, max_bytes=self.max_bytes)
            except SsrfError:
                self._note(url, "blocked")
                self.result.partial = True
                continue
            except requests.RequestException as exc:
                self._note(url, "error", error=type(exc).__name__)
                self.result.partial = True
                continue
            if not got.ok:
                self._note(url, got.status)
                if got.status >= 500 or got.status == 429:
                    self.result.partial = True
                continue
            if not same_site(got.url, host):
                self._note(url, "offsite")
                continue
            if got.url != url and not self._allowed(got.url):  # цель редиректа — тоже robots
                self._note(got.url, "robots")
                continue
            page = htmlparse.parse(got.text(), got.url)
            self.result.pages.append(page)
            self._note(got.url, got.status, bytes=len(got.body), ld=bool(page.jsonld))
            for link in page.links:
                enqueue(link)
            if (queue_first or hinted or other) and len(self.result.pages) >= self.max_pages:
                self.result.partial = True  # потолок страниц: остальное не смотрели
            pause = self._pause()
            if pause:
                self.sleep(pause)
        return self.result


def crawl(start_url: str, **kwargs) -> CrawlResult:
    return Crawler(start_url, **kwargs).run()
