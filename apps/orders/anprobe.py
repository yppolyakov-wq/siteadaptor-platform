"""M3 Boutique (план m3-click-reserve-plan-2026-07-30): Click&Reserve —
«In der Anprobe zurücklegen».

Резерв = обычный Order (fulfillment=pickup, payment on_site, qty=1) с
`reserve_expires_at` и source_channel="anprobe": anti-oversell, возврат стока
при cancelled и канбан — штатные пути заказа; письма created/cancelled
ремапятся на unverbindlich-тексты (KEIN Kaufvertrag). Beat
`expire_due_anprobe` отменяет просроченные.
"""

from datetime import timedelta

from django.utils import timezone

ANPROBE_TTL_HOURS = 48


def create_anprobe(*, product, variant=None, name, email="", phone=""):
    """Создать Anprobe-резерв (одна вещь, TTL 48 ч). OutOfStock пробрасывается."""
    from apps.orders.services import create_order

    return create_order(
        items=[(product, variant, 1)],
        name=name,
        email=email,
        phone=phone,
        source_channel="anprobe",
        payment_method="on_site",
        reserve_expires_at=timezone.now() + timedelta(hours=ANPROBE_TTL_HOURS),
    )
