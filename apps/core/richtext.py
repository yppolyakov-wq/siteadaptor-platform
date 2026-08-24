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
ALLOWED_ATTRIBUTES = {"a": {"href", "rel", "target"}}
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
