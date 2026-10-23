"""DSGVO-запросы клиента: экспорт (Art. 15/20) и удаление (Art. 17) по email.

Авто-retention обезличивает контакты по сроку (tasks.purge_reservation_pii);
эта команда — для явного запроса клиента владельцу бизнеса:

    python manage.py dsgvo_customer --schema <tenant> --email kunde@mail.de            # экспорт JSON
    python manage.py dsgvo_customer --schema <tenant> --email kunde@mail.de --delete   # стереть PII

Экспорт пишет JSON в stdout (передать клиенту). Удаление обезличивает Customer
(строка остаётся для агрегатной статистики, как в retention-очистке), стирает
note у его броней, удаляет записи waitlist и затирает адресата в логе
уведомлений. При активных бронях (pending/confirmed) — отказ: сначала
выполнить/отменить бронь (Art. 17 (3) — исполнение договора).
"""

import json

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django_tenants.utils import get_tenant_model, schema_context

from apps.promotions.models import Customer, Reservation, WaitlistEntry


def _customers(email: str, customer=None) -> list:
    """Клиенты по e-mail + (T-8.30l) клиент из сессии ЛК — у входа через Telegram
    e-mail может не быть, права Art. 15/17 у него те же."""
    found = list(Customer.objects.filter(email__iexact=email)) if email else []
    if customer is not None and all(c.pk != customer.pk for c in found):
        found.append(customer)
    return found


def _export_payload(email: str, customer=None) -> dict:
    customers = _customers(email, customer)
    reservations = Reservation.objects.filter(customer__in=customers).select_related("promotion")
    waitlist = (
        WaitlistEntry.objects.filter(email__iexact=email).select_related("promotion")
        if email
        else WaitlistEntry.objects.none()
    )

    from apps.notifications.models import Notification

    notifications = (
        Notification.objects.filter(recipient__iexact=email)
        if email
        else Notification.objects.none()
    )

    return {
        "email": email,
        "customers": [
            {
                "name": c.name,
                "email": c.email,
                "phone": c.phone,
                "note": c.note,
                "tags": c.tags,
                "marketing_opt_in": c.marketing_opt_in,
                "created_source": c.created_source,
                "unsubscribed": c.unsubscribed,
                "created_at": c.created_at.isoformat(),
                "telegram_chat_id": getattr(getattr(c, "telegram_link", None), "chat_id", ""),
                "loyalty_cards": [
                    {
                        "program": str(card.program),
                        "stamps": card.stamps,
                        "rewards_earned": card.rewards_earned,
                    }
                    for card in c.loyalty_cards.select_related("program")
                ],
            }
            for c in customers
        ],
        "reservations": [
            {
                "promotion": r.promotion.title_text,
                "reference_code": r.reference_code,
                "quantity": r.quantity,
                "status": r.status,
                "note": r.note,
                "created_at": r.created_at.isoformat(),
            }
            for r in reservations
        ],
        "waitlist": [
            {
                "promotion": w.promotion.title_text,
                "name": w.name,
                "created_at": w.created_at.isoformat(),
            }
            for w in waitlist
        ],
        "notifications": [
            {"type": n.type, "status": n.status, "created_at": n.created_at.isoformat()}
            for n in notifications
        ],
        "crm_notes": [
            {"text": n.text, "created_at": n.created_at.isoformat()}
            for c in customers
            for n in c.crm_notes.all()
        ],
        # KA-12 E6.1: полная выгрузка по всем сделкам (заказы, брони, билеты, заявки,
        # предложения, счета, переписка) — та же, что у кнопки владельца.
        "full": [_full_export(c) for c in customers],
    }


def _full_export(customer) -> dict:
    from apps.crm import dsgvo

    return json.loads(dsgvo.export_json(customer))


def _erase(email: str, customer=None) -> dict:
    """Art. 17 — общая реализация `apps.crm.dsgvo` (KA-12 E6.1): та же политика, что у
    кнопки владельца; живая сделка любого вида блокирует удаление."""
    from apps.crm import dsgvo

    customers = _customers(email, customer)
    for c in customers:
        blockers = dsgvo.erasure_blockers(c)
        if blockers:
            raise CommandError(" ".join(str(b) for b in blockers))

    stats: dict = {"customers_anonymized": len(customers)}
    with transaction.atomic():
        for c in customers:
            for key, value in dsgvo.erase_customer(c).items():
                stats[key] = stats.get(key, 0) + value
        # e-mail без карточки клиента (только лист ожидания / уведомления)
        if email and not customers:
            for key, value in dsgvo._erase_email_linked(email, []).items():
                stats[key] = stats.get(key, 0) + value
    return stats


class Command(BaseCommand):
    help = "DSGVO: экспорт (по умолчанию) или удаление (--delete) данных клиента по email."

    def add_arguments(self, parser):
        parser.add_argument("--schema", required=True, help="Схема тенанта")
        parser.add_argument("--email", required=True)
        parser.add_argument("--delete", action="store_true", help="Стереть PII вместо экспорта")

    def handle(self, *args, **options):
        schema = options["schema"]
        email = options["email"].strip().lower()
        if not get_tenant_model().objects.filter(schema_name=schema).exists():
            raise CommandError(f"Схема {schema!r} не найдена")

        with schema_context(schema):
            has_customer = Customer.objects.filter(email__iexact=email).exists()
            has_waitlist = WaitlistEntry.objects.filter(email__iexact=email).exists()
            if not (has_customer or has_waitlist):
                raise CommandError(f"Данных по {email} в схеме {schema} не найдено")

            if options["delete"]:
                stats = _erase(email)
                self.stdout.write(self.style.SUCCESS(f"PII удалены: {stats}"))
            else:
                payload = _export_payload(email)
                self.stdout.write(json.dumps(payload, ensure_ascii=False, indent=2))
