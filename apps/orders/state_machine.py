"""FSM заказа Click & Collect / доставка (Track D / D2, G4). База — apps.core.fsm.

new → confirmed → ready → picked_up (самовывоз) | shipped (доставка); отмена — из
любого незавершённого статуса. Каждый переход шлёт письмо клиенту (notifications
dedupe); picked_up/shipped пишут выручку (finance).
"""

from apps.core.fsm import PaymentRequired, StateMachine, Transition


class OrderSM(StateMachine):
    kind = "order"
    transitions = [
        Transition("new", "confirmed", "order.confirmed"),
        Transition("new", "cancelled", "order.cancelled"),
        Transition("confirmed", "ready", "order.ready"),
        Transition("confirmed", "cancelled", "order.cancelled"),
        Transition("ready", "picked_up", "order.picked_up"),
        Transition("ready", "shipped", "order.shipped"),  # G4: доставка → versandt
        Transition("ready", "cancelled", "order.cancelled"),
        # A2c: возврат уже выданного/отправленного заказа (Widerruf).
        Transition("picked_up", "returned", "order.returned"),
        Transition("shipped", "returned", "order.returned"),
    ]

    def guard(self, instance, src, dst):
        # KA-12 E2.6: онлайн-/Vorkasse-заказ выдаётся только после оплаты —
        # и во встроенные статусы выдачи, и в свои статусы с ролью «done».
        from apps.core import money_contract, status_registry

        delivering = dst in money_contract.DELIVERED["order"]
        if not delivering:
            desc = status_registry.resolve("order", dst)
            delivering = desc is not None and not desc.builtin and desc.role == "done"
        if delivering and money_contract.delivery_blocked_unpaid("order", instance):
            raise PaymentRequired(type(instance).__name__, src, dst)

    def on_transition(self, instance, t, **kw):
        # W7c (аудит 2026-08-05): момент отправки фиксируем в FSM — доска зовёт
        # apply() напрямую, минуя вьюху карточки заказа (единственное место, где
        # ставился shipped_at), и заказ уходил «отправленным» с shipped_at=NULL.
        # Вьюха ставит его ДО apply (вместе с трек-номером) — тогда тут no-op.
        if t.dst == "shipped" and getattr(instance, "shipped_at", None) is None:
            from django.utils import timezone

            instance.shipped_at = timezone.now()
            instance.save(update_fields=["shipped_at"])

        from .notifications import enqueue_order_email

        enqueue_order_email(instance, t.dst)

        # Отмена/возврат → возврат остатка на склад (R3). Терминальные →
        # срабатывают один раз. Только по позициям с учётом (stock_quantity не null).
        if t.dst in ("cancelled", "returned"):
            _restore_stock(instance)

        # B1.4: отмена → вернуть использование промокода/Gutschein (однократно —
        # FSM не даёт второй переход в cancelled).
        # KA-12 B2-7a: и возврат заказа (`returned`) — сертификат клиента не сгорает.
        if t.dst in ("cancelled", "returned") and getattr(instance, "voucher_code", ""):
            from apps.promotions.services import unredeem_voucher, voucher_return_cents

            # B1.5: balance-сертификату возвращается и списанная сумма (снимок).
            unredeem_voucher(instance.voucher_code, amount_cents=voucher_return_cents(instance))

        # Выдан/отправлен → запись в журнал выручки (D4a, идемпотентно по
        # source_ref). Доставка включена в total → попадает в выручку.
        if t.dst in ("picked_up", "shipped"):
            # KA-MC X1: оплата на месте получена при исполнении (решение владельца).
            from apps.core.money_contract import settle_on_delivery

            settle_on_delivery("order", instance)

            from apps.finance.services import record_revenue

            record_revenue(
                source="order",
                source_ref=str(instance.id),
                amount=instance.total,
                currency=instance.currency,
                customer=instance.customer,
                note=instance.reference_code,
            )

        # Возврат → сторно выручки (отрицательная запись, идемпотентно).
        if t.dst == "returned":
            from apps.finance.services import record_reversal

            record_reversal(
                source="order",
                source_ref=f"{instance.id}:return",
                amount=instance.total,
                currency=instance.currency,
                customer=instance.customer,
                note=f"Storno {instance.reference_code}",
            )


class OfferSM(StateMachine):
    """LS-3: FSM предложения (Sofort-Angebot). open → accepted/declined/cancelled.

    Без kind (кастом-статусы FB-3 scoped на order/booking/stay — предложение не
    карточка канбана). Письма владельцу на accepted/declined — как у jobs; письмо
    клиенту «sent» — не переход (offer рождается open), шлёт offers.send_offer.
    """

    transitions = [
        Transition("open", "accepted", "offer.accepted"),
        Transition("open", "declined", "offer.declined"),
        Transition("open", "cancelled", "offer.cancelled"),
    ]

    def on_transition(self, instance, t, **kw):
        if t.dst in ("accepted", "declined"):
            from .offers import enqueue_offer_email

            enqueue_offer_email(instance, t.dst)


def _restore_stock(instance):
    """Вернуть остаток по позициям заказа (R3); учитываются только товары/варианты
    со складским учётом (stock_quantity не null).

    U-D3: возврат логируется в склад-леджер (kind=return, delta=+qty) в той же
    atomic, что и F()-инкремент; только когда реально вернули (rowcount>0)."""
    from django.db import transaction
    from django.db.models import F

    from apps.catalog.models import Product, ProductVariant
    from apps.inventory.services import record_movement

    with transaction.atomic():
        for item in instance.items.all():
            # KA-12 WR-8: штуки, уже прошедшие поштучный возврат (`returned_qty`), второй
            # раз на склад не идут — ни годные (уже вернули), ни повреждённые (не возвращаем).
            qty = item.qty - (item.returned_qty or 0)
            if qty <= 0:
                continue
            if item.variant_id:
                n = ProductVariant.objects.filter(
                    pk=item.variant_id, stock_quantity__isnull=False
                ).update(stock_quantity=F("stock_quantity") + qty)
            else:
                n = Product.objects.filter(pk=item.product_id, stock_quantity__isnull=False).update(
                    stock_quantity=F("stock_quantity") + qty
                )
            if n:  # реально вернули (учитываемый остаток) → запись в леджер
                record_movement(
                    product=item.product,
                    variant=item.variant,
                    kind="return",
                    delta=qty,
                    source="order",
                    source_ref=str(item.pk),
                    note=instance.reference_code,
                )
                # Склад-2 E1.5: обратить FEFO-расход — долить партии (no-op без партий).
                from apps.inventory.services import restore_fefo

                restore_fefo(item.product, item.variant, qty=qty)
        # P2 «ценовой слой»: заказ из акции возвращает ЛИМИТ КАМПАНИИ (маркер
        # {"promo": id} в modifiers custom-строки). Единственная точка возврата:
        # сюда приходят и встроенный FSM, и зеркало кастом-статусов
        # (status_effects.restore_stock_for("order") зовёт этот же _restore_stock).
        _restore_promo_limits(instance)


def _restore_promo_limits(instance):
    from django.db.models import F

    from apps.promotions.models import Promotion
    from apps.promotions.services import notify_waitlist_available

    per_promo = {}
    for item in instance.items.all():
        for mod in item.modifiers or []:
            promo_id = isinstance(mod, dict) and mod.get("promo")
            if promo_id:
                per_promo[promo_id] = per_promo.get(promo_id, 0) + item.qty
    from apps.aggregator.stock_sync import touch_promotion

    for promo_id, qty in per_promo.items():
        Promotion.objects.filter(id=promo_id, available_quantity__isnull=False).update(
            available_quantity=F("available_quantity") + qty
        )
        touch_promotion(promo_id)  # T-8.26 п.3
        promo = Promotion.objects.filter(id=promo_id).first()
        if promo is not None:
            notify_waitlist_available(promo)
