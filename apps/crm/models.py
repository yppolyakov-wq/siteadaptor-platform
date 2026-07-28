"""CRM-минимум (Track C3, TENANT): ведение клиентов как отдельный блок.

Клиент (promotions.Customer) не привязан к товару/заказу: бизнес заводит и
ведёт людей независимо от броней. Здесь — журнал заметок по клиенту; теги
живут полем Customer.tags. Лиды/воронки/канбан — полный CRM (vision Модуль 9),
следующий шаг.
"""

from django.core.validators import MaxValueValidator
from django.db import models

from apps.core.models import TimestampedModel
from apps.promotions.models import Customer


class Company(TimestampedModel):
    """CO-1 (PMS-корпоративный контур v1, одобрено владельцем): справочник
    компаний тенанта — реквизиты для счетов/привязки корпоративных гостей.
    Тарифы/безнал по компании — CO-3 (v2, план pms-corporate-competitor-plans)."""

    name = models.CharField(max_length=200)
    vat_id = models.CharField(max_length=40, blank=True)  # USt-IdNr
    street = models.CharField(max_length=200, blank=True)
    postal_code = models.CharField(max_length=20, blank=True)
    city = models.CharField(max_length=100, blank=True)
    email = models.EmailField(blank=True)
    phone = models.CharField(max_length=40, blank=True)
    note = models.TextField(blank=True)
    # Задел CO-3: скидка компании (пока только отображается в карточке).
    discount_percent = models.PositiveSmallIntegerField(
        default=0, validators=[MaxValueValidator(50)]
    )

    class Meta:
        ordering = ["name"]
        verbose_name_plural = "companies"

    def __str__(self):
        return self.name

    @property
    def invoice_recipient(self) -> str:
        """CO-2: многострочный получатель счёта из реквизитов."""
        lines = [self.name]
        if self.street:
            lines.append(self.street)
        if self.postal_code or self.city:
            lines.append(f"{self.postal_code} {self.city}".strip())
        if self.vat_id:
            lines.append(f"USt-IdNr: {self.vat_id}")
        return "\n".join(lines)


class CustomerNote(TimestampedModel):
    customer = models.ForeignKey(Customer, on_delete=models.CASCADE, related_name="crm_notes")
    text = models.TextField()

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.customer}: {self.text[:40]}"
