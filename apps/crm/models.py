"""CRM-минимум (Track C3, TENANT): ведение клиентов как отдельный блок.

Клиент (promotions.Customer) не привязан к товару/заказу: бизнес заводит и
ведёт людей независимо от броней. Здесь — журнал заметок по клиенту; теги
живут полем Customer.tags. Лиды/воронки/канбан — полный CRM (vision Модуль 9),
следующий шаг.
"""

from django.db import models

from apps.core.models import TimestampedModel
from apps.promotions.models import Customer


class CustomerNote(TimestampedModel):
    customer = models.ForeignKey(Customer, on_delete=models.CASCADE, related_name="crm_notes")
    text = models.TextField()

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.customer}: {self.text[:40]}"
