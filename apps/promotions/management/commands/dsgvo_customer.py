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
from apps.promotions.tasks import _ANONYMIZED_NAME


def _export_payload(email: str) -> dict:
    customers = list(Customer.objects.filter(email__iexact=email))
    reservations = Reservation.objects.filter(customer__in=customers).select_related("promotion")
    waitlist = WaitlistEntry.objects.filter(email__iexact=email).select_related("promotion")

    from apps.notifications.models import Notification

    notifications = Notification.objects.filter(recipient__iexact=email)

    return {
        "email": email,
        "customers": [
            {
                "name": c.name,
                "email": c.email,
                "phone": c.phone,
                "note": c.note,
                "unsubscribed": c.unsubscribed,
                "created_at": c.created_at.isoformat(),
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
    }


def _erase(email: str) -> dict:
    from apps.notifications.models import Notification

    customers = list(Customer.objects.filter(email__iexact=email))

    active = Reservation.objects.filter(
        customer__in=customers, status__in=["pending", "confirmed"]
    ).count()
    if active:
        raise CommandError(
            f"У клиента {active} активных броней (pending/confirmed) — сначала "
            "выполнить или отменить их (Art. 17 (3): исполнение договора)."
        )

    with transaction.atomic():
        notes = Reservation.objects.filter(customer__in=customers).exclude(note="").update(note="")
        for c in customers:
            c.name = _ANONYMIZED_NAME
            c.email = ""
            c.phone = ""
            c.note = ""
            c.save(update_fields=["name", "email", "phone", "note", "updated_at"])
        waitlist, _ = WaitlistEntry.objects.filter(email__iexact=email).delete()
        recipients = Notification.objects.filter(recipient__iexact=email).update(recipient="")

    return {
        "customers_anonymized": len(customers),
        "reservation_notes_cleared": notes,
        "waitlist_deleted": waitlist,
        "notification_recipients_cleared": recipients,
    }


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
