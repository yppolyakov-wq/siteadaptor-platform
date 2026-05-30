"""Каталог: Category и Product (TENANT-схема).

Спецификация: phase1-implementation-guide.md, Часть 2 + дополнения:
- soft-delete (доп. 1.3) — patterns/soft-delete.md
- FileRef-envelope для images (доп. 2.2)
- i18n JSONField + metadata на runtime-моделях
"""

from django.db import models

from apps.core.models import I18nMixin, SoftDeleteMixin


class Category(SoftDeleteMixin, I18nMixin):
    parent = models.ForeignKey(
        "self",
        null=True,
        blank=True,
        related_name="children",
        on_delete=models.SET_NULL,
    )
    name = models.JSONField(default=dict)  # {"de": "...", "en": "..."}
    slug = models.SlugField(max_length=100)
    icon = models.CharField(max_length=50, blank=True)
    sort_order = models.IntegerField(default=0)
    is_active = models.BooleanField(default=True)

    class Meta:
        verbose_name_plural = "Categories"
        ordering = ["sort_order", "slug"]
        constraints = [
            # slug уникален среди живых записей (soft-delete не должен мешать
            # переиспользовать slug; см. patterns/soft-delete.md).
            models.UniqueConstraint(
                fields=["slug"],
                condition=models.Q(deleted_at__isnull=True),
                name="uniq_category_slug_alive",
            )
        ]

    def __str__(self):
        return self.get_i18n("name") or self.slug


class Product(SoftDeleteMixin, I18nMixin):
    sku = models.CharField(max_length=100, blank=True, db_index=True)
    name = models.JSONField(default=dict)
    description = models.JSONField(default=dict)

    category = models.ForeignKey(
        Category,
        null=True,
        blank=True,
        related_name="products",
        on_delete=models.SET_NULL,
    )

    # FileRef-envelope (доп. 2.2): список dict'ов
    # [{"id","url","alt":{de,en},"mime_type","size","is_primary","sort_order"}]
    images = models.JSONField(default=list, blank=True)

    base_price = models.DecimalField(max_digits=10, decimal_places=2)
    currency = models.CharField(max_length=3, default="EUR")

    stock_quantity = models.IntegerField(null=True, blank=True)

    is_active = models.BooleanField(default=True)
    is_featured = models.BooleanField(default=False)

    metadata = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["is_active"], name="product_active_idx"),
            models.Index(fields=["category"], name="product_category_idx"),
            models.Index(fields=["sku"], name="product_sku_idx"),
        ]

    def __str__(self):
        return self.get_i18n("name") or self.sku or str(self.pk)

    @property
    def primary_image(self) -> dict | None:
        imgs = self.images or []
        for img in imgs:
            if img.get("is_primary"):
                return img
        return imgs[0] if imgs else None
