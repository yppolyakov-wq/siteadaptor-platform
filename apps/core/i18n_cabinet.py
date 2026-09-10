"""T1 (FB-12): язык КАБИНЕТА (админ-панели) — отдельно от языка витрины.

Витрина и кабинет живут на одном субдомене тенанта и делят Django-cookie языка
(её выбирает КЛИЕНТ на витрине). Поэтому язык кабинета храним отдельно — в сессии
(`cabinet_lang`), а `CabinetLocaleMiddleware` активирует его только для кабинет-путей.
Список доступных = `settings.CABINET_LANGUAGES` (курируемый, растёт по мере
готовности `.po`).

STU-16e (фидбэк владельца 2026-09-10 «язык неправильный»): при ПЕРВОМ заходе, пока
выбора в сессии нет, берём язык БРАУЗЕРА (`Accept-Language`, кламп к доступным) и
только потом падаем в `settings.LANGUAGE_CODE`. Куку языка НЕ читаем сознательно —
её ставит посетитель на витрине, и подмешивать её сюда значило бы вернуть ровно то
смешение понятий, ради которого язык кабинета и отделяли (T1-a).
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


def browser_language(request) -> str | None:
    """Лучший язык из `Accept-Language`, приведённый к доступным. None — совпадений нет.

    Свой разбор вместо `translation.get_language_from_request`: та читает ещё и куку
    языка ВИТРИНЫ, то есть язык кабинета поехал бы за выбором посетителя. Регион
    отбрасываем (`ru-RU` → `ru`); при равных базах выигрывает язык, который стоит
    раньше в реестре.
    """
    header = (getattr(request, "META", None) or {}).get("HTTP_ACCEPT_LANGUAGE") or ""
    if not header:
        return None
    avail = cabinet_language_codes()
    # reversed → при коллизии баз побеждает более ранний код реестра.
    by_base = {c.split("-")[0].lower(): c for c in reversed(avail)}
    ranked = []
    for order, chunk in enumerate(header.split(",")):
        code, _, params = chunk.strip().partition(";")
        code = code.strip().lower()
        if not code or code == "*":
            continue
        quality = 1.0
        for param in params.split(";"):
            param = param.strip()
            if param.startswith("q="):
                try:
                    quality = float(param[2:])
                except ValueError:
                    quality = 0.0
        if quality > 0:
            ranked.append((-quality, order, code))
    for _, _, code in sorted(ranked):
        hit = by_base.get(code.split("-")[0])
        if hit:
            return hit
    return None


def resolve_cabinet_locale(request) -> str:
    """Язык кабинета: сессия `cabinet_lang` → язык браузера → `settings.LANGUAGE_CODE`.

    НЕ привязываем к tenant.default_locale — то язык ВИТРИНЫ, другое понятие.
    """
    avail = set(cabinet_language_codes())
    try:
        chosen = request.session.get(SESSION_KEY)
    except Exception:  # noqa: BLE001 — нет сессии (редкие пути) → дефолт
        chosen = None
    if chosen in avail:
        return chosen
    return browser_language(request) or settings.LANGUAGE_CODE


def set_cabinet_locale(request, lang: str) -> bool:
    """Записать выбор языка кабинета в сессию (если валиден). True — записано."""
    if lang in set(cabinet_language_codes()):
        request.session[SESSION_KEY] = lang
        return True
    return False
