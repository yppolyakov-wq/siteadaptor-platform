"""FSM заказа Click & Collect / доставка (Track D / D2, G4). База — apps.core.fsm.

new → confirmed → ready → picked_up (самовывоз) | shipped (доставка); отмена — из
любого незавершённого статуса. Каждый переход шлёт письмо клиенту (notifications
dedupe); picked_up/shipped пишут выручку (finance).
"""

from apps.core.fsm import StateMachine, Transition


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
        if t.dst == "cancelled" and getattr(instance, "voucher_code", ""):
            from apps.promotions.services import unredeem_voucher

            # B1.5: balance-сертификату возвращается и списанная сумма (снимок).
            unredeem_voucher(
                instance.voucher_code, amount_cents=getattr(instance, "discount_cents", 0)
            )

        # Выдан/отправлен → запись в журнал выручки (D4a, идемпотентно по
        # source_ref). Доставка включена в total → попадает в выручку.
        if t.dst in ("picked_up", "shipped"):
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
            if item.variant_id:
                n = ProductVariant.objects.filter(
                    pk=item.variant_id, stock_quantity__isnull=False
                ).update(stock_quantity=F("stock_quantity") + item.qty)
            else:
                n = Product.objects.filter(pk=item.product_id, stock_quantity__isnull=False).update(
                    stock_quantity=F("stock_quantity") + item.qty
                )
            if n:  # реально вернули (учитываемый остаток) → запись в леджер
                record_movement(
                    product=item.product,
                    variant=item.variant,
                    kind="return",
                    delta=item.qty,
                    source="order",
                    source_ref=str(item.pk),
                    note=instance.reference_code,
                )
                # Склад-2 E1.5: обратить FEFO-расход — долить партии (no-op без партий).
                from apps.inventory.services import restore_fefo

                restore_fefo(item.product, item.variant, qty=item.qty)
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
    for promo_id, qty in per_promo.items():
        Promotion.objects.filter(id=promo_id, available_quantity__isnull=False).update(
            available_quantity=F("available_quantity") + qty
        )
        promo = Promotion.objects.filter(id=promo_id).first()
        if promo is not None:
            notify_waitlist_available(promo)
