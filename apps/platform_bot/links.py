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


def bind(tg_user_id: int, tenant, *, via: str = OwnerTelegramLink.VIA_CABINET):
    """Привязать пользователя Telegram к бизнесу через общий бот (и сделать текущим)."""
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
            locked, owner_chat_id=str(tg_user_id), owner_bot=OWNER_BOT_PLATFORM
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
            tenant.site_config = _write_mirror(locked, owner_chat_id=None, owner_bot=None)
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
