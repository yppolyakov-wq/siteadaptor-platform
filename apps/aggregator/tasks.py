"""Материализация AggregatorListing из акций (кросс-схемно, идемпотентно).

Агрегатор — SHARED (public). Акции — в TENANT-схемах. Задача читает акцию в её
schema_context, снимает плоский снимок карточки, затем upsert/удаляет листинг в
public. Дёргается хуком PromotionSM на переходах (active → upsert; ended/paused/
archived → remove). Резистентна к отсутствию акции/тенанта (просто удаляет листинг).
"""

from django.conf import settings
from django_tenants.utils import schema_context

from apps.core.jobs import idempotent_task


def _scheme() -> str:
    return "http" if getattr(settings, "DEBUG", False) else "https"


def _snapshot(promotion_id):
    """Снимок карточки акции в ТЕКУЩЕЙ (tenant) схеме → dict или None."""
    from apps.promotions.models import Promotion

    promo = Promotion.objects.filter(id=promotion_id).first()
    if promo is None:
        return None
    return {
        "status": promo.status,
        "title": promo.title or {},
        "teaser": promo.description or {},
        "image": promo.primary_image or {},
        "currency": promo.currency,
        "old_price": promo.old_price,
        "new_price": promo.new_price,
        "discount_percent": promo.discount_percent_display,
        "starts_at": promo.starts_at,
        "ends_at": promo.ends_at,
        "is_surprise": promo.is_surprise,
    }


def sync_listing(tenant_schema, promotion_id) -> str:
    """Чистая логика (вызывается из задачи и тестов): upsert/remove листинга."""
    from apps.tenants.models import Tenant

    from .models import AggregatorListing

    with schema_context(tenant_schema):
        snap = _snapshot(promotion_id)

    tenant = Tenant.objects.filter(schema_name=tenant_schema).first()
    key = {"tenant_schema": tenant_schema, "promo_uuid": promotion_id}

    # Нет акции/тенанта или акция неактивна → листинга в агрегаторе быть не должно.
    if snap is None or tenant is None or snap["status"] != "active":
        AggregatorListing.objects.filter(**key).delete()
        return "removed"

    base = getattr(settings, "TENANT_DOMAIN_BASE", "siteadaptor.de")
    AggregatorListing.objects.update_or_create(
        **key,
        defaults={
            "tenant_slug": tenant.slug,
            "business_name": tenant.name,
            "business_type": tenant.business_type,
            "city": tenant.city,
            "title": snap["title"],
            "teaser": snap["teaser"],
            "image": snap["image"],
            "currency": snap["currency"],
            "old_price": snap["old_price"],
            "new_price": snap["new_price"],
            "discount_percent": snap["discount_percent"],
            "starts_at": snap["starts_at"],
            "ends_at": snap["ends_at"],
            "detail_url": f"{_scheme()}://{tenant.slug}.{base}/p/{promotion_id}/",
            "is_surprise": snap["is_surprise"],
            "is_active": True,
        },
    )
    return "upserted"


@idempotent_task()
def sync_aggregator_listing(*, tenant_schema, promotion_id):
    """Beat/hook: материализовать листинг акции в агрегаторе."""
    return {"result": sync_listing(tenant_schema, promotion_id)}


@idempotent_task()
def send_magic_link_email(*, email, url):
    """Письмо со ссылкой входа на портал (P2.3a). dedupe_key — хэш токена.

    Шлём напрямую (send_mail), не через apps.notifications: та модель — TENANT,
    а клиент портала живёт на public-схеме. Дедуп даёт idempotent_task.
    """
    from django.conf import settings
    from django.core.mail import send_mail

    send_mail(
        subject="Ihr Anmelde-Link",
        message=(
            "Guten Tag,\n\n"
            f"mit diesem Link melden Sie sich an: {url}\n\n"
            "Der Link ist 15 Minuten gültig und kann nur einmal verwendet werden.\n"
            "Falls Sie keine Anmeldung angefordert haben, ignorieren Sie diese E-Mail."
        ),
        from_email=settings.DEFAULT_FROM_EMAIL,
        recipient_list=[email],
    )
    return {"sent": email}


def sync_marketing_opt_out(email: str, opt_out: bool, *, tenants=None) -> int:
    """Разнести центральную (от)подписку по схемам: Customer.unsubscribed.

    PortalUser.marketing_opt_out — источник истины на порталах; здесь оно
    доводится до per-tenant Customer (его уважают рассылки бизнесов и
    one-click `/u/<token>/`). tenants инжектится в тестах (физических
    схем там нет — как в reconcile_schema).
    """
    from django_tenants.utils import get_public_schema_name, get_tenant_model

    from apps.promotions.models import Customer

    if tenants is None:
        tenants = get_tenant_model().objects.exclude(schema_name=get_public_schema_name())
    updated = 0
    for tenant in tenants:
        with schema_context(tenant.schema_name):
            updated += Customer.objects.filter(email__iexact=email).update(unsubscribed=opt_out)
    return updated


@idempotent_task()
def apply_marketing_opt_out(*, email, opt_out):
    """Celery: применить выбор клиента из /konto/ ко всем бизнесам."""
    return {"updated": sync_marketing_opt_out(email, opt_out)}


def resync_on_promotion_save(sender, instance, **kwargs):
    """post_save Promotion: правка активной акции → обновить её листинг.

    SM-хук ловит только переходы статуса; фото/цена/текст, изменённые у уже
    активной акции, иначе оставались бы в листинге устаревшим снимком. dedupe —
    по updated_at (повтор того же сохранения отсекается, новое — проходит);
    enqueue после коммита, чтобы задача не прочитала несохранённые данные.
    Подключение — apps.py::ready (post_save живёт в TENANT-схеме акции).
    """
    if instance.status != "active":
        return
    from django.db import connection, transaction

    schema = connection.schema_name
    dedupe = f"agg:{instance.id}:edit:{instance.updated_at.timestamp()}"
    transaction.on_commit(
        lambda: sync_aggregator_listing.delay(
            dedupe_key=dedupe,
            tenant_schema=schema,
            promotion_id=str(instance.id),
        )
    )


def reconcile_schema(tenant_schema) -> int:
    """Привести агрегатор к полному соответствию для одной схемы.

    Upsert всех активных акций + удаление устаревших листингов. Хук материализует
    по будущим переходам; это — для бэкофилла/реконсиляции (команда sync_aggregator).
    Возвращает число активных акций. AggregatorListing — SHARED (public).
    """
    from apps.promotions.models import Promotion

    from .models import AggregatorListing

    with schema_context(tenant_schema):
        active_ids = [
            str(pid)
            for pid in Promotion.objects.filter(status="active").values_list("id", flat=True)
        ]
    for promo_id in active_ids:
        sync_listing(tenant_schema, promo_id)
    AggregatorListing.objects.filter(tenant_schema=tenant_schema).exclude(
        promo_uuid__in=active_ids
    ).delete()
    return len(active_ids)
