# Pattern: Cursor Pagination (keyset-пагинация)

Статус: Phase 1, Sprint 1 (utility), используется с Sprint 3 (API) и Sprint 5 (фид).
Ссылается из: `phase1-plan-additions.md` §1.2, §5.1.

## Зачем не offset/limit

`OFFSET N` заставляет БД просканировать и отбросить N строк — на больших
лентах (фид агрегатора) это деградирует линейно, плюс при вставке/удалении
между запросами строки «прыгают» (дубли/пропуски). **Keyset (cursor)**
пагинация фильтрует по значению последнего элемента — O(log n) по индексу и
стабильна при изменениях.

## Принцип

Сортируем по стабильному составному ключу — `(sort_field, pk)` (pk как
tie-breaker, чтобы порядок был детерминирован при равных `sort_field`).
Курсор кодирует значения ключа последнего элемента страницы.

```python
# apps/core/pagination.py
import base64
import json
from dataclasses import dataclass


def _encode(values: dict) -> str:
    raw = json.dumps(values, default=str, separators=(",", ":")).encode()
    return base64.urlsafe_b64encode(raw).decode()


def _decode(cursor: str) -> dict:
    return json.loads(base64.urlsafe_b64decode(cursor.encode()))


@dataclass
class Page:
    items: list
    next_cursor: str | None
    has_more: bool


def paginate(qs, *, order_field: str, limit: int = 20,
             cursor: str | None = None, descending: bool = True):
    """Keyset-пагинация по (order_field, pk). Возвращает Page.

    qs должен быть отсортирован тем же ключом, что и здесь.
    """
    limit = max(1, min(limit, 100))  # защита от выгрузки всего
    sign = "-" if descending else ""
    qs = qs.order_by(f"{sign}{order_field}", f"{sign}pk")

    if cursor:
        c = _decode(cursor)
        last_val, last_pk = c["v"], c["pk"]
        lookup = "lt" if descending else "gt"
        # (order_field, pk) < (last_val, last_pk)  — строгий keyset
        qs = qs.filter(
            models.Q(**{f"{order_field}__{lookup}": last_val})
            | models.Q(**{order_field: last_val, f"pk__{lookup}": last_pk})
        )

    rows = list(qs[: limit + 1])          # +1 чтобы узнать has_more
    has_more = len(rows) > limit
    items = rows[:limit]

    next_cursor = None
    if has_more and items:
        last = items[-1]
        next_cursor = _encode({"v": getattr(last, order_field), "pk": last.pk})

    return Page(items=items, next_cursor=next_cursor, has_more=has_more)
```

```python
from django.db import models  # вверху файла
```

## Использование

```python
# фид агрегатора, сортировка по времени старта
page = paginate(
    AggregatorListing.objects.filter(portal=portal, is_active=True),
    order_field="starts_at",
    cursor=request.GET.get("cursor"),
    limit=20,
)
return {
    "items": serialize(page.items),
    "next_cursor": page.next_cursor,  # null = конец
}
```

## Требования к индексам

Keyset эффективен только при индексе по тому же ключу. Для фида:

```python
class Meta:
    indexes = [models.Index(fields=["portal", "is_active", "-starts_at", "-id"])]
```

## Тонкости

- **Tie-breaker по pk обязателен** — без него строки с одинаковым `order_field`
  теряются/дублируются на границе страниц.
- `order_field` должен быть **immutable** в пределах сессии листания (нельзя
  пагинировать по полю, которое массово меняется, — напр. по `view_count`).
  Для фида `starts_at`/`created_at` подходят.
- Курсор **opaque** для клиента (base64) — не документируем формат, чтобы
  можно было менять.
- Назад идём тем же кодом с инверсией `descending` (или храним стек курсоров
  на клиенте).

## Чек-лист

- [ ] Сортировка по `(order_field, pk)`, pk — tie-breaker.
- [ ] Есть индекс под ключ сортировки.
- [ ] `limit` ограничен сверху (≤100).
- [ ] Курсор opaque (base64), `next_cursor = null` при конце.
