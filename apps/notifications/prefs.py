"""UD4-2: настройки каналов уведомлений (email ∥ Telegram) per-событие.

Хранение — `Tenant.site_config["notify"]` (без миграции, прецедент
`low_stock_threshold`). Семантика по умолчанию = ТЕКУЩЕЕ поведение: ничего не
настроено → все каналы включены (email + Telegram шлются как раньше). Настроил
владелец → уважаем. Telegram к клиенту всё равно уходит только при привязке
(`TelegramLink.chat_id`), к владельцу — только при привязке owner_chat_id.

Резолвер `channel_enabled(tenant, audience, domain, event, channel)` зовут
доменные `enqueue_*`-функции ПЕРЕД отправкой каждого канала.
"""

import threading
from contextlib import contextmanager

from django.utils.translation import gettext_lazy as _

CHANNELS = ("email", "telegram")

# Клиентские события по домену: (event, DE-подпись). Порядок = порядок в матрице.
CUSTOMER_EVENTS = {
    "order": [
        ("created", _("Bestellung eingegangen")),
        ("confirmed", _("Bestätigt")),
        ("ready", _("Abholbereit")),
        ("picked_up", _("Abgeholt")),
        ("shipped", _("Versendet")),
        ("cancelled", _("Storniert")),
        ("returned", _("Retoure")),
        ("post_purchase", _("Danke & Bewertung")),
        ("payment_reminder", _("Zahlungserinnerung")),
    ],
    "booking": [
        ("created", _("Termin eingegangen")),
        ("confirmed", _("Bestätigt")),
        ("cancelled", _("Storniert")),
        ("reminder", _("Terminerinnerung")),
        ("post_visit", _("Danke & Bewertung")),
        ("payment_reminder", _("Zahlungserinnerung")),
    ],
    "stay": [
        ("created", _("Buchung eingegangen")),
        ("confirmed", _("Bestätigt")),
        ("cancelled", _("Storniert")),
        ("reminder", _("Anreise-Erinnerung")),
        ("post_stay", _("Danke & Bewertung")),
        ("payment_reminder", _("Zahlungserinnerung")),
    ],
    "ticket": [
        ("created", _("Ticket eingegangen")),
        ("confirmed", _("Bestätigt")),
        ("cancelled", _("Storniert")),
        ("reminder", _("Erinnerung")),
        ("post_event", _("Danke & Bewertung")),
        ("payment_reminder", _("Zahlungserinnerung")),
    ],
    "job": [
        ("quoted", _("Angebot gesendet")),
        ("done", _("Auftrag fertig")),
        ("service_reminder", _("Service-Erinnerung")),
    ],
    "reservation": [
        ("created", _("Reserviert")),
        ("confirmed", _("Bestätigt")),
        ("cancelled", _("Storniert")),
        ("expired", _("Abgelaufen")),
    ],
    # MT-3: пространство поездки. Рассылаем только объявления гида — реплики
    # чата читают в самом чате, иначе поездка утонет в письмах.
    "community": [
        ("new_post", _("Neuer Beitrag in der Reisegruppe")),
    ],
}

# Домен → ключ модуля (гейтинг строк матрицы по активным модулям бизнеса).
DOMAIN_MODULE = {
    "order": "orders",
    "booking": "booking",
    "stay": "stays",
    "ticket": "events",
    "job": "jobs",
    "reservation": "promotions",
    "community": "events",
}

# Домен → короткая DE-подпись группы (для матрицы).
DOMAIN_LABEL = {
    "order": _("Bestellungen"),
    "booking": _("Termine"),
    "stay": _("Übernachtungen"),
    "ticket": _("Tickets"),
    "job": _("Aufträge"),
    "reservation": _("Reservierungen"),
    "community": _("Reisegruppe"),
}


def _notify_cfg(tenant) -> dict:
    cfg = getattr(tenant, "site_config", None)
    if not isinstance(cfg, dict):
        return {}
    node = cfg.get("notify")
    return node if isinstance(node, dict) else {}


# DC-3 (ТЗ владельца 2026-08-25): РАЗОВОЕ подавление уведомлений на одну смену
# статуса («отправить уведомление клиенту и администратору?» на карточке сделки).
# Это не настройка тенанта, а флаг текущего действия, поэтому живёт в
# thread-local и снимается сразу после выхода из блока: письма ставятся в
# очередь синхронно внутри `SM().apply`, то есть в том же потоке.
_mute = threading.local()


@contextmanager
def muted(*, customer: bool = False, owner: bool = False):
    """Не уведомлять указанные аудитории внутри блока (по умолчанию — уведомлять)."""
    prev = (getattr(_mute, "customer", False), getattr(_mute, "owner", False))
    _mute.customer, _mute.owner = bool(customer), bool(owner)
    try:
        yield
    finally:
        _mute.customer, _mute.owner = prev


def channel_enabled(tenant, audience: str, domain: str, event: str, channel: str) -> bool:
    """Включён ли `channel` для (`audience`, `domain`, `event`).

    `audience` ∈ {"customer","owner"}. Не настроено → True (текущее поведение).
    Owner — per-channel (не per-event): owner-письмо/пуш идёт на «created»-события.
    """
    if getattr(_mute, audience, False):  # DC-3: разовое «не уведомлять»
        return False
    cfg = _notify_cfg(tenant)
    if audience == "owner":
        owner = cfg.get("owner")
        if not isinstance(owner, dict):
            return True
        return bool(owner.get(channel, True))
    customer = cfg.get("customer")
    if not isinstance(customer, dict):
        return True
    ev = customer.get(f"{domain}:{event}")
    if not isinstance(ev, dict):
        return True
    return bool(ev.get(channel, True))


def customer_matrix(tenant) -> list[dict]:
    """Данные матрицы для настроек: по активным модулям — группы с событиями и
    текущим состоянием чекбоксов email/telegram. ``[{domain,label,rows:[{event,
    label,email,telegram}]}]``."""
    out = []
    for domain, events in CUSTOMER_EVENTS.items():
        module = DOMAIN_MODULE[domain]
        if not tenant.is_module_active(module):
            continue
        rows = [
            {
                "event": event,
                "label": label,
                "email": channel_enabled(tenant, "customer", domain, event, "email"),
                "telegram": channel_enabled(tenant, "customer", domain, event, "telegram"),
            }
            for event, label in events
        ]
        out.append({"domain": domain, "label": DOMAIN_LABEL[domain], "rows": rows})
    return out


def owner_channels(tenant) -> dict:
    """{email: bool, telegram: bool} для owner-уведомлений (дефолт — оба True)."""
    return {
        "email": channel_enabled(tenant, "owner", "", "", "email"),
        "telegram": channel_enabled(tenant, "owner", "", "", "telegram"),
    }
