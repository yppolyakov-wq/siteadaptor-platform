"""Разбор одной HTML-страницы stdlib-парсером (без новых зависимостей).

Собирает то, что нужно импорту: JSON-LD, meta/OG, ссылки, картинки, `<html lang>`,
`tel:`-ссылки и видимый текст (без script/style/nav/header/footer — для ИИ, T-8.27e).
Ничего не исполняет и не загружает."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from html.parser import HTMLParser
from urllib.parse import urljoin

_SKIP_TEXT = {"script", "style", "noscript", "template", "nav", "header", "footer", "svg"}
_MAX_LD_SCRIPTS = 20
_MAX_LD_BYTES = 300_000
_MAX_TEXT = 60_000
# Ревью Г1: страница 2 МБ может нести 100k ссылок — память воркера ограничена.
_MAX_LINKS = 500
_MAX_IMAGES = 200
_MAX_PHONES = 20


@dataclass
class Page:
    url: str
    lang: str = ""
    title: str = ""
    jsonld: list = field(default_factory=list)
    meta: dict = field(default_factory=dict)
    links: list = field(default_factory=list)
    images: list = field(default_factory=list)
    phones: list = field(default_factory=list)
    text: str = ""


class _Parser(HTMLParser):
    def __init__(self, base_url: str):
        super().__init__(convert_charrefs=True)
        self.base = base_url
        self.page = Page(url=base_url)
        self._in_ld = False
        self._ld_buf: list[str] = []
        self._skip = 0
        self._in_title = False
        self._text: list[str] = []
        self._text_len = 0

    def handle_starttag(self, tag, attrs):
        a = {k.lower(): (v or "") for k, v in attrs}
        if tag == "html" and a.get("lang"):
            self.page.lang = a["lang"].split("-")[0].lower()[:8]
        elif tag == "base" and a.get("href"):
            self.base = urljoin(self.base, a["href"])
        elif tag == "script" and a.get("type", "").lower() == "application/ld+json":
            self._in_ld = True
            self._ld_buf = []
        elif tag == "meta":
            key = (a.get("property") or a.get("name") or a.get("itemprop") or "").lower()
            if key and a.get("content") and key not in self.page.meta:
                self.page.meta[key] = a["content"][:2000]
        elif tag == "a" and a.get("href"):
            href = a["href"].strip()
            if href.lower().startswith("tel:"):
                if len(self.page.phones) < _MAX_PHONES:
                    self.page.phones.append(href[4:].strip()[:40])
            elif len(self.page.links) < _MAX_LINKS and not href.lower().startswith(
                ("mailto:", "javascript:", "#", "data:")
            ):
                self.page.links.append(urljoin(self.base, href))
        elif tag == "img":
            src = a.get("src") or a.get("data-src") or ""
            if src and len(self.page.images) < _MAX_IMAGES and not src.lower().startswith("data:"):
                self.page.images.append(urljoin(self.base, src))
        elif tag == "title":
            self._in_title = True
        if tag in _SKIP_TEXT:
            self._skip += 1

    def handle_endtag(self, tag):
        if tag == "script" and self._in_ld:
            self._in_ld = False
            raw = "".join(self._ld_buf)
            if len(self.page.jsonld) < _MAX_LD_SCRIPTS and len(raw) <= _MAX_LD_BYTES:
                try:
                    self.page.jsonld.append(json.loads(raw))
                except ValueError:
                    pass
        elif tag == "title":
            self._in_title = False
        if tag in _SKIP_TEXT and self._skip:
            self._skip -= 1

    def handle_data(self, data):
        if self._in_ld:
            self._ld_buf.append(data)
            return
        if self._in_title:
            self.page.title = (self.page.title + data).strip()[:300]
            return
        if self._skip or self._text_len >= _MAX_TEXT:
            return
        chunk = " ".join(data.split())
        if chunk:
            self._text.append(chunk)
            self._text_len += len(chunk) + 1


def parse(html: str, url: str) -> Page:
    parser = _Parser(url)
    try:
        parser.feed(html or "")
        parser.close()
    except Exception:  # noqa: BLE001 — кривой HTML не роняет импорт: берём собранное
        pass
    page = parser.page
    page.text = " ".join(parser._text)[:_MAX_TEXT]
    page.links = list(dict.fromkeys(page.links))
    page.images = list(dict.fromkeys(page.images))
    return page
