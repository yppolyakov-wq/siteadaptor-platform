"""Кнопка «поделиться» с выбором канала (фидбэк владельца 2026-08-25).

«Нужна кнопка поделиться и выбрать канал где» — здесь строятся прямые
share-ссылки популярных каналов. Это ЛИЧНОЕ/ручное распространение (владелец
сам выбирает, куда отправить), в отличие от авто-публикации акций по включённым
каналам (`apps.publishing`) — она остаётся отдельной кнопкой «во все каналы».
"""

from __future__ import annotations

from urllib.parse import quote

from django.utils.translation import gettext_lazy as _

# (ключ, подпись, иконка, шаблон URL). {text} и {url} подставляются закодированными.
TARGETS = (
    ("whatsapp", _("WhatsApp"), "🟢", "https://wa.me/?text={text}%20{url}"),
    ("telegram", _("Telegram"), "✈️", "https://t.me/share/url?url={url}&text={text}"),
    ("facebook", _("Facebook"), "📘", "https://www.facebook.com/sharer/sharer.php?u={url}"),
    ("email", _("E-Mail"), "✉️", "mailto:?subject={text}&body={url}"),
)


def share_targets(text: str, url: str) -> list[dict]:
    """Список каналов для меню «Teilen» (подпись, иконка, готовая ссылка)."""
    text_q, url_q = quote(text or "", safe=""), quote(url or "", safe="")
    return [
        {
            "key": key,
            "label": label,
            "icon": icon,
            "url": tpl.format(text=text_q, url=url_q),
        }
        for key, label, icon, tpl in TARGETS
    ]
