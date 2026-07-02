"""UB3-2 (решение владельца B-3): M2M-коллекции — группировка услуг/номеров на витрине.

Зачем: у листингов `booking.Service` (A3/A7/A9) и `stays.StayUnit` (A5) нет
категорий; коллекция — подборка владельца («Damen», «Mit Seeblick»), одна
сущность может входить в несколько. Модель НАМЕРЕННО плоская (без иерархии —
self-FK остаётся только у catalog.Category) и без пер-архетипного scope: чипы
на листинге услуг показывают только коллекции с активными услугами, на листинге
номеров — с номерами (present-values фасета из QuerySet).

Связи — M2M-поля на самих сущностях (`Service.collections`,
`StayUnit.collections`), чтобы читались естественно и не требовали generic-джанкшена.
"""

from django.db import models

from apps.core.models import I18nMixin, TimestampedModel


class Collection(I18nMixin, TimestampedModel):
    """Подборка продаваемых сущностей (per-tenant, TENANT-схема).

    i18n — по L3-паттерну «база + оверлей»: базовая локаль в плоских
    `name`/`description`, переводы неосновных локалей — в `*_i18n` (реестр DE+EN,
    решение S-3). `slug` — стабильный идентификатор для URL-фасета `?kollektion=`."""

    name = models.CharField(max_length=120)
    name_i18n = models.JSONField(default=dict, blank=True)
    slug = models.SlugField(max_length=140, unique=True)
    description = models.TextField(blank=True)
    description_i18n = models.JSONField(default=dict, blank=True)
    sort_order = models.PositiveSmallIntegerField(default=0)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["sort_order", "name"]

    def __str__(self):
        return self.name

    def name_localized(self, locale=None) -> str:
        """Имя подборки на запрошенной локали (чип фасета на витрине)."""
        return self.get_overlay("name", "name_i18n", locale)

    def description_localized(self, locale=None) -> str:
        """Описание подборки на локали (интро секции при будущей группировке)."""
        return self.get_overlay("description", "description_i18n", locale)
