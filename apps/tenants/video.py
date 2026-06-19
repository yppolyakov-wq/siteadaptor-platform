"""Разбор video-URL для галереи витрины (T1).

GDPR-дружелюбно: YouTube → youtube-nocookie embed (грузится только по клику,
2-Klick-Lösung на витрине); прямой файл (.mp4/.webm/.ogg) → <video>; иначе —
просто ссылка. Никаких трекеров на витрине до явного действия пользователя.
"""

import re

_YT = re.compile(r"(?:youtube\.com/(?:watch\?v=|embed/|shorts/)|youtu\.be/)([\w-]{11})")
_VIMEO = re.compile(r"vimeo\.com/(?:video/)?(\d+)")
_FILE_EXT = (".mp4", ".webm", ".ogg")


def embed_info(url: str | None) -> dict | None:
    """Вернуть {"kind", "src"} для секции галереи или None, если URL пуст.

    kind: ``youtube`` (nocookie-embed по клику), ``vimeo`` (player по клику),
    ``file`` (прямое видео в <video>), ``link`` (внешняя ссылка-фолбэк).
    """
    url = (url or "").strip()
    if not url:
        return None
    m = _YT.search(url)
    if m:
        return {"kind": "youtube", "src": f"https://www.youtube-nocookie.com/embed/{m.group(1)}"}
    m = _VIMEO.search(url)
    if m:
        return {"kind": "vimeo", "src": f"https://player.vimeo.com/video/{m.group(1)}"}
    if url.lower().split("?")[0].endswith(_FILE_EXT):
        return {"kind": "file", "src": url}
    return {"kind": "link", "src": url}
