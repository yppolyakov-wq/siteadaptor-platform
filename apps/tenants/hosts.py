"""Динамическое доверие хостам кастомных доменов (автоподключение домена).

`ALLOWED_HOSTS` статичен, а кастомные домены владельцы добавляют в кабинете в
любой момент — перечислить их в env нельзя. Поэтому хосты из таблицы `Domain`
(поддомены бизнесов + подтверждённые кастомные домены) трастятся динамически:
middleware (`CustomDomainHostMiddleware`) дописывает известный хост в
`settings.ALLOWED_HOSTS` на лету, ещё до `TenantMainMiddleware`. Множество хостов
кэшируется в Redis (TTL + явный сброс сигналом при изменении `Domain`, см.
`apps.py::ready`). Неизвестный хост остаётся запрещённым — django-tenants отдаёт
404, как и раньше. Так подключение домена становится автоматическим: добавил в
кабинете → подтвердилось (создалась строка `Domain`) → хост сразу обслуживается,
без ручной правки `.env.prod`.
"""

from django.core.cache import cache

_CACHE_KEY = "tenants:known_hosts"
_CACHE_TTL = 300  # сек; плюс явный сброс сигналом при save/delete Domain


def known_hosts() -> set:
    """Множество хостов всех `Domain` (lower-case). Кэш в Redis (TTL + сигнал).

    Fail-open: недоступная БД/кэш → пустое множество (статический ALLOWED_HOSTS
    продолжает работать, кастомные домены просто не трастятся до восстановления).
    """
    hosts = cache.get(_CACHE_KEY)
    if hosts is None:
        from .models import Domain

        try:
            hosts = {h.lower() for h in Domain.objects.values_list("domain", flat=True)}
        except Exception:  # noqa: BLE001 — БД недоступна на раннем этапе/в тестах
            return set()
        try:
            cache.set(_CACHE_KEY, hosts, _CACHE_TTL)
        except Exception:  # noqa: BLE001 — кэш недоступен: просто не кэшируем
            pass
    return hosts


def clear_known_hosts(**_kwargs) -> None:
    """Сигнал-обработчик: сбросить кэш известных хостов (при изменении Domain)."""
    try:
        cache.delete(_CACHE_KEY)
    except Exception:  # noqa: BLE001
        pass


def _custom_key(tenant_id) -> str:
    return f"tenants:primary_custom:{tenant_id}"


def primary_custom_domain(tenant) -> str:
    """T-8.25: свой домен бизнеса — самый ранний АКТИВНЫЙ (A-запись подтверждена); иначе "".

    Кэш на тенанта (витрина спрашивает на каждом запросе); сброс — сигналом `Domain`
    (подтверждение/удаление своего домена создаёт/удаляет строку Domain).
    """
    if tenant is None or not getattr(tenant, "pk", None):
        return ""
    key = _custom_key(tenant.pk)
    try:
        cached = cache.get(key)
    except Exception:  # noqa: BLE001
        cached = None
    if cached is not None:
        return cached
    try:
        from .models import CustomDomain

        row = (
            CustomDomain.objects.filter(tenant=tenant, status=CustomDomain.ACTIVE)
            .order_by("verified_at", "created_at")
            .values_list("domain", flat=True)
            .first()
        )
    except Exception:  # noqa: BLE001 — нет таблицы/БД: основной адрес = поддомен
        return ""
    value = row or ""
    try:
        cache.set(key, value, _CACHE_TTL)
    except Exception:  # noqa: BLE001
        pass
    return value


def clear_primary_custom(sender=None, instance=None, **_kwargs) -> None:
    """Сигнал-обработчик: сменился Domain → основной адрес тенанта пересчитать."""
    tenant_id = getattr(instance, "tenant_id", None)
    if tenant_id:
        try:
            cache.delete(_custom_key(tenant_id))
        except Exception:  # noqa: BLE001
            pass


def public_base_url(tenant) -> str:
    """T-8.25: ОСНОВНОЙ адрес витрины без «/» в конце — свой домен, иначе поддомен.

    Сюда ведут ссылки наружу: каталог города, QR, флаеры, «Teilen», canonical витрины.
    Кабинет и вход остаются на поддомене (`services.site_url_for`): сессия привязана к хосту.
    """
    from django.conf import settings

    scheme = "http" if getattr(settings, "DEBUG", False) else "https"
    custom = primary_custom_domain(tenant)
    if custom:
        return f"{scheme}://{custom}"
    base = getattr(settings, "TENANT_DOMAIN_BASE", "siteadaptor.de")
    return f"{scheme}://{tenant.slug}.{base}"
