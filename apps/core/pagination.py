"""Keyset (cursor) пагинация. Спецификация: docs/references/patterns/cursor-pagination.md.

Сортировка по (order_field, pk) — pk как tie-breaker для детерминизма.
Курсор opaque (base64). Эффективна только при индексе по ключу сортировки.
"""

import base64
import json
from dataclasses import dataclass

from django.db import models


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


def paginate(
    qs, *, order_field: str, limit: int = 20, cursor: str | None = None, descending: bool = True
) -> Page:
    """Keyset-пагинация по (order_field, pk)."""
    limit = max(1, min(limit, 100))  # защита от выгрузки всего
    sign = "-" if descending else ""
    qs = qs.order_by(f"{sign}{order_field}", f"{sign}pk")

    if cursor:
        c = _decode(cursor)
        last_val, last_pk = c["v"], c["pk"]
        lookup = "lt" if descending else "gt"
        qs = qs.filter(
            models.Q(**{f"{order_field}__{lookup}": last_val})
            | models.Q(**{order_field: last_val, f"pk__{lookup}": last_pk})
        )

    rows = list(qs[: limit + 1])  # +1 чтобы узнать has_more
    has_more = len(rows) > limit
    items = rows[:limit]

    next_cursor = None
    if has_more and items:
        last = items[-1]
        next_cursor = _encode({"v": getattr(last, order_field), "pk": last.pk})

    return Page(items=items, next_cursor=next_cursor, has_more=has_more)


@dataclass
class ListPage:
    """Постраничный срез ГОТОВОГО списка (STU-18f).

    Keyset (`paginate`) требует упорядоченный queryset, а обзор акций работает со
    списком: фасеты «−20/30/50 %+» считают процент в памяти, секции собираются
    циклом. Поэтому здесь простой offset по номеру страницы (`?seite=N`).
    """

    items: list
    page: int
    pages: int
    has_prev: bool
    has_next: bool
    total: int


def paginate_list(items, *, limit: int | None, page: int = 1) -> ListPage:
    """Срез списка. `limit=None` (владелец не задал «Pro Seite») — одна страница
    со всем содержимым: молча резать живые витрины нельзя (инвариант волны LAY)."""
    rows = list(items)
    total = len(rows)
    if not limit or limit < 1:
        return ListPage(rows, 1, 1, False, False, total)
    limit = min(int(limit), 100)  # защита от выгрузки всего (как у keyset)
    pages = max(1, -(-total // limit))
    page = max(1, min(int(page or 1), pages))
    start = (page - 1) * limit
    return ListPage(rows[start : start + limit], page, pages, page > 1, page < pages, total)
