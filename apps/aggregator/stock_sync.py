"""T-8.26 п.3: наличие в снимке каталога города после массовых `.update()`.

Хуки агрегатора висят на `post_save`, а остаток товара и лимит акции меняются
`F()`-`.update()` (отмена заказа, освобождение опции, списание лимита) — сигнала нет,
`updated_at` не трогается, снимок застывал. Одна точка истины для остатка — леджер
`StockMovement` (каждый массовый `.update()` пишет движение в той же atomic, UD3-2), для
лимита акции — хелпер `touch_promotion` рядом с каждым `.update(available_quantity=…)`
(скан-замок `test_stock_sync`), для мест события — `post_save/post_delete Ticket`.

Окно 30 с + `countdown` на ширину окна (прецедент `resync_on_category_save`): задача
стартует, когда все правки окна закоммичены, всплеск отмен даёт ОДИН синк на объект.

Две тонкости (ревью перед мержем):
- окно считается В МОМЕНТ КОММИТА, а не правки: иначе длинная транзакция, начатая в
  конце окна и закоммиченная после старта первой задачи, теряла обновление до ночной
  сверки (её задача упиралась в тот же lock и пропускалась);
- дедуп ещё и ПРИ ПОСТАНОВКЕ (`cache.add` на ширину окна): lock `idempotent_task`
  берётся при исполнении, а брокер иначе получал бы по сообщению на каждую строку
  заказа/билет. Кэш недоступен → ставим (fail-open, как сам lock).
"""

from __future__ import annotations

import time

from django.core.cache import cache
from django.db import connection, transaction

SYNC_BUCKET = 30  # с


def _bucket() -> int:
    return int(time.time() // SYNC_BUCKET)


def _first_in_window(dedupe: str) -> bool:
    try:
        return bool(cache.add(f"enq:{dedupe}", 1, SYNC_BUCKET + 5))
    except Exception:  # noqa: BLE001 — кэш недоступен: ставим задачу, lock тоже fail-open
        return True


def _enqueue(task, prefix: str, ident, **kwargs) -> None:
    schema = (
        connection.schema_name
    )  # читаем сейчас: к моменту коммита соединение может сменить схему

    def send():
        dedupe = f"{prefix}:{schema}:{ident}:{_bucket()}"  # окно коммита
        if not _first_in_window(dedupe):
            return
        task.apply_async(
            kwargs={"dedupe_key": dedupe, "tenant_schema": schema, **kwargs},
            countdown=SYNC_BUCKET,
        )

    transaction.on_commit(send)


def touch_products(product_ids) -> None:
    """Остаток товаров изменился мимо `save()` → отложенный синк их листингов."""
    from .tasks import sync_aggregator_product

    for pid in {str(p) for p in product_ids if p}:
        _enqueue(sync_aggregator_product, "agg-stock", pid, product_id=pid)


def touch_promotion(promotion_id) -> None:
    """Лимит акции изменился `.update()` → отложенный синк её листинга («Ausverkauft»)."""
    from .tasks import sync_aggregator_listing

    if promotion_id:
        _enqueue(
            sync_aggregator_listing, "agg-promo-stock", promotion_id, promotion_id=str(promotion_id)
        )


def touch_event(event_id) -> None:
    """Места события изменились (билет) → отложенный синк листинга (группа делегируется сама)."""
    from .tasks import sync_aggregator_event

    if event_id:
        _enqueue(sync_aggregator_event, "agg-seats", event_id, event_id=str(event_id))


def resync_on_stock_movement(sender, instance, created=False, **kwargs):
    """post_save StockMovement: только новые движения; переносы между локациями
    счётчик не меняют (сумма 0) — пропускаем."""
    if not created:
        return
    if instance.kind in (sender.KIND_TRANSFER_OUT, sender.KIND_TRANSFER_IN):
        return
    touch_products([instance.product_id])


def resync_on_ticket_change(sender, instance, **kwargs):
    """post_save/post_delete Ticket: занятость мест события → снимок."""
    touch_event(instance.event_id)
