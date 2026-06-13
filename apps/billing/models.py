"""Биллинг — модели (SHARED, public). Пока одна: учёт выставленной Nutzungsgebühr.

Статус подписки живёт на Tenant (см. state_machine); здесь — журнал помесячной
платы за пользование системой (вариант B, P2.5-fee): по одной записи на
(tenant, период) — это и идемпотентность beat'а (месяц выставляется один раз),
и аудит-след того, что мы начислили продавцу.
"""

from django.db import models


class UsageFeeRecord(models.Model):
    tenant = models.ForeignKey(
        "tenants.Tenant", on_delete=models.CASCADE, related_name="usage_fees"
    )
    period = models.CharField(max_length=7)  # "YYYY-MM"
    gmv_cents = models.PositiveIntegerField(default=0)  # оборот за период (брутто)
    fee_percent = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    fee_cents = models.PositiveIntegerField(default=0)
    stripe_invoice_item_id = models.CharField(max_length=255, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-period"]
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "period"], name="usagefee_tenant_period_uniq"
            ),
        ]

    def __str__(self):
        return f"{self.tenant_id} {self.period}: {self.fee_cents}c"
