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


def _tenant_base_defaults(tenant) -> dict:
    """Денормализованные поля бизнеса, общие для всех видов листинга."""
    return {
        "tenant_slug": tenant.slug,
        "business_name": tenant.name,
        "business_type": tenant.business_type,
        "city": tenant.city,
        "latitude": tenant.latitude,  # G8c: гео для карты/«рядом»
        "longitude": tenant.longitude,
    }


def sync_listing(tenant_schema, promotion_id) -> str:
    """Чистая логика (вызывается из задачи и тестов): upsert/remove листинга."""
    from apps.tenants.models import Tenant

    from .models import AggregatorListing

    with schema_context(tenant_schema):
        snap = _snapshot(promotion_id)

    tenant = Tenant.objects.filter(schema_name=tenant_schema).first()
    key = {
        "tenant_schema": tenant_schema,
        "listing_kind": AggregatorListing.KIND_PROMOTION,
        "source_ref": str(promotion_id),
    }

    # Нет акции/тенанта или акция неактивна → листинга в агрегаторе быть не должно.
    if snap is None or tenant is None or snap["status"] != "active":
        AggregatorListing.objects.filter(**key).delete()
        return "removed"

    base = getattr(settings, "TENANT_DOMAIN_BASE", "siteadaptor.de")
    AggregatorListing.objects.update_or_create(
        **key,
        defaults={
            **_tenant_base_defaults(tenant),
            "promo_uuid": promotion_id,
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


# --- A5/A6: листинги по датам (размещение/события) ----------------------------


def _stay_snapshot(unit_id):
    """Снимок юнита размещения в ТЕКУЩЕЙ (tenant) схеме → dict или None.

    Листим, только пока юнит активен (is_active). Цена — «ab price_cents/Nacht»
    (минимальная база; сезон/выходные считаются на витрине при выборе дат)."""
    from decimal import Decimal

    from apps.stays.models import StayUnit

    unit = StayUnit.objects.filter(id=unit_id).first()
    if unit is None or not unit.is_active:
        return None
    return {
        "title": {"de": unit.name},
        "teaser": {"de": (unit.description or "")[:300]} if unit.description else {},
        "new_price": (Decimal(unit.price_cents) / 100) if unit.price_cents else None,
    }


def sync_stay_listing(tenant_schema, unit_id) -> str:
    """Upsert/remove листинга размещения (StayUnit) в агрегаторе (A5)."""
    from apps.tenants.models import Tenant

    from .models import AggregatorListing

    with schema_context(tenant_schema):
        snap = _stay_snapshot(unit_id)

    tenant = Tenant.objects.filter(schema_name=tenant_schema).first()
    key = {
        "tenant_schema": tenant_schema,
        "listing_kind": AggregatorListing.KIND_STAY,
        "source_ref": str(unit_id),
    }
    # Юнит исчез/выключен, нет тенанта или модуль stays неактивен → нет листинга.
    if snap is None or tenant is None or not tenant.is_module_active("stays"):
        AggregatorListing.objects.filter(**key).delete()
        return "removed"

    base = getattr(settings, "TENANT_DOMAIN_BASE", "siteadaptor.de")
    AggregatorListing.objects.update_or_create(
        **key,
        defaults={
            **_tenant_base_defaults(tenant),
            "promo_uuid": None,
            "title": snap["title"],
            "teaser": snap["teaser"],
            "image": {},
            "new_price": snap["new_price"],
            "old_price": None,
            "discount_percent": None,
            "starts_at": None,
            "ends_at": None,
            "detail_url": f"{_scheme()}://{tenant.slug}.{base}/unterkunft/{unit_id}/",
            "is_surprise": False,
            "is_active": True,
        },
    )
    return "upserted"


@idempotent_task()
def sync_aggregator_stay(*, tenant_schema, unit_id):
    """Beat/hook: материализовать листинг размещения в агрегаторе."""
    return {"result": sync_stay_listing(tenant_schema, unit_id)}


def _event_snapshot(event_id):
    """Снимок события в ТЕКУЩЕЙ (tenant) схеме → dict или None.

    Листим опубликованные будущие события (прошедшие/черновики/отменённые — нет)."""
    from decimal import Decimal

    from django.utils import timezone

    from apps.events.models import Event

    event = Event.objects.filter(id=event_id).first()
    if event is None or not event.is_published or event.starts_at < timezone.now():
        return None
    return {
        "title": {"de": event.title},
        "teaser": {"de": (event.description or "")[:300]} if event.description else {},
        "new_price": (Decimal(event.price_cents) / 100) if event.price_cents else None,
        "starts_at": event.starts_at,
        "ends_at": event.ends_at,
    }


def sync_event_listing(tenant_schema, event_id) -> str:
    """Upsert/remove листинга события (Event) в агрегаторе (A6)."""
    from apps.tenants.models import Tenant

    from .models import AggregatorListing

    with schema_context(tenant_schema):
        snap = _event_snapshot(event_id)

    tenant = Tenant.objects.filter(schema_name=tenant_schema).first()
    key = {
        "tenant_schema": tenant_schema,
        "listing_kind": AggregatorListing.KIND_EVENT,
        "source_ref": str(event_id),
    }
    if snap is None or tenant is None or not tenant.is_module_active("events"):
        AggregatorListing.objects.filter(**key).delete()
        return "removed"

    base = getattr(settings, "TENANT_DOMAIN_BASE", "siteadaptor.de")
    AggregatorListing.objects.update_or_create(
        **key,
        defaults={
            **_tenant_base_defaults(tenant),
            "promo_uuid": None,
            "title": snap["title"],
            "teaser": snap["teaser"],
            "image": {},
            "new_price": snap["new_price"],
            "old_price": None,
            "discount_percent": None,
            "starts_at": snap["starts_at"],
            "ends_at": snap["ends_at"],
            "detail_url": f"{_scheme()}://{tenant.slug}.{base}/veranstaltung/{event_id}/",
            "is_surprise": False,
            "is_active": True,
        },
    )
    return "upserted"


@idempotent_task()
def sync_aggregator_event(*, tenant_schema, event_id):
    """Beat/hook: материализовать листинг события в агрегаторе."""
    return {"result": sync_event_listing(tenant_schema, event_id)}


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


def resync_on_stay_save(sender, instance, **kwargs):
    """post_save StayUnit: правка/активация/деактивация → обновить листинг (A5).

    Задача сама решает upsert vs remove (по is_active + модулю). enqueue после
    коммита, чтобы не прочитать несохранённые данные; dedupe — по updated_at.
    """
    from django.db import connection, transaction

    schema = connection.schema_name
    dedupe = f"agg-stay:{instance.id}:save:{instance.updated_at.timestamp()}"
    transaction.on_commit(
        lambda: sync_aggregator_stay.delay(
            dedupe_key=dedupe, tenant_schema=schema, unit_id=str(instance.id)
        )
    )


def resync_on_stay_delete(sender, instance, **kwargs):
    """post_delete StayUnit: убрать листинг размещения."""
    from django.db import connection, transaction

    schema = connection.schema_name
    unit_id = str(instance.id)
    transaction.on_commit(
        lambda: sync_aggregator_stay.delay(
            dedupe_key=f"agg-stay:{unit_id}:delete", tenant_schema=schema, unit_id=unit_id
        )
    )


def resync_on_event_save(sender, instance, **kwargs):
    """post_save Event: правка опубликованного события → обновить листинг (A6).

    SM-хук ловит смену статуса; цена/дата/текст у уже опубликованного события
    иначе застыли бы в листинге. Задача сама решает upsert vs remove.
    """
    from django.db import connection, transaction

    schema = connection.schema_name
    dedupe = f"agg-event:{instance.id}:save:{instance.updated_at.timestamp()}"
    transaction.on_commit(
        lambda: sync_aggregator_event.delay(
            dedupe_key=dedupe, tenant_schema=schema, event_id=str(instance.id)
        )
    )


def reconcile_schema(tenant_schema) -> int:
    """Привести агрегатор к полному соответствию для одной схемы.

    Upsert всех активных акций + размещений (stays) + опубликованных будущих
    событий (events) + удаление устаревших листингов. Хуки материализуют по
    будущим переходам; это — для бэкофилла/реконсиляции (команда sync_aggregator).
    Возвращает число активных листингов. AggregatorListing — SHARED (public).
    """
    from apps.tenants.models import Tenant

    from .models import AggregatorListing

    tenant = Tenant.objects.filter(schema_name=tenant_schema).first()
    total = 0

    # --- акции ---
    from apps.promotions.models import Promotion

    with schema_context(tenant_schema):
        promo_ids = [
            str(pid)
            for pid in Promotion.objects.filter(status="active").values_list("id", flat=True)
        ]
    for promo_id in promo_ids:
        sync_listing(tenant_schema, promo_id)
    AggregatorListing.objects.filter(
        tenant_schema=tenant_schema, listing_kind=AggregatorListing.KIND_PROMOTION
    ).exclude(source_ref__in=promo_ids).delete()
    total += len(promo_ids)

    # --- размещения (stays) — только если модуль активен ---
    stay_ids = []
    if tenant is not None and tenant.is_module_active("stays"):
        from apps.stays.models import StayUnit

        with schema_context(tenant_schema):
            stay_ids = [
                str(uid)
                for uid in StayUnit.objects.filter(is_active=True).values_list("id", flat=True)
            ]
        for unit_id in stay_ids:
            sync_stay_listing(tenant_schema, unit_id)
    AggregatorListing.objects.filter(
        tenant_schema=tenant_schema, listing_kind=AggregatorListing.KIND_STAY
    ).exclude(source_ref__in=stay_ids).delete()
    total += len(stay_ids)

    # --- события (events) — опубликованные будущие, если модуль активен ---
    event_ids = []
    if tenant is not None and tenant.is_module_active("events"):
        from django.utils import timezone

        from apps.events.models import Event

        with schema_context(tenant_schema):
            event_ids = [
                str(eid)
                for eid in Event.objects.filter(
                    status=Event.STATUS_PUBLISHED, starts_at__gte=timezone.now()
                ).values_list("id", flat=True)
            ]
        for event_id in event_ids:
            sync_event_listing(tenant_schema, event_id)
    AggregatorListing.objects.filter(
        tenant_schema=tenant_schema, listing_kind=AggregatorListing.KIND_EVENT
    ).exclude(source_ref__in=event_ids).delete()
    total += len(event_ids)

    return total
