# Pattern: Soft Delete (мягкое удаление)

Статус: Phase 1, Sprint 1 (mixin), применяется к Product/Promotion/Customer/Reservation.
Ссылается из: `phase1-plan-additions.md` §1.3.

## Зачем

Жёсткий `DELETE` теряет историю, рвёт FK и ломает audit/аналитику. Для
бизнес-сущностей используем флаг `deleted_at`: запись «исчезает» из обычных
выборок, но остаётся в БД для восстановления, отчётов и ссылочной целостности.

## Mixin + менеджеры

```python
# apps/core/models.py
from django.db import models
from django.utils import timezone


class TimestampedModel(models.Model):
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


class SoftDeleteQuerySet(models.QuerySet):
    def alive(self):
        return self.filter(deleted_at__isnull=True)

    def dead(self):
        return self.filter(deleted_at__isnull=False)

    def delete(self):  # bulk soft-delete
        return self.update(deleted_at=timezone.now())

    def hard_delete(self):
        return super().delete()


class AliveManager(models.Manager):
    """Менеджер по умолчанию: отдаёт только не удалённые."""
    def get_queryset(self):
        return SoftDeleteQuerySet(self.model, using=self._db).alive()


class SoftDeleteMixin(TimestampedModel):
    deleted_at = models.DateTimeField(null=True, blank=True, db_index=True)

    # ВАЖНО: первый менеджер = default. objects скрывает удалённые,
    # all_objects видит всё (для админки/восстановления).
    objects = AliveManager()
    all_objects = SoftDeleteQuerySet.as_manager()

    class Meta:
        abstract = True

    def delete(self, using=None, keep_parents=False):
        self.deleted_at = timezone.now()
        self.save(update_fields=["deleted_at", "updated_at"])

    def hard_delete(self, using=None, keep_parents=False):
        super().delete(using=using, keep_parents=keep_parents)

    def restore(self):
        self.deleted_at = None
        self.save(update_fields=["deleted_at", "updated_at"])

    @property
    def is_deleted(self) -> bool:
        return self.deleted_at is not None
```

## Использование

```python
class Product(SoftDeleteMixin):
    name = models.JSONField(default=dict)
    ...

Product.objects.all()          # только живые
Product.all_objects.all()      # включая удалённые
Product.all_objects.dead()     # корзина
product.delete()               # soft
product.restore()              # вернуть
product.hard_delete()          # физически (GDPR-стирание)
```

## Подводные камни

- **`unique` ломается с soft-delete.** Удалённая запись всё ещё занимает
  уникальное значение (slug, email). Решение — частичный уникальный индекс
  только по живым строкам:

  ```python
  class Meta:
      constraints = [
          models.UniqueConstraint(
              fields=["slug"], condition=models.Q(deleted_at__isnull=True),
              name="uniq_product_slug_alive",
          )
      ]
  ```

- **FK на soft-deleted родителя.** `on_delete` Django не сработает при soft —
  каскад надо обрабатывать вручную в `delete()` (например, удаляя дочерние
  резервы) либо полагаться на фильтрацию `objects` в выборках.
- **Default-менеджер.** Первый объявленный менеджер используется в related-
  доступе и Admin по умолчанию. `objects = AliveManager()` объявляем первым.
  В Admin для корзины подключаем `all_objects` через кастомный `get_queryset`.
- **GDPR.** «Право на забвение» = `hard_delete()` или анонимизация PII-полей,
  не просто `deleted_at`.

## Чек-лист

- [ ] `SoftDeleteMixin` применён к Product/Promotion/Customer/Reservation.
- [ ] `objects` (живые) объявлен первым; есть `all_objects`.
- [ ] Уникальные поля — partial unique constraint по `deleted_at IS NULL`.
- [ ] Каскад на дочерние сущности обработан явно.
- [ ] Для GDPR есть путь `hard_delete()`/анонимизации.
