"""Context processors порталов (P2.3a): portal_user в каждом шаблоне портала."""


def portal_user(request):
    if getattr(request, "portal", None) is None:
        return {}
    from . import auth

    return {"portal_user": auth.current_portal_user(request)}


def shortlist(request):
    """MEN-12: отложенные предложения в каждом шаблоне агрегатора.

    Кнопка «Merken» и счётчик в шапке нужны на ВСЕХ страницах выдачи (индекс,
    город, поиск, Finder) — поэтому контекст, а не по-вьюховый проброс. На
    портальных хостах под логином остаётся персональное избранное, поэтому
    флаг `shortlist_enabled` там False (кнопки не дублируются).
    """
    # Кэш публичных страниц (cache_public_page) обходит запросы с НЕПУСТОЙ
    # сессией, поэтому кэшированная выдача не может унести чужие ★ — а без
    # сессии (прогрев/тестовая фабрика) отдаём пустое состояние, не падая.
    if not (request.path or "").startswith("/entdecken"):
        return {}
    if getattr(request, "session", None) is None:
        return {"shortlist_enabled": False, "shortlist_ids": set(), "shortlist_count": 0}
    from . import shortlist as sl

    return {
        "shortlist_enabled": getattr(request, "portal", None) is None,
        "shortlist_ids": set(sl.ids(request)),
        "shortlist_count": sl.count(request),
    }
