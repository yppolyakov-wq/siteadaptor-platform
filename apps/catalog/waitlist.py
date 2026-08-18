"""M2 Boutique: Warteliste по товару/размеру.

`join` — идемпотентная подписка с витрины; `notify_available` — письма всем
живым подпискам товара (и конкретного размера) при приёмке склада. Вызов из
inventory.apply_manual_movement через on_commit + fail-safe (письмо не должно
ронять приёмку). Email-механика — как у промо-Warteliste (S6.4): notify с
dedupe_key, шаблоны emails/product_waitlist_available*.
"""

from django.db import IntegrityError


def join(product, email, variant=None):
    """Подписать email (get_or_create по живой подписке); True = новая."""
    from apps.catalog.models import ProductWaitlist

    try:
        _, created = ProductWaitlist.objects.get_or_create(
            product=product, variant=variant, email=email, notified=False
        )
    except IntegrityError:
        return False
    return created


def notify_available(product, variant=None) -> int:
    """Уведомить живые подписки: приёмка размера → подписчики этого размера +
    подписчики «товара в целом»; приёмка без варианта → все подписки товара.
    Каждая запись — ровно одно письмо (notified + dedupe_key)."""
    from django.db.models import Q

    from apps.catalog.models import ProductWaitlist
    from apps.promotions.notifications import _base_url, _render, notify

    if not product.is_active:
        return 0
    qs = ProductWaitlist.objects.filter(product=product, notified=False)
    if variant is not None:
        qs = qs.filter(Q(variant=variant) | Q(variant__isnull=True))
    count = 0
    for entry in qs.order_by("created_at"):
        from django.db import connection

        base = _base_url(connection.schema_name)
        url = f"{base}{product.get_absolute_url()}" if base else ""  # KAT-3: SEO-URL
        ctx = {"entry": entry, "product": product, "variant": entry.variant, "product_url": url}
        subject, body, html = _render("product_waitlist_available", ctx)
        notify(
            dedupe_key=f"product-waitlist:{entry.pk}:available",
            type="product_waitlist_available",
            recipient=entry.email,
            subject=subject,
            body=body,
            html=html,
        )
        entry.notified = True
        entry.save(update_fields=["notified", "updated_at"])
        count += 1
    return count


def notify_available_safe(product, variant=None) -> None:
    """Fail-safe обёртка для хука приёмки: любая ошибка писем глотается."""
    try:
        notify_available(product, variant=variant)
    except Exception:  # noqa: BLE001 — письмо не должно ронять приёмку
        pass
