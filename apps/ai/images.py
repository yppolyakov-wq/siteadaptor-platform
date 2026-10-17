"""Проверка картинок до отправки: тип по сигнатуре (не по имени/заголовку), размер, число."""

from __future__ import annotations

from .errors import AIConfigError
from .providers.base import Image

MAX_BYTES = 5 * 1024 * 1024
MAX_COUNT = 4


def sniff(data: bytes) -> str | None:
    if data[:3] == b"\xff\xd8\xff":
        return "image/jpeg"
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return "image/png"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    return None


def prepare(images) -> tuple[Image, ...]:
    images = list(images or ())
    if len(images) > MAX_COUNT:
        raise AIConfigError("too many images")
    out = []
    for data in images:
        data = bytes(data)
        if len(data) > MAX_BYTES:
            raise AIConfigError("image too large")
        mime = sniff(data)
        if mime is None:
            raise AIConfigError("unsupported image type")
        out.append(Image(mime=mime, data=data))
    return tuple(out)
