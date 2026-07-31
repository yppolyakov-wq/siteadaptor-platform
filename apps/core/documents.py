"""I18N-7b: общий слой печатных документов (PDF) — язык, шрифт, форматы.

Пять генераторов (`finance/pdf`, `jobs/pdf`, `orders/pdf`, `events/memo`,
`promotions/poster`) рисуют reportlab-канвой и раньше несли немецкие литералы,
немецкий формат чисел/дат и встроенный Helvetica. Решение владельца 2026-07-31 —
переводить документы ПОЛНОСТЬЮ, поэтому здесь собрано то, что у всех общее:

* **Язык документа** — `document_language()`: явный `?lang=` (валидируется по
  локалям тенанта), иначе активный язык поверхности (кабинет → язык кабинета,
  витрина → язык посетителя).
* **Шрифт** — встроенный Helvetica у reportlab это WinAnsi: латиница + äöüß, но
  без кириллицы И без турецких ı/ş/ğ. Для ru/uk/tr нужен TTF (DejaVu). Если его
  в системе нет, документ печатался бы рваным текстом — поэтому язык честно
  понижается до английского (`document_language`), а не «квадраты».
* **Форматы** — деньги и даты через `django.utils.formats`, т.е. по активной
  локали (в de «1.234,50», в en «1,234.50»).

DATEV-экспорт (`apps/finance/exports.py`) сюда НЕ входит и остаётся немецким:
это машинный формат для импорта в бухгалтерию, заголовки колонок фиксированы.
"""

from __future__ import annotations

import logging
import os
from decimal import Decimal

from django.conf import settings
from django.utils import formats, translation

logger = logging.getLogger(__name__)

# Языки, которым встроенного WinAnsi-шрифта НЕ хватает и нужен TTF.
# Кириллица очевидна; турецкий тоже — WinAnsi не знает ı/ş/ğ/İ, и стенд показал,
# что «Açıklama» без TTF рассыпается на куски.
NON_LATIN_LANGS = ("ru", "uk", "bg", "sr", "el", "tr")

# Кандидаты DejaVu по дистрибутивам (Debian/Ubuntu, Alpine, Arch, Fedora).
_FONT_CANDIDATES = (
    (
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    ),
    ("/usr/share/fonts/dejavu/DejaVuSans.ttf", "/usr/share/fonts/dejavu/DejaVuSans-Bold.ttf"),
    ("/usr/share/fonts/TTF/DejaVuSans.ttf", "/usr/share/fonts/TTF/DejaVuSans-Bold.ttf"),
)

REGULAR = "DocSans"
BOLD = "DocSans-Bold"

_registered: bool | None = None  # None = ещё не пробовали


def unicode_fonts_available() -> bool:
    """Зарегистрирован ли TTF с кириллицей (регистрируем один раз за процесс)."""
    global _registered
    if _registered is not None:
        return _registered
    _registered = False
    for regular, bold in _FONT_CANDIDATES:
        if not (os.path.exists(regular) and os.path.exists(bold)):
            continue
        try:
            from reportlab.pdfbase import pdfmetrics
            from reportlab.pdfbase.ttfonts import TTFont

            pdfmetrics.registerFont(TTFont(REGULAR, regular))
            pdfmetrics.registerFont(TTFont(BOLD, bold))
            pdfmetrics.registerFontFamily(REGULAR, normal=REGULAR, bold=BOLD)
            _registered = True
            break
        except Exception:  # noqa: BLE001 — битый файл шрифта не должен ронять PDF
            logger.warning("documents: не удалось зарегистрировать шрифт %s", regular)
    if not _registered:
        logger.warning(
            "documents: TTF с кириллицей не найден — документы на ru/uk выйдут по-английски"
        )
    return _registered


def fonts() -> tuple[str, str]:
    """(обычный, жирный) — юникодный DejaVu, если есть, иначе встроенный Helvetica."""
    if unicode_fonts_available():
        return REGULAR, BOLD
    return "Helvetica", "Helvetica-Bold"


def allowed_languages(tenant=None) -> list[str]:
    """Языки, на которых разрешено печатать документ: локали витрины тенанта +
    языки кабинета (владелец может печатать на своём языке) + LANGUAGE_CODE."""
    codes: list[str] = []
    for source in (
        list(getattr(tenant, "enabled_locales", None) or []),
        list(getattr(settings, "CABINET_LANGUAGES", []) or []),
        [settings.LANGUAGE_CODE],
    ):
        for code in source:
            if code and code not in codes:
                codes.append(code)
    registry = {code for code, _ in settings.LANGUAGES}
    return [c for c in codes if c in registry]


def document_language(request=None, *, explicit: str = "", tenant=None) -> str:
    """Язык документа: явный `?lang=` → активный язык поверхности → LANGUAGE_CODE.

    Понижает ru/uk до английского, если юникодного шрифта нет: пустые глифы в
    счёте хуже, чем счёт на понятном латиницей языке."""
    tenant = tenant if tenant is not None else getattr(request, "tenant", None)
    allowed = allowed_languages(tenant)
    lang = (explicit or "").strip()
    if not lang and request is not None:
        lang = (request.GET.get("lang") or "").strip()
    if lang not in allowed:
        lang = translation.get_language() or settings.LANGUAGE_CODE
    if lang not in allowed:
        lang = settings.LANGUAGE_CODE
    if lang in NON_LATIN_LANGS and not unicode_fonts_available():
        return "en" if "en" in allowed else settings.LANGUAGE_CODE
    return lang


def business_language(tenant=None) -> str:
    """Язык бизнеса — дефолт для НОВОГО документа (Tenant.default_locale)."""
    allowed = allowed_languages(tenant)
    lang = (getattr(tenant, "default_locale", "") or "").strip()
    if lang not in allowed:
        lang = settings.LANGUAGE_CODE
    return lang


def clean_language(raw, tenant=None) -> str:
    """Валидировать выбор языка документа из формы («» = не выбран)."""
    lang = (raw or "").strip()
    return lang if lang in allowed_languages(tenant) else ""


def language_choices(tenant=None) -> list[dict]:
    """[{code, label}] для селектора языка документа в кабинете."""
    names = dict(settings.LANGUAGES)
    return [{"code": c, "label": names.get(c, c.upper())} for c in allowed_languages(tenant)]


def money(value, currency: str = "EUR") -> str:
    """Сумма по активной локали + код валюты («1.234,50 EUR» / «1,234.50 EUR»)."""
    amount = Decimal(str(value or 0)).quantize(Decimal("0.01"))
    return f"{formats.number_format(amount, decimal_pos=2, use_l10n=True)} {currency}"


def qty(value) -> str:
    """Количество без хвостовых нулей, по активной локали («3,5» / «3.5», «2»)."""
    amount = Decimal(str(value or 0)).quantize(Decimal("0.01"))
    text = formats.number_format(amount, decimal_pos=2, use_l10n=True)
    if "," in text or "." in text:
        text = text.rstrip("0").rstrip(",.")
    return text


def doc_date(value) -> str:
    """Дата в формате активной локали (SHORT_DATE_FORMAT)."""
    if not value:
        return ""
    return formats.date_format(value, "SHORT_DATE_FORMAT", use_l10n=True)


def doc_datetime(value) -> str:
    """Дата+время в формате активной локали (SHORT_DATETIME_FORMAT)."""
    if not value:
        return ""
    return formats.date_format(value, "SHORT_DATETIME_FORMAT", use_l10n=True)
