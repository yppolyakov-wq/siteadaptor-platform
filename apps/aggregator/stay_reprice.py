"""2026-11-09: свежесть честной «ab … / Nacht» номеров в каталоге города.

Цена номера в портале (`stays.from_price`) зависит не только от самого номера: сезоны,
тарифы, цены по дням, брони и блокировки её меняют. Правка ставит пересчёт ТОЛЬКО того
номера, к которому относится (сезон/цена дня/бронь/блокировка несут `unit_id`); тариф
действует на много номеров — пересчёт всех номеров схемы. Окно 30 с считается В МОМЕНТ
КОММИТА, задача стартует с countdown на ширину окна (прецедент `resync_on_category_save`):
все правки окна уже видны, N сохранений дают один пересчёт на номер. Сохранение брони,
не меняющее даты/статус/номера (оплата, заметки, флаги напоминаний), пересчёт не ставит.
Прочее (наступление нового дня, Last-Minute) — ночная сверка `reconcile_schema`.
"""

import time

from django.db import connection, transaction

WINDOW = 30  # с
# поля брони, от которых зависят наличие и цена номера (занятость, Lücken-Deal)
BOOKING_FIELDS = frozenset(
    {"unit", "unit_id", "arrival", "departure", "status", "rooms", "extra_rooms"}
)


def _schema() -> str:
    schema = getattr(connection, "schema_name", "") or ""
    return "" if schema == "public" else schema


def schedule(schema: str | None = None, unit_id=None) -> None:
    """Пересчёт номера ``unit_id`` (или всех номеров схемы при None) после коммита."""
    schema = schema or _schema()
    if not schema:
        return
    unit = str(unit_id) if unit_id else ""
    # массовое удаление (номер, сброс демо) — не N сообщений брокеру на окно, а одно
    from django.core.cache import cache

    if not cache.add(f"agg-stay-sched:{schema}:{unit}:{int(time.time() // WINDOW)}", 1, WINDOW):
        return

    def send():
        from .tasks import reprice_stay_listings, sync_aggregator_stay

        bucket = int(time.time() // WINDOW)
        if unit:
            sync_aggregator_stay.apply_async(
                kwargs={
                    "dedupe_key": f"agg-stay-price:{schema}:{unit}:{bucket}",
                    "tenant_schema": schema,
                    "unit_id": unit,
                },
                countdown=WINDOW,
            )
        else:
            reprice_stay_listings.apply_async(
                kwargs={
                    "dedupe_key": f"agg-stay-reprice:{schema}:{bucket}",
                    "tenant_schema": schema,
                },
                countdown=WINDOW,
            )

    transaction.on_commit(send)


def on_change(sender, instance=None, update_fields=None, **kwargs) -> None:
    """post_save/post_delete сезона, тарифа, цены дня, брони или блокировки."""
    from apps.stays.models import StayBooking

    if (
        sender is StayBooking
        and update_fields is not None
        and not (set(update_fields) & BOOKING_FIELDS)
    ):
        return
    schedule(unit_id=getattr(instance, "unit_id", None))


def on_promotion_change(sender, instance=None, **kwargs) -> None:
    """Акция на номер (P6) входит в «ab» номера — пересчитать этот номер."""
    unit_id = getattr(instance, "stay_unit_id", None)
    if unit_id:
        schedule(unit_id=unit_id)
