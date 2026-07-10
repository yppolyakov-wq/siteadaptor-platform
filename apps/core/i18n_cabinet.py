"""T1 (FB-12): язык КАБИНЕТА (админ-панели) — отдельно от языка витрины.

Витрина и кабинет живут на одном субдомене тенанта и делят Django-cookie языка
(её выбирает КЛИЕНТ на витрине). Поэтому язык кабинета храним отдельно — в сессии
(`cabinet_lang`), а `CabinetLocaleMiddleware` активирует его только для кабинет-путей.
Дефолт — `settings.LANGUAGE_CODE` (de), т.е. кабинет как раньше, пока владелец не
переключит на переведённый язык. Список доступных = `settings.CABINET_LANGUAGES`
(курируемый, растёт по мере готовности `.po`).
"""

from django.conf import settings

SESSION_KEY = "cabinet_lang"

# Кабинет-пути (владельца): и /dashboard/, и разделы, смонтированные на корне субдомена.
CABINET_PREFIXES = ("/dashboard/", "/catalog/", "/promotions/", "/imports/", "/crm/")


def cabinet_language_codes() -> list[str]:
    """Коды доступных языков кабинета (из settings.CABINET_LANGUAGES, в порядке реестра
    LANGUAGES; неизвестные/дубли отфильтрованы). de включён всегда (исходный)."""
    registry = [code for code, _ in settings.LANGUAGES]
    chosen = set(getattr(settings, "CABINET_LANGUAGES", ["de"])) | {settings.LANGUAGE_CODE}
    ordered = [c for c in registry if c in chosen]
    # LANGUAGE_CODE обязателен, даже если его нет в реестре (страховка).
    if settings.LANGUAGE_CODE not in ordered:
        ordered.insert(0, settings.LANGUAGE_CODE)
    return ordered


def cabinet_languages() -> list[dict]:
    """[{code, label}] для переключателя в шапке (лейблы из реестра LANGUAGES)."""
    names = dict(settings.LANGUAGES)
    return [{"code": c, "label": names.get(c, c.upper())} for c in cabinet_language_codes()]


def resolve_cabinet_locale(request) -> str:
    """Язык кабинета для запроса: сессия `cabinet_lang` (если доступен) → иначе de.

    НЕ привязываем к tenant.default_locale — то язык ВИТРИНЫ, другое понятие. Кабинет
    по умолчанию немецкий (как было), владелец опционально переключает на переведённый.
    """
    avail = set(cabinet_language_codes())
    try:
        chosen = request.session.get(SESSION_KEY)
    except Exception:  # noqa: BLE001 — нет сессии (редкие пути) → дефолт
        chosen = None
    if chosen in avail:
        return chosen
    return settings.LANGUAGE_CODE


def set_cabinet_locale(request, lang: str) -> bool:
    """Записать выбор языка кабинета в сессию (если валиден). True — записано."""
    if lang in set(cabinet_language_codes()):
        request.session[SESSION_KEY] = lang
        return True
    return False
