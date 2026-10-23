"""KA-12 E6.1: запрос клиента по DSGVO — выгрузка (Art. 15/20) и удаление (Art. 17).

Одна реализация для кабинета владельца, ЛК клиента и CLI `dsgvo_customer`.

Выгрузка обходит ВСЕ модели, ссылающиеся на клиента (`Customer._meta.related_objects`),
плюс копии по e-mail (отзывы, подарочные ваучеры, листы ожидания, лог уведомлений).
Удаление идёт по `ERASURE_POLICY`: у каждой связанной модели — своё правило. Замок
покрытия требует, чтобы новая модель с FK на клиента попала в политику, иначе CI красный.

Что сохраняется по закону — не молча, а с основанием (`KEPT_REASONS`, README выгрузки):
суммы сделок и счета (GoBD/HGB § 257, 10 лет), Meldeschein (§ 30 BMG, 1 год),
подписанный отказ участника (срок исковой давности).
"""

from __future__ import annotations

import datetime
import decimal
import json
import uuid

from django.db import transaction
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

ANONYMIZED_NAME = "—"

# Модели с FK на клиента → правило удаления.
#   anonymize — строка клиента остаётся (на неё ссылаются сделки), PII затирается
#   delete    — удалить строки
#   clear     — затереть перечисленные поля, строку оставить (суммы — по закону)
#   author    — автор поста/комментария: имя «—», ссылка на клиента снимается
#   purge     — документ: удалить запись И зашифрованный файл
#   keep      — оставить без изменений (основание в KEPT_REASONS)
ERASURE_POLICY = {
    "promotions.Reservation": ("clear", ("note",)),
    "loyalty.Voucher": ("keep", "money"),
    "loyalty.LoyaltyCard": ("delete", ()),
    "crm.CustomerNote": ("delete", ()),
    "orders.Order": ("clear", ("note", "shipping_address")),
    "orders.Offer": ("clear", ("customer_name", "customer_email", "note")),
    "booking.Pass": ("keep", "money"),
    "booking.Booking": ("clear", ("note",)),
    "finance.RevenueEntry": ("keep", "money"),
    "finance.Invoice": ("keep", "invoice"),
    "stays.StayBooking": ("clear", ("note",)),
    "jobs.Job": ("clear", ("site_address",)),
    "inbox.Conversation": ("delete", ()),
    "telegram.TelegramLink": ("delete", ()),
    "events.Ticket": ("clear", ("note", "answers")),
    "documents.SecureDocument": ("purge", ()),
    "community.FeedPost": ("author", ()),
    "community.FeedComment": ("author", ()),
}

# Дочерние строки, которые входят в выгрузку вместе с родителем.
CHILDREN = {
    "orders.Order": ("items",),
    "orders.Offer": ("lines",),
    "jobs.Job": ("lines",),
    "inbox.Conversation": ("messages",),
    "stays.StayBooking": ("registration",),
    "events.Ticket": ("waiver",),
}

# Поля, которые в выгрузку НЕ идут или идут маской (секреты/служебное).
MASKED = {"doc_number", "signed_ip", "public_token", "token", "path"}
SKIPPED = {"stripe_payment_intent", "external_ref"}

KEPT_REASONS = {
    "money": _(
        "Umsätze bleiben 10 Jahre gespeichert (GoBD, § 147 AO, § 257 HGB); "
        "Kontaktdaten werden entfernt."
    ),
    "invoice": _(
        "Ausgestellte Rechnungen bleiben 10 Jahre unverändert (GoBD, § 147 AO); "
        "der Empfänger auf der Rechnung kann nicht geändert werden."
    ),
    "registration": _(
        "Meldescheine bleiben 1 Jahr gespeichert (§ 30 BMG) und werden dann gelöscht."
    ),
    "waiver": _("Unterschriebene Haftungsverzichte bleiben bis zum Ende der Verjährungsfrist."),
}


class ErasureBlocked(Exception):
    """У клиента есть живая сделка — удалять нельзя (Art. 17 (3) b: исполнение договора)."""

    def __init__(self, reasons):
        super().__init__("; ".join(str(r) for r in reasons))
        self.reasons = reasons


def _value(value):
    if isinstance(value, datetime.datetime | datetime.date | datetime.time):
        return value.isoformat()
    if isinstance(value, decimal.Decimal | uuid.UUID):
        return str(value)
    if isinstance(value, bytes):
        return None
    return value


def _row(obj) -> dict:
    data = {}
    for field in obj._meta.concrete_fields:
        name = field.name
        if name in SKIPPED:
            continue
        if field.is_relation:
            target = getattr(obj, field.attname, None)
            data[name] = str(target) if target is not None else None
            continue
        raw = getattr(obj, field.attname, None)
        if name in MASKED:
            data[name] = "***" if raw else ""
            continue
        data[name] = _value(raw)
    return data


def _children(obj, label) -> dict:
    out = {}
    for accessor in CHILDREN.get(label, ()):
        try:
            related = getattr(obj, accessor)
        except Exception:  # noqa: BLE001 — one-to-one без строки
            continue
        if hasattr(related, "all"):
            out[accessor] = [_row(child) for child in related.all()]
        elif related is not None:
            out[accessor] = _row(related)
    return out


def _related_specs():
    from apps.promotions.models import Customer

    for rel in Customer._meta.related_objects:
        yield rel.related_model._meta.label, rel.related_model, rel.field.name


def _email_linked(email):
    """Копии по e-mail (без FK). Сопоставление ТОЛЬКО по e-mail, никогда по имени."""
    if not email:
        return {}
    from django.apps import apps as django_apps

    specs = {
        "reviews.Review": "email",
        "loyalty.GiftVoucher": "buyer_email",
        "promotions.WaitlistEntry": "email",
        "events.EventWaitlistEntry": "email",
        "notifications.Notification": "recipient",
    }
    out = {}
    for label, field in specs.items():
        try:
            model = django_apps.get_model(label)
        except LookupError:
            continue
        out[label] = model.objects.filter(**{f"{field}__iexact": email})
    return out


def export_customer(customer) -> dict:
    """Все данные клиента в этой схеме (Art. 15/20): машиночитаемый dict."""
    sections = {}
    for label, model, field in _related_specs():
        rows = []
        for obj in model.objects.filter(**{field: customer}):
            row = _row(obj)
            row.update(_children(obj, label))
            rows.append(row)
        if rows:
            sections[label] = rows
    for label, qs in _email_linked(customer.email).items():
        rows = [_row(obj) for obj in qs]
        if rows:
            sections.setdefault(label, []).extend(rows)
    return {
        "exported_at": timezone.now().isoformat(),
        "customer": _row(customer),
        "data": sections,
        "kept": {key: str(text) for key, text in KEPT_REASONS.items()},
    }


def export_json(customer) -> str:
    return json.dumps(export_customer(customer), ensure_ascii=False, indent=2, default=str)


def erasure_blockers(customer, tenant=None) -> list:
    """Почему сейчас удалять нельзя (пусто — можно)."""
    from apps.promotions.models import Customer
    from apps.promotions.tasks import open_deal_q

    blocked = Customer.objects.filter(pk=customer.pk).filter(open_deal_q(tenant)).exists()
    if not blocked:
        return []
    return [
        _(
            "Der Kunde hat noch eine offene Bestellung, Buchung, ein offenes Angebot oder "
            "eine unbezahlte Rechnung. Bitte zuerst abschließen oder stornieren."
        )
    ]


def _anonymize_customer(customer):
    customer.name = ANONYMIZED_NAME
    customer.email = ""
    customer.phone = ""
    customer.note = ""
    customer.tags = []
    customer.birthday = None
    customer.marketing_opt_in = False
    customer.save(
        update_fields=[
            "name",
            "email",
            "phone",
            "note",
            "tags",
            "birthday",
            "marketing_opt_in",
            "updated_at",
        ]
    )


def _clear_value(field):
    if field.null:
        return None
    if field.get_internal_type() == "JSONField":
        return field.default() if callable(field.default) else {}
    return ""


def erase_customer(customer, tenant=None) -> dict:
    """Art. 17: стереть персональные данные клиента по политике. Всё или ничего.

    → статистика (только числа — без персональных данных)."""
    from apps.promotions.models import Customer

    blockers = erasure_blockers(customer, tenant)
    if blockers:
        raise ErasureBlocked(blockers)

    email = customer.email
    stats: dict[str, int] = {}
    documents = []
    chats: list[str] = []
    with transaction.atomic():
        customer = Customer.objects.select_for_update().get(pk=customer.pk)
        for label, model, field in _related_specs():
            action, arg = ERASURE_POLICY[label]
            qs = model.objects.filter(**{field: customer})
            if action == "delete":
                if label == "telegram.TelegramLink":
                    chats = [c for c in qs.values_list("chat_id", flat=True) if c]
                count, _detail = qs.delete()
            elif action == "clear":
                fields = {name: _clear_value(model._meta.get_field(name)) for name in arg}
                count = qs.update(**fields)
            elif action == "author":
                count = qs.update(author_name=ANONYMIZED_NAME, author_customer=None)
            elif action == "purge":
                documents = list(qs)
                count = len(documents)
            else:
                count = 0
            stats[label] = count
        stats.update(_erase_email_linked(email, chats))
        _anonymize_customer(customer)
        if documents:
            from apps.documents import services as document_services

            # Файл удаляется после фиксации: потерянный файл лучше потерянной записи.
            transaction.on_commit(lambda: [document_services.purge(d) for d in documents])
    return stats


def _erase_email_linked(email, chats) -> dict:
    stats = {}
    linked = _email_linked(email)
    for label, qs in linked.items():
        if label == "reviews.Review":
            stats[label] = qs.update(author_name=ANONYMIZED_NAME, email="")
        elif label == "loyalty.GiftVoucher":
            stats[label] = qs.update(buyer_name=ANONYMIZED_NAME, buyer_email="", recipient_name="")
        elif label == "notifications.Notification":
            stats[label] = qs.update(recipient="")
        else:
            stats[label], _detail = qs.delete()
    if chats:
        from apps.notifications.models import Notification

        stats["notifications.chat"] = Notification.objects.filter(recipient__in=chats).update(
            recipient=""
        )
    return stats
