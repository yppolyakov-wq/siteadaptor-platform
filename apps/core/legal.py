"""L5/E-2: резолвер правовых текстов витрины.

Цепочка (план legal-lang-package-plan §3): LegalDoc[текущая локаль] →
LegalDoc[default_locale тенанта] → плоское Tenant-поле → существующий
генерённый фолбэк (`impressum_text()` и т.п. уже делают «поле или генерация»).
AGB фолбэка не имеет — пусто означает «страницы нет».
"""

from django.utils import translation

# kind → метод Tenant «плоское поле ИЛИ генерённый текст».
_TENANT_FALLBACKS = {
    "impressum": "impressum_text",
    "datenschutz": "privacy_text",
    "widerruf": "withdrawal_text",
}


def _locale_chain(tenant, locale=None) -> list[str]:
    """[текущая, дефолт тенанта] — короткие коды, без дублей/пустых."""
    current = (locale or translation.get_language() or "").split("-")[0]
    default = (getattr(tenant, "default_locale", "") or "de").split("-")[0]
    chain = []
    for loc in (current, default):
        if loc and loc not in chain:
            chain.append(loc)
    return chain


def legal_text(tenant, kind: str, locale: str | None = None) -> str:
    """Правовой текст для страницы витрины (см. цепочку в докстринге модуля)."""
    from apps.core.models import LegalDoc

    chain = _locale_chain(tenant, locale)
    try:
        docs = {d.locale: d.text for d in LegalDoc.objects.filter(kind=kind, locale__in=chain)}
    except Exception:  # таблица ещё не накатана (деплой-гонка) — фолбэк, не 500
        docs = {}
    for loc in chain:
        text = docs.get(loc) or ""
        if text.strip():
            return text
    method = _TENANT_FALLBACKS.get(kind)
    return getattr(tenant, method)() if method else ""


#: M21.10: потолок текста правовой страницы (DoS через гигантский POST/nh3).
LEGAL_TEXT_MAX = 200_000


def legal_kinds() -> tuple:
    from apps.core.models import LegalDoc

    return tuple(k for k, _label in LegalDoc.KIND_CHOICES)


def save_legal_doc(kind: str, locale: str, text: str) -> str:
    """M21.10: ЕДИНСТВЕННЫЙ писатель правового текста (LegalDoc) из кабинета.

    HTML — через ``sanitize_page``; пусто — строка удаляется (витрина берёт
    автотекст, у AGB страницы нет). Возвращает ``saved`` | ``deleted``.
    ``kind``/``locale`` — только из белых списков (иначе ValueError)."""
    from django.conf import settings

    from apps.core.models import LegalDoc
    from apps.core.richtext import clean_page_input

    if kind not in legal_kinds() or locale not in dict(settings.LANGUAGES):
        raise ValueError("unknown legal kind/locale")
    value = (text or "")[:LEGAL_TEXT_MAX]
    if not value.strip():
        LegalDoc.objects.filter(kind=kind, locale=locale).delete()
        return "deleted"
    LegalDoc.objects.update_or_create(
        kind=kind, locale=locale, defaults={"text": clean_page_input(value)}
    )
    return "saved"
