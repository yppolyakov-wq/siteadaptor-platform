"""UD4-2: настройки каналов уведомлений (email ∥ Telegram) per-событие.

Хранение — `Tenant.site_config["notify"]` (без миграции, прецедент
`low_stock_threshold`). Семантика по умолчанию = ТЕКУЩЕЕ поведение: ничего не
настроено → все каналы включены (email + Telegram шлются как раньше). Настроил
владелец → уважаем. Telegram к клиенту всё равно уходит только при привязке
(`TelegramLink.chat_id`), к владельцу — только при привязке owner_chat_id.

Резолвер `channel_enabled(tenant, audience, domain, event, channel)` зовут
доменные `enqueue_*`-функции ПЕРЕД отправкой каждого канала.
"""

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
}

# Домен → ключ модуля (гейтинг строк матрицы по активным модулям бизнеса).
DOMAIN_MODULE = {
    "order": "orders",
    "booking": "booking",
    "stay": "stays",
    "ticket": "events",
    "job": "jobs",
    "reservation": "promotions",
}

# Домен → короткая DE-подпись группы (для матрицы).
DOMAIN_LABEL = {
    "order": _("Bestellungen"),
    "booking": _("Termine"),
    "stay": _("Übernachtungen"),
    "ticket": _("Tickets"),
    "job": _("Aufträge"),
    "reservation": _("Reservierungen"),
}


def _notify_cfg(tenant) -> dict:
    cfg = getattr(tenant, "site_config", None)
    if not isinstance(cfg, dict):
        return {}
    node = cfg.get("notify")
    return node if isinstance(node, dict) else {}


def channel_enabled(tenant, audience: str, domain: str, event: str, channel: str) -> bool:
    """Включён ли `channel` для (`audience`, `domain`, `event`).

    `audience` ∈ {"customer","owner"}. Не настроено → True (текущее поведение).
    Owner — per-channel (не per-event): owner-письмо/пуш идёт на «created»-события.
    """
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
