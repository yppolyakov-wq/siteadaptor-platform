"""STU-3: охват настройки — «для всех» или «только здесь» (вариант A владельца).

Данные платформы трёхуровневые с волн DL-19/20/21: значение берётся у самого объекта,
иначе — общий дефолт сайта, иначе — прежний вид. Но объектный уровень правился ТОЛЬКО
в формах кабинета: чтобы задать шаблон одной категории, владелец уходил из редактора в
список категорий и обратно. Здесь этот уровень появляется в самой Студии — рядом с
общей настройкой, пилюлей «для всех / только здесь».

Запись НЕ идёт через большую форму билдера. Форма пересобирает `site_config` целиком,
и подмешивать в неё поля чужих моделей значило бы, что промах в любом контроле трогает
товар или категорию. Поэтому здесь точечные чтение и запись ОДНОГО поля ОДНОГО объекта
(прецедент targeted-write: SEO, Finder, настройки доски).

Значения валидируются теми же реестрами, что и рендер витрины: неизвестный код —
отказ, а не «сохранили мусор, витрина молча показала дефолт».
"""

from __future__ import annotations

from dataclasses import dataclass

from apps.core import studio_pages


class ScopeError(ValueError):
    """Запрос не описывает существующую пару «объект + настройка»."""


@dataclass(frozen=True)
class ScopeState:
    """Что показать у пилюли охвата."""

    setting: str
    site_value: str
    own_value: str

    @property
    def overridden(self) -> bool:
        return bool(self.own_value)


def _valid_values(setting: studio_pages.Setting) -> frozenset[str]:
    """Допустимые коды объектного уровня — из тех же реестров, что и витрина."""
    from apps.catalog import category_styles
    from apps.core import card_forms
    from apps.promotions import group_styles

    kind = setting.object_kind
    if kind == studio_pages.OBJECT_CATEGORY:
        return category_styles.VALID_PAGE_STYLES
    if kind == studio_pages.OBJECT_PRODUCT:
        return card_forms.keys_for(card_forms.PRODUCT)
    if kind == studio_pages.OBJECT_PROMOTION:
        return card_forms.keys_for(card_forms.PROMO)
    if kind == studio_pages.OBJECT_PROMO_GROUP:
        return group_styles.VALID_GROUP_STYLES
    raise ScopeError(f"нет объектного уровня у настройки {setting.code}")


def _site_value(tenant, setting: studio_pages.Setting) -> str:
    """Значение уровня «для всех» — чтобы пилюля честно писала, что наследуется."""
    from apps.tenants import siteconfig

    node = siteconfig.normalize(tenant.site_config or {})
    for part in setting.site_key:
        if not isinstance(node, dict) or part not in node:
            return ""
        node = node[part]
    return node if isinstance(node, str) else ""


def _fetch(setting: studio_pages.Setting, ref: str):
    """Объект по ссылке из адреса канвы. Группа акций модели не имеет — None."""
    kind = setting.object_kind
    ref = (ref or "").strip()
    if not ref:
        raise ScopeError("страница канвы не указывает объект")

    if kind == studio_pages.OBJECT_PROMO_GROUP:
        return None  # хранение — в site_config, ниже

    if kind == studio_pages.OBJECT_CATEGORY:
        from apps.catalog.models import Category

        obj = Category.objects.filter(slug=ref).first()
    elif kind == studio_pages.OBJECT_PRODUCT:
        from apps.catalog.models import Product

        obj = Product.objects.filter(slug=ref).first() or _by_uuid(Product, ref)
    elif kind == studio_pages.OBJECT_PROMOTION:
        from apps.promotions.models import Promotion

        obj = _by_uuid(Promotion, ref)
    else:
        raise ScopeError(f"неизвестный вид объекта: {kind}")

    if obj is None:
        raise ScopeError("объект страницы не найден")
    return obj


def _by_uuid(model, ref: str):
    """Роуты деталей живут и на uuid — мусорная строка не должна ронять запрос."""
    import uuid as _uuid

    try:
        return model.objects.filter(pk=_uuid.UUID(str(ref))).first()
    except (ValueError, AttributeError, TypeError):
        return None


def read_state(tenant, setting_code: str, ref: str) -> ScopeState:
    """Что сейчас у объекта и что он унаследовал бы."""
    setting = studio_pages.SETTINGS.get(setting_code or "")
    if setting is None or not setting.has_object_scope:
        raise ScopeError(f"настройка {setting_code!r} не имеет охвата «только здесь»")

    site_value = _site_value(tenant, setting)
    if setting.object_kind == studio_pages.OBJECT_PROMO_GROUP:
        per_group = (tenant.site_config or {}).get("promo_groups") or {}
        own = per_group.get((ref or "").strip(), "")
    else:
        own = getattr(_fetch(setting, ref), setting.object_field, "") or ""
    return ScopeState(setting.code, site_value, str(own or ""))


def write_value(tenant, setting_code: str, ref: str, value: str) -> ScopeState:
    """Записать значение объектного уровня; пустое — вернуть объект к наследованию."""
    setting = studio_pages.SETTINGS.get(setting_code or "")
    if setting is None or not setting.has_object_scope:
        raise ScopeError(f"настройка {setting_code!r} не имеет охвата «только здесь»")

    value = (value or "").strip()
    if value and value not in _valid_values(setting):
        raise ScopeError(f"недопустимое значение {value!r} для {setting.code}")

    if setting.object_kind == studio_pages.OBJECT_PROMO_GROUP:
        _write_promo_group(tenant, (ref or "").strip(), value)
    else:
        obj = _fetch(setting, ref)
        setattr(obj, setting.object_field, value)
        obj.save(update_fields=[setting.object_field])  # точечно: чужие поля не трогаем
    return read_state(tenant, setting_code, ref)


def _write_promo_group(tenant, group: str, value: str) -> None:
    """Группа акций — свободный текст без модели, поэтому её выбор лежит в конфиге.

    Пишем ТОЧЕЧНО (а не пересобирая конфиг): рядом живут ключи, которые Студия в этот
    момент не редактирует, и полная пересборка роняла бы их — класс дефектов W6.
    """
    if not group:
        raise ScopeError("страница канвы не указывает группу акций")
    cfg = dict(tenant.site_config or {})
    groups = dict(cfg.get("promo_groups") or {})
    if value:
        groups[group] = value
    else:
        groups.pop(group, None)
    if groups:
        cfg["promo_groups"] = groups
    else:
        cfg.pop("promo_groups", None)  # presence-minimal: пустой ключ не храним
    tenant.site_config = cfg
    tenant.save(update_fields=["site_config"])
