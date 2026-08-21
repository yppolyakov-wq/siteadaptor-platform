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


def _logo_image(tenant) -> dict:
    """Карточка stay/event без своего фото — фолбэк на логотип бизнеса (A5/A6).

    Шаблон карточки ждёт FileRef-конверт {"url": ...}; пусто → placeholder.
    """
    return {"url": tenant.logo_url} if getattr(tenant, "logo_url", "") else {}


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
            "image": _logo_image(tenant),
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
        "category": event.category or "",  # R2b направление для фильтра агрегатора
        "city": event.city or "",  # R2b город события (точнее, чем город бизнеса)
    }


def _event_group_ref(event) -> str:
    """6c: ключ группы события — заезды тура/серия листятся ОДНОЙ записью."""
    if event.tour_id:
        return f"tour:{event.tour_id}"
    if event.series_id:
        return f"series:{event.series_id}"
    return ""


def sync_event_group_listing(tenant_schema, group_ref) -> str:
    """6c: upsert/remove ГРУППОВОГО листинга (заезды тура / серия = одна карточка).

    Payload — ближайший БУДУЩИЙ опубликованный заезд группы; нет такого →
    запись удаляется. detail_url тура ведёт на страницу тура (там все даты),
    серии — на деталь ближайшего события (MX-6 показывает «Weitere Termine»)."""
    from django.utils import timezone as tz

    from apps.tenants.models import Tenant

    from .models import AggregatorListing

    tenant = Tenant.objects.filter(schema_name=tenant_schema).first()
    key = {
        "tenant_schema": tenant_schema,
        "listing_kind": AggregatorListing.KIND_EVENT,
        "source_ref": group_ref,
    }
    nearest_id = None
    tour_slug = tour_title = ""
    with schema_context(tenant_schema):
        from apps.events.models import Event

        kind_val, _, ident = group_ref.partition(":")
        qs = Event.objects.filter(status=Event.STATUS_PUBLISHED, starts_at__gte=tz.now())
        qs = qs.filter(tour_id=ident) if kind_val == "tour" else qs.filter(series_id=ident)
        nearest = qs.order_by("starts_at").first()
        if nearest is not None:
            nearest_id = str(nearest.id)
            if kind_val == "tour" and nearest.tour_id:
                tour_slug = nearest.tour.slug
                tour_title = nearest.tour.title
        snap = _event_snapshot(nearest_id) if nearest_id else None

    if snap is None or tenant is None or not tenant.is_module_active("events"):
        AggregatorListing.objects.filter(**key).delete()
        return "removed"
    base = getattr(settings, "TENANT_DOMAIN_BASE", "siteadaptor.de")
    detail = (
        f"{_scheme()}://{tenant.slug}.{base}/tour/{tour_slug}/"
        if tour_slug
        else f"{_scheme()}://{tenant.slug}.{base}/veranstaltung/{nearest_id}/"
    )
    AggregatorListing.objects.update_or_create(
        **key,
        defaults={
            **_tenant_base_defaults(tenant),
            "city": snap["city"] or _tenant_base_defaults(tenant)["city"],
            "category": snap["category"],
            "promo_uuid": None,
            "title": {"de": tour_title} if tour_title else snap["title"],
            "teaser": snap["teaser"],
            "image": _logo_image(tenant),
            "new_price": snap["new_price"],
            "old_price": None,
            "discount_percent": None,
            "starts_at": snap["starts_at"],
            "ends_at": snap["ends_at"],
            "detail_url": detail,
            "is_surprise": False,
            "is_active": True,
        },
    )
    return "upserted"


def sync_event_listing(tenant_schema, event_id) -> str:
    """Upsert/remove листинга события (Event) в агрегаторе (A6).

    6c: событие ГРУППЫ (tour/series) делегирует групповой записи, а свою
    per-event строку удаляет (миграционный путь со старых строк)."""
    from apps.tenants.models import Tenant

    from .models import AggregatorListing

    group_ref = ""
    with schema_context(tenant_schema):
        from apps.events.models import Event

        _ev = Event.objects.filter(id=event_id).only("id", "tour_id", "series_id").first()
        if _ev is not None:
            group_ref = _event_group_ref(_ev)
        snap = _event_snapshot(event_id)

    if group_ref:
        AggregatorListing.objects.filter(
            tenant_schema=tenant_schema,
            listing_kind=AggregatorListing.KIND_EVENT,
            source_ref=str(event_id),
        ).delete()
        return sync_event_group_listing(tenant_schema, group_ref)

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
            # город события точнее города бизнеса (выездной/филиал) — если задан
            "city": snap["city"] or _tenant_base_defaults(tenant)["city"],
            "category": snap["category"],  # R2b направление (фильтр агрегатора)
            "promo_uuid": None,
            "title": snap["title"],
            "teaser": snap["teaser"],
            "image": _logo_image(tenant),
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


def roll_event_group_listings() -> int:
    """6c (beat): групповые записи с ПРОШЕДШИМ ближайшим заездом перекатить на
    следующий (или удалить, если дат больше нет). Без этого карточка тура
    пропадала бы из выдачи (вьюха прячет starts_at в прошлом), хотя будущие
    заезды есть. Возвращает число обработанных записей."""
    from django.utils import timezone as tz

    from .models import AggregatorListing

    stale = AggregatorListing.objects.filter(
        listing_kind=AggregatorListing.KIND_EVENT,
        starts_at__lt=tz.now(),
        source_ref__regex=r"^(tour|series):",
    ).values_list("tenant_schema", "source_ref")
    n = 0
    for tenant_schema, ref in list(stale):
        sync_event_group_listing(tenant_schema, ref)
        n += 1
    return n


@idempotent_task()
def roll_aggregator_event_groups():
    """Обёртка beat: перекат групповых событийных листингов (6c)."""
    return roll_event_group_listings()


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
    # 6c: событие группы (tour/series) живёт ГРУППОВОЙ записью — в allowed идёт
    # ref группы, per-event строки групповых чистятся exclude'ом.
    event_ids, event_refs = [], []
    if tenant is not None and tenant.is_module_active("events"):
        from django.utils import timezone

        from apps.events.models import Event

        with schema_context(tenant_schema):
            rows = list(
                Event.objects.filter(
                    status=Event.STATUS_PUBLISHED, starts_at__gte=timezone.now()
                ).only("id", "tour_id", "series_id")
            )
            event_ids = [str(e.id) for e in rows]
            event_refs = list(dict.fromkeys(_event_group_ref(e) or str(e.id) for e in rows))
        for event_id in event_ids:
            sync_event_listing(tenant_schema, event_id)
    AggregatorListing.objects.filter(
        tenant_schema=tenant_schema, listing_kind=AggregatorListing.KIND_EVENT
    ).exclude(source_ref__in=event_refs).delete()
    total += len(event_refs)

    # --- MEN-5: наборы меню (Combo) — каталог core, гейт как в sync_menu_listing ---
    menu_ids = []
    if tenant is not None and tenant.is_module_active("catalog"):
        from apps.catalog.models import Combo

        with schema_context(tenant_schema):
            menu_ids = [
                str(cid)
                for cid in Combo.objects.filter(is_active=True).values_list("id", flat=True)
            ]
        for combo_id in menu_ids:
            sync_menu_listing(tenant_schema, combo_id)
    AggregatorListing.objects.filter(
        tenant_schema=tenant_schema, listing_kind=AggregatorListing.KIND_MENU
    ).exclude(source_ref__in=menu_ids).delete()
    total += len(menu_ids)

    return total


def _menu_snapshot(combo_id):
    """MEN-5: снимок набора меню (Combo) в ТЕКУЩЕЙ схеме → dict или None.

    Цена — БАЗОВАЯ сборка (`combo_price_from`, «ab X»); у свободной сборки
    считаем минимум как самое дешёвое блюдо пула (пустая сборка не продаётся).
    Диеты — СТРОГО (решение владельца 2026-08-13): чип «vegan» стоит только у
    набора, где веганское КАЖДОЕ блюдо (пересечение по составу) — гость по
    фильтру «vegan» не должен получить меню с мясным горячим. У свободной
    сборки пересечение считается по пулу: гость волен взять любое блюдо, так
    что обещать диету можно, лишь когда её держит весь пул. Блюда — в dish_names.
    """
    from apps.catalog.combos import combo_price_from, pool_products
    from apps.catalog.models import Combo

    combo = Combo.objects.filter(id=combo_id).prefetch_related("groups__options__product").first()
    if combo is None or not combo.is_active:
        return None
    if combo.free_pool:
        dishes = pool_products(combo)
        price = combo.price + (min((d.base_price for d in dishes), default=0) if dishes else 0)
    else:
        dishes = [o.product for g in combo.groups_active for o in g.options_active if o.product_id]
        price = combo_price_from(combo)
    seen, names = set(), []
    diets: set | None = None  # None = блюд ещё не было (пустой состав → без чипов)
    for dish in dishes:
        label = str(dish)
        if label not in seen:
            seen.add(label)
            names.append(label)
        dish_diets = set(dish.diets or ())
        diets = dish_diets if diets is None else (diets & dish_diets)
    return {
        "title": {"de": combo.name, **(combo.name_i18n or {})},
        "teaser": ({"de": combo.description[:300]} if combo.description else {}),
        "new_price": price or None,
        "currency": combo.currency or "EUR",
        "image": (combo.images or [{}])[0] if combo.images else {},
        "price_per_person": combo.price_per_person,
        "min_persons": combo.min_persons,
        "event_types": list(combo.event_types or []),
        "diets": sorted(diets or ()),
        "dish_names": names[:40],
    }


def sync_menu_listing(tenant_schema, combo_id) -> str:
    """MEN-5: upsert/remove листинга набора меню в агрегаторе."""
    from apps.tenants.models import Tenant

    from .models import AggregatorListing

    with schema_context(tenant_schema):
        snap = _menu_snapshot(combo_id)

    tenant = Tenant.objects.filter(schema_name=tenant_schema).first()
    key = {
        "tenant_schema": tenant_schema,
        "listing_kind": AggregatorListing.KIND_MENU,
        "source_ref": str(combo_id),
    }
    # Набор исчез/выключен, нет тенанта или каталог недоступен → нет листинга.
    if snap is None or tenant is None or not tenant.is_module_active("catalog"):
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
            "image": snap["image"] or _logo_image(tenant),
            "currency": snap["currency"],
            "new_price": snap["new_price"],
            "old_price": None,
            "discount_percent": None,
            "starts_at": None,
            "ends_at": None,
            "detail_url": f"{_scheme()}://{tenant.slug}.{base}/kombi/{combo_id}/",
            "price_per_person": snap["price_per_person"],
            "min_persons": snap["min_persons"],
            "event_types": snap["event_types"],
            "diets": snap["diets"],
            "dish_names": snap["dish_names"],
            "is_surprise": False,
            "is_active": True,
        },
    )
    return "upserted"


@idempotent_task()
def sync_aggregator_menu(*, tenant_schema, combo_id):
    """Beat/hook: материализовать листинг набора меню в агрегаторе."""
    return {"result": sync_menu_listing(tenant_schema, combo_id)}


def resync_on_combo_save(sender, instance, **kwargs):
    """post_save Combo: правка/включение/выключение → обновить листинг."""
    from django.db import connection, transaction

    schema = connection.schema_name
    dedupe = f"agg-menu:{instance.id}:save:{instance.updated_at.timestamp()}"
    transaction.on_commit(
        lambda: sync_aggregator_menu.delay(
            dedupe_key=dedupe, tenant_schema=schema, combo_id=str(instance.id)
        )
    )


def resync_on_combo_part_save(sender, instance, **kwargs):
    """post_save/-delete группы или опции: пересинк РОДИТЕЛЬСКОГО набора.

    Состав правится гранулярно (N опций = N сигналов), поэтому dedupe — по id
    набора и метке времени части: пачка правок схлопывается в одну задачу.
    """
    from django.db import connection, transaction

    combo_id = getattr(instance, "combo_id", None) or getattr(
        getattr(instance, "group", None), "combo_id", None
    )
    if not combo_id:
        return
    schema = connection.schema_name
    stamp = getattr(instance, "updated_at", None)
    dedupe = f"agg-menu:{combo_id}:part:{stamp.timestamp() if stamp else ''}"
    transaction.on_commit(
        lambda: sync_aggregator_menu.delay(
            dedupe_key=dedupe, tenant_schema=schema, combo_id=str(combo_id)
        )
    )
