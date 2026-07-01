"""UA4-1 (U-A): единый реестр секций детальной страницы — KEYS + подписи (LABELS)
в одном месте, для всех kind (товар/услуга/номер/событие).

Раньше KEYS жили в `apps/tenants/siteconfig.py`, а подписи для билдера — отдельно
в `apps/core/views.py` (`_EVENT_SECTION_LABELS`/`_PRODUCT_SECTION_LABELS`). Здесь они
сведены в ОДИН источник: инспектор билдера и (позже, UA4-2) data-driven рендер читают
его, а не два рассинхронных списка.

Границы (важно):
- Здесь ТОЛЬКО опциональные body/wide секции детали (описание/атрибуты/FAQ/инфо/
  отзывы/команда/amenities/похожие/тематические). Спец-секции (галерея/buy-box/buybar)
  НЕ здесь — они всегда присутствуют, живут в своих `{% block %}` и не управляются
  реестром (инвариант §6 плана).
- UA4-1 = только реестр/подписи (нулевое изменение вывода витрины). Data-driven цикл
  рендера — UA4-2. Обобщённый нормализатор `config['<module>_detail']` — Slice B (пока
  KEYS-нормализация остаётся в `siteconfig.py`, а реестр держит те же ключи + подписи).

`module` — ключ модуля витрины (`catalog`/`events`/`booking`/`stays`), совпадает с
источником в `apps.core.archetypes`. Порядок дескрипторов = дефолтный порядок рендера.
"""

from dataclasses import dataclass

from django.utils.translation import gettext_lazy as _


@dataclass(frozen=True)
class DetailSection:
    """Дескриптор одной секции детальной страницы (мета, не данные).

    `label` — ленивая i18n-строка (подпись в инспекторе билдера). `hideable` — можно
    ли скрыть через билдер; `orderable` — можно ли переупорядочить (сейчас только
    event; product/service/stay — hide-only, порядок фиксирован шаблоном)."""

    key: str
    label: object
    hideable: bool = True
    orderable: bool = False


# module → секции детальной в дефолтном порядке рендера. Ключи совпадают с
# `siteconfig.{EVENT,PRODUCT}_DETAIL_SECTION_KEYS` (Slice B сведёт и их к реестру).
DETAIL_SECTIONS: dict[str, tuple[DetailSection, ...]] = {
    "catalog": (
        DetailSection("description", _("Description")),
        DetailSection("info", _("Product info (origin/ingredients/allergens)")),
        DetailSection("reviews", _("Customer reviews")),
        DetailSection("related", _("Related products")),
    ),
    "events": tuple(
        DetailSection(key, label, hideable=True, orderable=True)
        for key, label in (
            ("for_whom", _("For whom")),
            ("idea", _("The idea")),
            ("includes", _("What's included")),
            ("program", _("Schedule")),
            ("venue", _("Venue")),
            ("accommodation", _("Accommodation")),
            ("food", _("Food")),
            ("hosts", _("Hosts")),
            ("price", _("Price")),
            ("bring", _("What to bring")),
            ("faq", _("FAQ")),
            ("testimonials", _("Testimonials")),
            ("before_after", _("Before & after")),
            ("certifications", _("Certifications")),
        )
    ),
}


def sections_for(module: str) -> tuple[DetailSection, ...]:
    """Дескрипторы секций модуля в дефолтном порядке (пустой кортеж — нет реестра)."""
    return DETAIL_SECTIONS.get(module, ())


def section_keys(module: str) -> tuple[str, ...]:
    """Ключи секций модуля в дефолтном порядке рендера."""
    return tuple(s.key for s in sections_for(module))


def section_labels(module: str) -> dict:
    """{key: lazy label} для инспектора билдера — единый источник подписей."""
    return {s.key: s.label for s in sections_for(module)}
