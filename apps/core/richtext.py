"""SR-3: ограниченный rich-text для описаний (визуальный редактор кабинета).

Владелец подтвердил (2026-08-24): форматирование описания (жирный/списки)
сохраняется и отображается на витрине. До этой волны описание было плоским
текстом (autoescape + whitespace-pre-line), санитайзера в проекте не было.

Правила слоя:
- `sanitize()` зовётся ДВАЖДЫ — при сохранении формы и при рендере (фильтр
  `rich_text`): рендер fail-closed к легаси-данным и любым обходным записям.
- Allowlist сознательно узкий — ровно то, что умеет тулбар редактора.
  Расширение (таблицы, заголовки) — отдельным решением.
- Плоский текст остаётся валидным входом: без тегов sanitize() его не меняет
  (экранирование спецсимволов делает nh3), переносы строк доносит фильтр.
"""

from __future__ import annotations

import nh3

# Ровно набор тулбара: жирный/курсив/подчёркивание, списки, ссылка, абзацы.
ALLOWED_TAGS = {"p", "br", "b", "strong", "i", "em", "u", "ul", "ol", "li", "a"}
# «rel» задаёт сам nh3 (link_rel) — в allowlist его быть не должно (ValueError).
ALLOWED_ATTRIBUTES = {"a": {"href", "target"}}
# nh3 сам ограничивает схемы ссылок (относительные же нам не нужны — наружу).
ALLOWED_URL_SCHEMES = {"http", "https", "mailto", "tel"}


def sanitize(html: str) -> str:
    """Чистит HTML до allowlist; не-строки и пустое → ""."""
    if not isinstance(html, str) or not html.strip():
        return ""
    return nh3.clean(
        html,
        tags=ALLOWED_TAGS,
        attributes=ALLOWED_ATTRIBUTES,
        url_schemes=ALLOWED_URL_SCHEMES,
        link_rel="noopener noreferrer",
    ).strip()


def is_rich(text: str) -> bool:
    """Есть ли в тексте разметка нашего allowlist (для выбора режима рендера).

    Легаси-описания — плоский текст с переносами: их рендерим как раньше
    (whitespace-pre-line), иначе перенос строки потерялся бы, ведь в HTML
    он не значим. Проверка нарочно грубая — ложный False безопасен.
    """
    if not isinstance(text, str):
        return False
    lowered = text.lower()
    return any(f"<{t}" in lowered for t in ALLOWED_TAGS)


# M21.6: свои страницы сайта — то же правило, что у описаний, плюс заголовки, цитата и
# картинки. ``style``/``class``/``on*`` не проходят ни у одного тега.
PAGE_ALLOWED_TAGS = ALLOWED_TAGS | {"h2", "h3", "h4", "img", "figure", "blockquote"}
PAGE_ALLOWED_ATTRIBUTES = {
    "a": {"href", "target"},
    "img": {"src", "alt", "width", "height"},
}


def _local_image_only(tag: str, attribute: str, value: str):
    """Картинка страницы — только с нашего сервера (относительный путь или адрес
    хранилища медиа). Чужая картинка = запрос посетителя к стороннему серверу без
    согласия (DSGVO) и «битая» страница, когда тот сервер её уберёт."""
    if tag == "img" and attribute == "src":
        from django.conf import settings

        media = (getattr(settings, "MEDIA_URL", "") or "").strip()
        allowed = value.startswith("/") and not value.startswith("//")
        if media.startswith(("http://", "https://")) and value.startswith(media):
            allowed = True
        return value if allowed else None
    if tag == "img" and attribute in ("width", "height"):
        return value if value.isdigit() and len(value) <= 4 else None
    return value


def sanitize_page(html: str) -> str:
    """HTML своей страницы сайта (`core.ContentPage`): узкий allowlist + картинки
    только с нашего сервера. Как ``sanitize`` — при сохранении и при показе."""
    if not isinstance(html, str) or not html.strip():
        return ""
    return nh3.clean(
        html,
        tags=PAGE_ALLOWED_TAGS,
        attributes=PAGE_ALLOWED_ATTRIBUTES,
        url_schemes=ALLOWED_URL_SCHEMES,
        link_rel="noopener noreferrer",
        attribute_filter=_local_image_only,
    ).strip()
