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

import re

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


#: M21.10: признак разметки — ВСЕ теги белого списка (иначе текст только с <hr> или
#: <figcaption> считался бы плоским и показывался бы буквами). Тот же источник уходит
#: в JS редактора (``editor_rules``).
RICH_TAG_SOURCE = (
    r"</?(?:p|br|b|strong|i|em|u|ul|ol|li|a|h[234]|div|img|figure|figcaption|blockquote|hr"
    r"|s|strike|sup|sub|details|summary)"
    r"(?=[\s/>])"
)
_RICH_TAG_RE = re.compile(RICH_TAG_SOURCE, re.I)


def is_rich(text: str) -> bool:
    """Есть ли в тексте разметка нашего allowlist (для выбора режима рендера).

    Легаси-описания — плоский текст с переносами: их рендерим как раньше
    (whitespace-pre-line), иначе перенос строки потерялся бы, ведь в HTML
    он не значим. Проверка нарочно грубая — ложный False безопасен.
    """
    if not isinstance(text, str):
        return False
    # M21.8: граница тега обязательна — «<info@shop.de>» в Impressum не тег <i>.
    return bool(_RICH_TAG_RE.search(text))


# M21.6: свои страницы сайта — то же правило, что у описаний, плюс заголовки, цитата и
# картинки. ``style``/``class``/``on*`` не проходят ни у одного тега.
PAGE_ALLOWED_TAGS = ALLOWED_TAGS | {
    "h2",
    "h3",
    "h4",
    "img",
    "figure",
    "figcaption",
    "blockquote",
    "div",
    "hr",
    # M21.11 P5: зачёркнутый (Chrome пишет <strike>), верхний/нижний индекс.
    "s",
    "strike",
    "sup",
    "sub",
    # M21.11 P5: раскрывающийся блок «Frage/Antwort».
    "details",
    "summary",
}
PAGE_ALLOWED_ATTRIBUTES = {
    # M21.11 P5: класс у ссылки — только кнопка-призыв (sf-btn).
    "a": {"href", "target", "class"},
    "img": {"src", "alt", "width", "height"},
    # M21.6/M21.10: только классы раскладки из белого списка (PAGE_CLASS_SOURCE).
    "div": {"class"},
    "p": {"class"},
    "figure": {"class"},
    "h2": {"class"},
    "h3": {"class"},
    "h4": {"class"},
    "li": {"class"},
    "blockquote": {"class"},
}
#: M21.10: классы страниц — раскладка (grid/col-N), выравнивание текста, размер и
#: положение фото (носитель — ``figure``). ``style`` не проходит ни у одного тега.
PAGE_CLASS_SOURCE = (
    r"sf-(?:grid|col-(?:[1-9]|1[0-6])|center|left|right|justify"
    r"|img-(?:sm|md|lg|full)|float-(?:left|right)"
    # M21.11 P5: стиль абзаца — вводный, мелкий, плашка «Hinweis»; три колонки.
    r"|lead|small|note|grid3|btn|gallery"
    # M21.11: ширина фото перетаскиванием — шаг 5 % (10 … 100).
    r"|w-(?:[1-9][05]|100))"
)
_PAGE_CLASS_RE = re.compile(PAGE_CLASS_SOURCE)
#: Взаимоисключающие группы: в атрибуте остаётся последний класс группы.
_CLASS_GROUPS = (
    re.compile(r"sf-(?:center|left|right|justify)"),
    re.compile(r"sf-(?:img-(?:sm|md|lg|full)|w-(?:[1-9][05]|100))"),
    re.compile(r"sf-float-(?:left|right)"),
    re.compile(r"sf-(?:lead|small|note)"),
)
ALT_MAX = 300
_EMPTY_CAPTION_RE = re.compile(r"<figcaption>(?:\s|&nbsp;|<br\s*/?>)*</figcaption>")


def _clean_classes(value: str) -> str | None:
    kept: list[str] = []
    for token in value.split():
        if not _PAGE_CLASS_RE.fullmatch(token):
            continue
        for group in _CLASS_GROUPS:
            if group.fullmatch(token):
                kept = [c for c in kept if not group.fullmatch(c)]
        if token not in kept:
            kept.append(token)
    return " ".join(kept) or None


def editor_rules() -> dict:
    """M21.10: правила для JS редактора — тот же источник, что у санитайзера (замок
    паритета). Клиент — только UX; граница безопасности — сервер."""
    return {
        "rich": RICH_TAG_SOURCE,
        "tags": sorted(t.upper() for t in ALLOWED_TAGS),
        "pageTags": sorted(t.upper() for t in PAGE_ALLOWED_TAGS - ALLOWED_TAGS),
        "classTags": sorted(
            tag.upper() for tag, attrs in PAGE_ALLOWED_ATTRIBUTES.items() if "class" in attrs
        ),
        "cls": PAGE_CLASS_SOURCE,
        "altMax": ALT_MAX,
    }


def _local_image_only(tag: str, attribute: str, value: str):
    """Картинка страницы — только с нашего сервера (относительный путь или адрес
    хранилища медиа). Чужая картинка = запрос посетителя к стороннему серверу без
    согласия (DSGVO) и «битая» страница, когда тот сервер её уберёт."""
    if tag == "img" and attribute == "src":
        from django.conf import settings

        media = (getattr(settings, "MEDIA_URL", "") or "/media/").strip()
        # Ревью M21.6: «/\\host/x» браузер читает как «//host/x» (WHATWG) — поэтому не
        # «любой путь от корня», а только папка медиа, без обратных слэшей, пробелов,
        # управляющих символов и кодированных «/» или «\\».
        lowered = value.lower()
        if (
            not value.startswith(media)
            or media in ("", "/")
            or any(ch in value for ch in "\\ \t\r\n")
            or any(ord(ch) < 32 for ch in value)
            or "%2f" in lowered
            or "%5c" in lowered
            or "/../" in value
        ):
            return None
        return value
    if tag == "img" and attribute in ("width", "height"):
        return value if value.isdigit() and len(value) <= 4 else None
    if tag == "img" and attribute == "alt":
        return value[:ALT_MAX]
    if attribute == "class":
        return _clean_classes(value)
    return value


def sanitize_page(html: str) -> str:
    """HTML своей страницы сайта (`core.ContentPage`): узкий allowlist + картинки
    только с нашего сервера. Как ``sanitize`` — при сохранении и при показе."""
    if not isinstance(html, str) or not html.strip():
        return ""
    out = nh3.clean(
        html,
        tags=PAGE_ALLOWED_TAGS,
        attributes=PAGE_ALLOWED_ATTRIBUTES,
        url_schemes=ALLOWED_URL_SCHEMES,
        link_rel="noopener noreferrer",
        attribute_filter=_local_image_only,
    ).strip()
    # Пустая подпись к фото — не элемент (иначе пустой блок под картинкой).
    return _EMPTY_CAPTION_RE.sub("", out)


_BLOCK_END_RE = re.compile(r"(?i)<br\s*/?>|</(p|li|h[1-6]|div|blockquote)>")


def to_plain(text) -> str:
    """Rich-text → обычный текст для фидов, PDF, писем и JSON-LD: блоки — переносами,
    сущности раскрыты. Плоский текст («ab <50 €») не трогается."""
    import html as html_lib

    from django.utils.html import strip_tags

    raw = str(text or "")
    if is_rich(raw):
        raw = html_lib.unescape(strip_tags(_BLOCK_END_RE.sub("\n", raw)))
    lines = [" ".join(line.split()) for line in raw.replace("\r", "").split("\n")]
    return re.sub(r"\n{3,}", "\n\n", "\n".join(lines)).strip()


def clean_input(value):
    """Ввод с визуального редактора перед записью: HTML → санитайз (второй рубеж — на
    рендере); плоский текст не трогаем (переносы строк целы)."""
    return sanitize(value) if isinstance(value, str) and is_rich(value) else value


def clean_page_input(value):
    """То же для своих страниц и правовых текстов (правила ``sanitize_page``)."""
    return sanitize_page(value) if isinstance(value, str) and is_rich(value) else value
