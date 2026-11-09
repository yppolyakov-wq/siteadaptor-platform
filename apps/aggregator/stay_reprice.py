"""2026-11-09: свежесть честной «ab … / Nacht» номеров в каталоге города.

Цена номера в портале (`stays.from_price`) зависит не только от самого номера: сезоны,
тарифы, цены по дням, брони и блокировки её меняют. Любая такая правка ставит ОДНУ
пересинхронизацию номеров схемы на окно 30 с (прецедент `resync_on_category_save`):
окно считается В МОМЕНТ КОММИТА, задача стартует с countdown на ширину окна — все
правки окна уже видны, N сохранений (массовая правка цен, импорт броней) дают один
проход. Прочее (наступление нового дня, Last-Minute) — ночная сверка `reconcile_schema`.
"""

import time

from django.db import connection, transaction

WINDOW = 30  # с


def schedule(schema: str | None = None) -> None:
    schema = schema or getattr(connection, "schema_name", "") or ""
    if not schema or schema == "public":
        return

    def send():
        from .tasks import reprice_stay_listings

        bucket = int(time.time() // WINDOW)
        reprice_stay_listings.apply_async(
            kwargs={"dedupe_key": f"agg-stay-reprice:{schema}:{bucket}", "tenant_schema": schema},
            countdown=WINDOW,
        )

    transaction.on_commit(send)


def on_change(sender, instance=None, **kwargs) -> None:
    """post_save/post_delete сезона, тарифа, цены дня, брони или блокировки."""
    schedule()
