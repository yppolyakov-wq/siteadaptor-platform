"""SF-2: провайдер листинга акций /aktionen/ — системные фильтры + поиск + сорт.

До SF-2 вьюха читала из GET только ?gruppe= (группы владельца); системных
фильтров у витрины акций не было вовсе. Данные в модели давно есть (ends_at /
discount_percent / promo_type), не хватало фильтрующего слоя U-B.

Особенность против остальных провайдеров: реальная скидка акции живёт НЕ в БД
(discount_percent | price_override/compare_at_price | base_price товара —
свойства new_price/discount_percent_display), поэтому фильтр «−N %+» и все
сортировки — in-memory (callable-вариант sort_keys, паттерн events). Листинг
акций не пагинируется — материализация списка тут штатная, keyset не нужен.
"""

from datetime import timedelta

from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from apps.core.facets import FacetProvider, i18n_icontains_q

from . import promo_types

#: пресеты чипа «минимальная скидка» (валидация ?rabatt=)
DISCOUNT_PRESETS = (20, 30, 50)

#: LB-4d «Gilt für» (?ziel=): цель акции волны PL → её FK. Ключи — те же, что у
#: `siteconfig.LIST_PROMO_TARGETS`; одна точка истины для блока «Liste», секции
#: главной, «Ending soon» и /aktionen/.
TARGET_FIELDS = {"product": "product", "service": "service", "stay": "stay_unit", "combo": "combo"}


def apply_target(items, target: str):
    """Акции с целью `target` (товар/услуга/номер/набор); пустая/неизвестная — все."""
    field = TARGET_FIELDS.get(target or "")
    return items.filter(**{f"{field}__isnull": False}) if field else items


def _pct(promo) -> int:
    return int(promo.discount_percent_display or 0)


def _ends_key(promo):
    # бессрочные — в конец; кортеж не сравнивает даты разных веток
    return (promo.ends_at is None, promo.ends_at or promo.created_at)


def _price_key(promo):
    p = promo.new_price
    return (p is None, p if p is not None else 0)


class PromoFacets(FacetProvider):
    kind = "promotion"

    def selected(self, params) -> dict:
        """Валидные значения из GET: группа владельца + три системных фильтра."""
        endet = (params.get("endet") or "").strip()
        try:
            rabatt = int(params.get("rabatt") or 0)
        except (TypeError, ValueError):
            rabatt = 0
        ziel = (params.get("ziel") or "").strip()
        return {
            "gruppe": (params.get("gruppe") or "").strip(),
            "endet": endet if endet in ("heute", "woche") else "",
            "rabatt": rabatt if rabatt in DISCOUNT_PRESETS else 0,
            "reservierbar": params.get("reservierbar") == "1",
            "ziel": ziel if ziel in TARGET_FIELDS else "",
        }

    def apply(self, items, params):
        """QuerySet-фильтры первыми (группа/срок/тип), «−N %+» — последним и
        in-memory: процент считается свойством из цен (в БД его нет)."""
        sel = self.selected(params)
        if sel["gruppe"]:
            # PT-1: один параметр на всю ось «тип акции» — своя рубрика владельца
            # фильтрует по `group`, встроенный тип (`sys:*`) — своим Q из реестра.
            items = promo_types.apply_type(items, sel["gruppe"])
        if sel["reservierbar"]:
            items = items.filter(promo_type="reservation")
        if sel["ziel"]:
            items = apply_target(items, sel["ziel"])
        if sel["endet"]:
            now = timezone.now()
            local = timezone.localtime(now)
            if sel["endet"] == "heute":
                end = local.replace(hour=23, minute=59, second=59, microsecond=0)
            else:
                end = local + timedelta(days=7)
            items = items.filter(ends_at__gt=now, ends_at__lte=end)
        if sel["rabatt"]:
            items = [p for p in items if _pct(p) >= sel["rabatt"]]
        return items

    def search(self, items, q: str):
        """?q= по названию/описанию (JSON-i18n по всем локалям) и группе.

        Звать ДО apply: фильтр «−N %+» материализует список, а Q-поиск —
        только по QuerySet."""
        if not q:
            return items
        return items.filter(
            i18n_icontains_q(
                q, flat_fields=("group",), json_fields=("title", "description", "group_i18n")
            )
        )

    def sort_keys(self) -> dict:
        # только callables: после «−N %+» items может быть списком — единый
        # in-memory путь (база сортирует sorted()), строковых order_by нет.
        return {
            "endet": (_ends_key, False),
            "rabatt": (_pct, True),
            "preis": (_price_key, False),
        }

    def sort_options(self) -> list:
        return [
            ("", _("Newest")),
            ("endet", _("Ending soon")),
            ("rabatt", _("Discount")),
            ("preis", _("Price: low to high")),
        ]
