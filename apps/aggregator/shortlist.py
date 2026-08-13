"""MEN-12 «Merkliste» агрегатора: отложенные предложения + сравнение вариантов.

Запрос владельца (2026-08-13): «для агрегатора нужно что-то наподобие избранного
отложенного или корзина, где потом можно сравнить варианты».

v1 — СЕССИЯ, по образцу `apps.orders.wishlist` (M4-C): 0 миграций, без аккаунта,
DSGVO-чисто — о неавторизованном посетителе в БД не пишем ничего. Портальное
`FavoriteListing` (под логином) остаётся и не затрагивается: там персональный
список аккаунта, здесь — анонимная «папка сравнения» на время визита.

Хранение: `session["shortlist"] = [<pk листинга>, …]`, новое первым.
"""

SHORTLIST_SESSION_KEY = "shortlist"
SHORTLIST_MAX = 12  # сравнивать больше дюжины бессмысленно (и кука не растёт)


def _raw(request) -> list[int]:
    # Сессии может не быть вовсе (кэш-прогрев, RequestFactory во вьюх-тестах) —
    # тогда список пуст, а не падение страницы выдачи.
    session = getattr(request, "session", None)
    if session is None:
        return []
    value = session.get(SHORTLIST_SESSION_KEY)
    if not isinstance(value, list):
        return []
    out: list[int] = []
    for item in value:
        try:
            out.append(int(item))
        except (TypeError, ValueError):
            continue  # мусор из чужой сессии не роняет страницу
    return out


def ids(request) -> list[int]:
    """Отложенные листинги в порядке показа (новое первым)."""
    return _raw(request)


def count(request) -> int:
    return len(_raw(request))


def has(request, pk) -> bool:
    try:
        return int(pk) in _raw(request)
    except (TypeError, ValueError):
        return False


def toggle(request, pk) -> bool:
    """Переключить листинг. Возвращает новое состояние (True = отложен)."""
    if getattr(request, "session", None) is None:
        return False
    try:
        pk = int(pk)
    except (TypeError, ValueError):
        return False
    current = _raw(request)
    if pk in current:
        current.remove(pk)
        state = False
    else:
        current.insert(0, pk)
        del current[SHORTLIST_MAX:]
        state = True
    request.session[SHORTLIST_SESSION_KEY] = current
    request.session.modified = True
    return state


def clear(request) -> None:
    if getattr(request, "session", None) is None:
        return
    request.session[SHORTLIST_SESSION_KEY] = []
    request.session.modified = True


def listings(request):
    """Активные листинги списка в порядке отложения (мёртвые pk молча выпадают —
    предложение могло закончиться, пока гость сравнивал)."""
    from .models import AggregatorListing

    order = _raw(request)
    if not order:
        return []
    found = {x.pk: x for x in AggregatorListing.objects.filter(pk__in=order, is_active=True)}
    return [found[pk] for pk in order if pk in found]


#: Строки таблицы сравнения: (ключ, подпись, как достать значение).
#: Значения — уже готовые к показу строки; пустые ячейки шаблон рисует как «—».
def compare_rows(items):
    """[(подпись, [значение по каждому листингу])] — таблица сравнения.

    Ряды с пустыми значениями у ВСЕХ вариантов выпадают: сравнивать нечего.
    """
    from django.utils.translation import gettext as _

    def price(listing):
        if listing.new_price is None:
            return ""
        unit = " / Gast" if listing.price_per_person else ""
        return f"ab {listing.new_price} {listing.currency}{unit}".replace(".", ",")

    def rating(listing):
        summary = getattr(listing, "business_rating", None)
        if not summary:
            return ""
        return f"★ {summary.avg_rating} ({summary.review_count})"

    spec = [
        (_("Anbieter"), lambda x: x.business_name),
        (_("Ort"), lambda x: x.city),
        (_("Preis"), price),
        (_("Mindestbestellung"), lambda x: f"ab {x.min_persons} Personen" if x.min_persons else ""),
        (_("Anlässe"), lambda x: ", ".join(x.event_types or [])),
        (_("Ernährung"), lambda x: ", ".join(x.diets or [])),
        (_("Bewertung"), rating),
    ]
    rows = []
    for label, getter in spec:
        values = [getter(item) or "" for item in items]
        if any(values):
            rows.append((label, values))
    return rows
