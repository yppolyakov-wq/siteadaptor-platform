"""Витринная презентация архетипов (S2) — слой между реестром и шаблонами.

Сводит «лица» активных архетипов из реестра модулей
(`apps.core.modules.storefront_archetypes`) с пер-тенантными оверрайдами из
`site_config["archetypes"]` (заголовок/описание/скрытие). Результат — готовые
карточки для секции «Наши разделы» на главной и (далее, S7) для меню.
"""

from apps.core import modules

from . import siteconfig


def archetype_teasers(tenant) -> list[dict]:
    """Карточки тизеров активных архетипов для секции «Наши разделы».

    Только архетипы с `storefront_teaser=True`, не скрытые владельцем; заголовок
    и описание — оверрайд владельца или дефолт из реестра. `url_name` резолвит
    шаблон ({% url %}), не хелпер.
    """
    overrides = siteconfig.normalize(tenant.site_config).get("archetypes", {})
    teasers = []
    for arch in modules.storefront_archetypes(tenant):
        if not arch.teaser:
            continue
        ov = overrides.get(arch.key, {})
        if ov.get("hidden"):
            continue
        teasers.append(
            {
                "key": arch.key,
                "label": ov.get("label") or arch.label,
                "blurb": ov.get("blurb") or arch.blurb,
                "icon": arch.icon,
                "url_name": arch.url_name,
            }
        )
    return teasers


def cover_specs(tenant) -> list[dict]:
    """Обложки разделов (S3) — на каждый активный архетип с публичной страницей:
    интро-текст и hero-фото (поверх его лендинга). Для формы кабинета «Bereiche»."""
    overrides = siteconfig.normalize(tenant.site_config).get("archetypes", {})
    specs = []
    for arch in modules.storefront_archetypes(tenant):
        ov = overrides.get(arch.key, {})
        specs.append(
            {
                "key": arch.key,
                "label": arch.label,
                "icon": arch.icon,
                "intro": ov.get("intro", ""),
                "hero_image": ov.get("hero_image", ""),
            }
        )
    return specs


def teaser_specs(tenant) -> list[dict]:
    """Все тизер-способные активные архетипы + текущий оверрайд — для формы
    кабинета (`/dashboard/site/`): владелец правит заголовок/описание/видимость.
    Возвращаем даже скрытые (чтобы был чекбокс «показывать»)."""
    overrides = siteconfig.normalize(tenant.site_config).get("archetypes", {})
    specs = []
    for arch in modules.storefront_archetypes(tenant):
        if not arch.teaser:
            continue
        ov = overrides.get(arch.key, {})
        specs.append(
            {
                "key": arch.key,
                "default_label": arch.label,
                "default_blurb": arch.blurb,
                "icon": arch.icon,
                "label": ov.get("label", ""),
                "blurb": ov.get("blurb", ""),
                "visible": not ov.get("hidden"),
            }
        )
    return specs
