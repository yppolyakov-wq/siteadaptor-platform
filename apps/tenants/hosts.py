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
