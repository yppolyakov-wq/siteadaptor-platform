"""T-8.10h: единственный писатель привязки владельца к общему боту.

Две стороны одной привязки: строка ``OwnerTelegramLink`` (SHARED, обратный поиск
«чат → бизнесы») и зеркало в ``site_config["notify"]`` бизнеса (``owner_chat_id`` +
``owner_bot``), которое читают уведомления и проверка владельца в Telegram-акциях.
Обе пишутся здесь в одной транзакции под замком строки бизнеса (единый порядок
блокировок «бизнес → связи»). Источник истины о праве — ТАБЛИЦА (`is_owner`); зеркало —
кэш для доставки уведомлений: его может перезаписать устаревший Save кабинета.
"""

from __future__ import annotations

from django.db import transaction
from django.utils import timezone

from .models import OwnerTelegramLink

OWNER_BOT_PLATFORM = "platform"
OWNER_BOT_TENANT = "tenant"


def _lock(tenant_pk):
    from apps.tenants.models import Tenant

    return Tenant.objects.select_for_update().get(pk=tenant_pk)


def _write_mirror(tenant, **changes) -> dict:
    cfg = tenant.site_config if isinstance(tenant.site_config, dict) else {}
    node = cfg.get("notify") if isinstance(cfg.get("notify"), dict) else {}
    node = {**node}
    for key, value in changes.items():
        if value is None:
            node.pop(key, None)
        else:
            node[key] = value
    cfg["notify"] = node
    tenant.site_config = cfg
    tenant.save(update_fields=["site_config"])
    return cfg


def bind(
    tg_user_id: int,
    tenant,
    *,
    via: str = OwnerTelegramLink.VIA_CABINET,
    user_pk=None,
    clear_pending: bool = False,
):
    """Привязать пользователя Telegram к бизнесу через общий бот (и сделать текущим).

    ``user_pk`` — пользователь кабинета, выпустивший ссылку: доставка проверяет, что он
    всё ещё владелец (понизили/удалили из команды — уведомления через общий бот гаснут)."""
    tg_user_id = int(tg_user_id)
    with transaction.atomic():
        locked = _lock(tenant.pk)  # сначала бизнес, потом связи — без взаимоблокировок
        # У бизнеса один владелец-чат: прежние связи других чатов гаснут.
        OwnerTelegramLink.objects.filter(tenant=tenant, is_active=True).exclude(
            tg_user_id=tg_user_id
        ).update(is_active=False, updated_at=timezone.now())
        link, _created = OwnerTelegramLink.objects.update_or_create(
            tg_user_id=tg_user_id,
            tenant=tenant,
            defaults={
                "is_active": True,
                "via": via,
                "selected_at": timezone.now(),
                "blocked_at": None,
            },
        )
        # Вызывающему — свежий site_config (сохранять его объект без update_fields нельзя).
        tenant.site_config = _write_mirror(
            locked,
            owner_chat_id=str(tg_user_id),
            owner_bot=OWNER_BOT_PLATFORM,
            owner_user_pk=user_pk,  # None — ключ снимается
            **({"pending_tg_owner": None} if clear_pending else {}),
        )
    return link


def _mirror_bot(tenant) -> str:
    cfg = tenant.site_config if isinstance(tenant.site_config, dict) else {}
    node = cfg.get("notify") if isinstance(cfg.get("notify"), dict) else {}
    return str(node.get("owner_bot") or "")


def unbind(tenant) -> None:
    """Снять привязку бизнеса к общему боту. Зеркало чистим, только если оно принадлежит
    общему боту: владелец на своём боте бизнеса этим не отключается."""
    with transaction.atomic():
        locked = _lock(tenant.pk)
        OwnerTelegramLink.objects.filter(tenant=tenant, is_active=True).update(
            is_active=False, updated_at=timezone.now()
        )
        if _mirror_bot(locked) == OWNER_BOT_PLATFORM:
            tenant.site_config = _write_mirror(
                locked, owner_chat_id=None, owner_bot=None, owner_user_pk=None
            )
        else:
            tenant.site_config = locked.site_config


def _active(tg_user_id):
    return OwnerTelegramLink.objects.filter(
        tg_user_id=int(tg_user_id), is_active=True, blocked_at__isnull=True
    )


def active_links(tg_user_id: int):
    from django.db.models import F

    return (
        _active(tg_user_id)
        .select_related("tenant")
        .order_by(F("selected_at").desc(nulls_last=True), "-created_at")
    )


def is_owner(tg_user_id, tenant) -> bool:
    """Владелец через общий бот = активная, не заблокированная связь (одна на бизнес —
    ограничение БД). Читаем только таблицу: зеркало в site_config — кэш доставки."""
    return _active(tg_user_id).filter(tenant=tenant).exists()


def mark_unblocked(tg_user_id: int) -> int:
    """Пользователь снова пишет боту (или разблокировал его) — доставка возобновляется."""
    return OwnerTelegramLink.objects.filter(
        tg_user_id=int(tg_user_id), blocked_at__isnull=False
    ).update(blocked_at=None, updated_at=timezone.now())


def mark_blocked(tg_user_id: int) -> int:
    """Пользователь заблокировал бот — доставка через общий бот прекращается."""
    return OwnerTelegramLink.objects.filter(
        tg_user_id=int(tg_user_id), blocked_at__isnull=True
    ).update(blocked_at=timezone.now(), updated_at=timezone.now())


def claim_for_tenant_bot(tenant, chat_id, *, rotate_token: str) -> None:
    """Владелец подключил СВОЙ бот бизнеса (`/start owner-…`): связи общего бота гаснут,
    зеркало переходит на свой бот, токен deep link ротируется (одноразовый)."""
    with transaction.atomic():
        locked = _lock(tenant.pk)
        OwnerTelegramLink.objects.filter(tenant=tenant, is_active=True).update(
            is_active=False, updated_at=timezone.now()
        )
        tenant.site_config = _write_mirror(
            locked,
            owner_chat_id=str(chat_id),
            owner_bot=OWNER_BOT_TENANT,
            owner_link_token=rotate_token,
            owner_user_pk=None,
        )


def disconnect(tenant) -> None:
    """«Trennen» в кабинете — какой бы бот ни был подключён."""
    with transaction.atomic():
        locked = _lock(tenant.pk)
        OwnerTelegramLink.objects.filter(tenant=tenant, is_active=True).update(
            is_active=False, updated_at=timezone.now()
        )
        tenant.site_config = _write_mirror(
            locked, owner_chat_id=None, owner_bot=None, owner_user_pk=None
        )


def select(tg_user_id, link_id):
    """Сделать связь текущей — только СВОЮ активную; чужая/неактивная → None."""
    link = _active(tg_user_id).filter(pk=link_id).select_related("tenant").first()
    if link is None:
        return None
    link.selected_at = timezone.now()
    link.save(update_fields=["selected_at", "updated_at"])
    return link


def owner_route(tenant) -> tuple[str, str]:
    """(вид бота, чат владельца) для уведомления; ('', '') — доставить нечем.

    Общий бот — только при живой связи в ТАБЛИЦЕ (зеркало могло устареть)."""
    from apps.telegram import bots

    cfg = getattr(tenant, "site_config", None)
    cfg = cfg if isinstance(cfg, dict) else {}
    node = cfg.get("notify") if isinstance(cfg.get("notify"), dict) else {}
    chat = str(node.get("owner_chat_id") or "")
    if not chat:
        return ("", "")
    if node.get("owner_bot") == OWNER_BOT_PLATFORM:
        if (
            tenant is None
            or bots.platform_bot() is None
            or not chat.isdigit()
            or not is_owner(int(chat), tenant)
            or not still_owner(tenant)
        ):
            return ("", "")
        return (OWNER_BOT_PLATFORM, chat)
    if bots.tenant_bot() is None:
        return ("", "")
    return (OWNER_BOT_TENANT, chat)


def still_owner(tenant) -> bool:
    """Выпустивший ссылку пользователь — всё ещё активный владелец (читается в схеме бизнеса).
    Связь без пользователя кабинета (регистрация через бот, H-5) — по таблице связей."""
    from apps.core.models import Membership

    cfg = getattr(tenant, "site_config", None)
    node = cfg.get("notify") if isinstance(cfg, dict) else None
    user_pk = node.get("owner_user_pk") if isinstance(node, dict) else None
    if not user_pk:
        return True
    return Membership.objects.filter(
        user_id=user_pk, user__is_active=True, role=Membership.ROLE_OWNER
    ).exists()


def platform_linked(tenant) -> bool:
    """Для показа в кабинете: владелец подключён к общему боту И связь жива по таблице
    (заблокировал бот / связь сменилась — показываем «не подключено», а не ложное «да»)."""
    cfg = getattr(tenant, "site_config", None)
    node = cfg.get("notify") if isinstance(cfg, dict) else None
    if not isinstance(node, dict) or node.get("owner_bot") != OWNER_BOT_PLATFORM:
        return False
    chat = str(node.get("owner_chat_id") or "")
    return chat.isdigit() and is_owner(int(chat), tenant)


# --- H-5b: привязка регистрации через бот — только после подтверждения почты -------------


PENDING_MAX_AGE = 30 * 24 * 3600  # = срок жизни ссылки подтверждения (owner_login)


def pending_marker(tenant) -> dict | None:
    """Метка «чат регистрации ждёт почты»; протухшая (старше ссылки) — как нет."""
    import time

    cfg = getattr(tenant, "site_config", None)
    node = cfg.get("notify") if isinstance(cfg, dict) else None
    marker = node.get("pending_tg_owner") if isinstance(node, dict) else None
    if not isinstance(marker, dict) or not marker.get("uid"):
        return None
    if time.time() - float(marker.get("at") or 0) > PENDING_MAX_AGE:
        return None
    return marker


def complete_pending(tenant) -> tuple[str, int | None, str]:
    """Почта подтверждена: привязать чат регистрации (метка) владельцем.

    → (итог, uid, язык): "bound" | "taken" (в кабинете уже выбран другой чат/свой бот —
    выбор кабинета не перебиваем, метка снимается) | "none" (метки нет)."""
    from django_tenants.utils import schema_context

    from apps.core.models import Membership

    with transaction.atomic():
        locked = _lock(tenant.pk)
        marker = pending_marker(locked)
        if marker is None:
            return ("none", None, "")
        uid, lang = int(marker["uid"]), str(marker.get("lang") or "")
        cfg = locked.site_config if isinstance(locked.site_config, dict) else {}
        node = cfg.get("notify") if isinstance(cfg.get("notify"), dict) else {}
        other = (
            OwnerTelegramLink.objects.filter(tenant=locked, is_active=True)
            .exclude(tg_user_id=uid)
            .exists()
        )
        if other or node.get("owner_bot") == OWNER_BOT_TENANT:
            tenant.site_config = _write_mirror(locked, pending_tg_owner=None)
            return ("taken", uid, lang)
        with schema_context(locked.schema_name):
            owner = (
                Membership.objects.filter(role=Membership.ROLE_OWNER, user__is_active=True)
                .order_by("created_at")
                .first()
            )
        bind(
            uid,
            locked,
            via=OwnerTelegramLink.VIA_SIGNUP,
            user_pk=owner.user_id if owner else None,
            clear_pending=True,
        )
        tenant.site_config = locked.site_config
    return ("bound", uid, lang)


def pending_for(tg_user_id):
    """Бизнесы, зарегистрированные этим чатом и ждущие подтверждения почты."""
    import time

    from apps.tenants.models import Tenant

    return Tenant.objects.filter(
        site_config__notify__pending_tg_owner__uid=int(tg_user_id),
        site_config__notify__pending_tg_owner__at__gte=int(time.time() - PENDING_MAX_AGE),
        email_pending=True,
    ).exclude(provisioning_status=Tenant.PROVISIONING_FAILED)


# --- H-6: DSGVO — удаление по запросу и сроки хранения ---------------------------------


def _erase_tenant(locked, uid: int) -> None:
    """Зеркало и метка регистрации этого пользователя — под замком строки бизнеса.
    Свой бот бизнеса (owner_bot=tenant) — данные бизнеса, его не трогаем."""
    cfg = locked.site_config if isinstance(locked.site_config, dict) else {}
    node = cfg.get("notify") if isinstance(cfg.get("notify"), dict) else {}
    changes = {}
    if node.get("owner_bot") == OWNER_BOT_PLATFORM and str(node.get("owner_chat_id")) == str(uid):
        changes.update(owner_chat_id=None, owner_bot=None, owner_user_pk=None)
    marker = node.get("pending_tg_owner")
    if isinstance(marker, dict) and str(marker.get("uid")) == str(uid):
        changes["pending_tg_owner"] = None
    if changes:
        _write_mirror(locked, **changes)


def erase_user(tg_user_id) -> dict:
    """Удалить ВСЕ связи пользователя Telegram (любые) и его следы в зеркалах бизнесов.
    Сами бизнесы не удаляются. Каждый бизнес — своей транзакцией (порядок «бизнес → связи»)."""
    from apps.tenants.models import Tenant

    uid = int(tg_user_id)
    tenant_ids = set(
        OwnerTelegramLink.objects.filter(tg_user_id=uid).values_list("tenant_id", flat=True)
    )
    tenant_ids |= set(
        Tenant.objects.filter(site_config__notify__pending_tg_owner__uid=uid).values_list(
            "pk", flat=True
        )
    )
    schemas = []
    for pk in sorted(tenant_ids):
        with transaction.atomic():
            try:
                locked = _lock(pk)
            except Tenant.DoesNotExist:
                continue
            schemas.append(locked.schema_name)
            _erase_tenant(locked, uid)
            OwnerTelegramLink.objects.filter(tg_user_id=uid, tenant=locked).delete()
    return {"schemas": schemas, "tenants": len(schemas)}


INACTIVE_KEEP_DAYS = 30
BLOCKED_KEEP_DAYS = 180
PURGE_BATCH = 500  # за один проход beat; остаток — на следующий день


def purge_stale(now=None) -> dict:
    """Сроки хранения: неактивные связи — 30 дней, заблокировавшие бот — 180 дней,
    протухшие метки регистрации — снимаются."""
    import time
    from datetime import timedelta

    from apps.tenants.models import Tenant

    now = now or timezone.now()
    inactive = OwnerTelegramLink.objects.filter(
        is_active=False, updated_at__lt=now - timedelta(days=INACTIVE_KEEP_DAYS)
    ).delete()[0]
    blocked = 0
    cutoff = now - timedelta(days=BLOCKED_KEEP_DAYS)
    old_blocked = OwnerTelegramLink.objects.filter(blocked_at__lt=cutoff).values_list(
        "pk", "tenant_id", "tg_user_id"
    )[:PURGE_BATCH]
    for pk, tenant_id, uid in list(old_blocked):
        with transaction.atomic():
            try:
                locked = _lock(tenant_id)
            except Tenant.DoesNotExist:
                continue
            # Перепроверка под блокировкой: пользователь мог снова написать боту (unblock).
            deleted = OwnerTelegramLink.objects.filter(pk=pk, blocked_at__lt=cutoff).delete()[0]
            if deleted:
                _erase_tenant(locked, uid)
                blocked += deleted
    markers = 0
    edge = int(time.time() - PENDING_MAX_AGE)
    for pk in list(
        Tenant.objects.filter(site_config__notify__pending_tg_owner__at__lt=edge).values_list(
            "pk", flat=True
        )[:PURGE_BATCH]
    ):
        with transaction.atomic():
            try:
                locked = _lock(pk)
            except Tenant.DoesNotExist:
                continue
            marker = ((locked.site_config or {}).get("notify") or {}).get("pending_tg_owner")
            if not isinstance(marker, dict) or int(marker.get("at") or 0) >= edge:
                continue  # свежая метка записана после выборки — не трогать
            _write_mirror(locked, pending_tg_owner=None)
            markers += 1
    return {"inactive": inactive, "blocked": blocked, "markers": markers}
