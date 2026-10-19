"""T-8.10h: единственный писатель привязки владельца к общему боту.

Две стороны одной привязки: строка ``OwnerTelegramLink`` (SHARED, обратный поиск
«чат → бизнесы») и зеркало в ``site_config["notify"]`` бизнеса (``owner_chat_id`` +
``owner_bot``), которое читают уведомления и проверка владельца в Telegram-акциях.
Обе пишутся здесь в одной транзакции — иначе они разъедутся.
"""

from __future__ import annotations

from django.db import transaction
from django.utils import timezone

from .models import OwnerTelegramLink

OWNER_BOT_PLATFORM = "platform"
OWNER_BOT_TENANT = "tenant"


def _write_mirror(tenant_pk, **changes) -> dict:
    from apps.tenants.models import Tenant

    tenant = Tenant.objects.select_for_update().get(pk=tenant_pk)
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
        tenant.site_config = _write_mirror(
            tenant.pk, owner_chat_id=str(tg_user_id), owner_bot=OWNER_BOT_PLATFORM
        )
    return link


def unbind(tenant) -> None:
    """Снять привязку бизнеса: связи общего бота и зеркало владельца."""
    with transaction.atomic():
        OwnerTelegramLink.objects.filter(tenant=tenant, is_active=True).update(
            is_active=False, updated_at=timezone.now()
        )
        tenant.site_config = _write_mirror(tenant.pk, owner_chat_id=None, owner_bot=None)


def active_links(tg_user_id: int):
    return (
        OwnerTelegramLink.objects.filter(
            tg_user_id=int(tg_user_id), is_active=True, blocked_at__isnull=True
        )
        .select_related("tenant")
        .order_by("-selected_at", "-created_at")
    )


def is_owner(tg_user_id, tenant) -> bool:
    """Владелец через общий бот: активная связь И зеркало бизнеса указывает на этот чат
    (перепривязка к другому чату или к своему боту снимает право)."""
    from apps.telegram.notify import _notify_node

    node = _notify_node(tenant)
    if node.get("owner_bot") != OWNER_BOT_PLATFORM:
        return False
    if str(node.get("owner_chat_id") or "") != str(tg_user_id):
        return False
    return active_links(tg_user_id).filter(tenant=tenant).exists()


def mark_blocked(tg_user_id: int) -> int:
    """Пользователь заблокировал бот — доставка через общий бот прекращается."""
    return OwnerTelegramLink.objects.filter(
        tg_user_id=int(tg_user_id), blocked_at__isnull=True
    ).update(blocked_at=timezone.now(), updated_at=timezone.now())
