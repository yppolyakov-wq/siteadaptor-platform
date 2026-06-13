"""FSM заказа Click & Collect (Track D / D2). База — apps.core.fsm.

new → confirmed → ready → picked_up; отмена — из любого незавершённого статуса.
Каждый переход шлёт письмо клиенту через notifications dedupe (D2b).
"""

from apps.core.fsm import StateMachine, Transition


class OrderSM(StateMachine):
    transitions = [
        Transition("new", "confirmed", "order.confirmed"),
        Transition("new", "cancelled", "order.cancelled"),
        Transition("confirmed", "ready", "order.ready"),
        Transition("confirmed", "cancelled", "order.cancelled"),
        Transition("ready", "picked_up", "order.picked_up"),
        Transition("ready", "cancelled", "order.cancelled"),
    ]

    def on_transition(self, instance, t, **kw):
        from .notifications import enqueue_order_email

        enqueue_order_email(instance, t.dst)

        # Отмена → возврат остатка на склад (R3). cancelled терминальный →
        # срабатывает один раз. Только по позициям с учётом (stock_quantity не null).
        if t.dst == "cancelled":
            from django.db.models import F

            from apps.catalog.models import Product, ProductVariant

            for item in instance.items.all():
                if item.variant_id:
                    ProductVariant.objects.filter(
                        pk=item.variant_id, stock_quantity__isnull=False
                    ).update(stock_quantity=F("stock_quantity") + item.qty)
                else:
                    Product.objects.filter(pk=item.product_id, stock_quantity__isnull=False).update(
                        stock_quantity=F("stock_quantity") + item.qty
                    )

        # Выдан → запись в журнал выручки (D4a, идемпотентно по source_ref).
        if t.dst == "picked_up":
            from apps.finance.services import record_revenue

            record_revenue(
                source="order",
                source_ref=str(instance.id),
                amount=instance.total,
                currency=instance.currency,
                customer=instance.customer,
                note=instance.reference_code,
            )
