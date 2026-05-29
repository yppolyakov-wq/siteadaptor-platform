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
