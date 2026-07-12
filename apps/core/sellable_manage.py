"""FB-8: единый кабинетный список продаваемых сущностей (товар/услуга/номер/событие/
комбо) — «отдел продажных сущностей».

Проблема: сущности живут в РАЗНЫХ силосах кабинета (товары /catalog/, услуги /booking/
leistungen/, номера /stays/units/, события /events/). У мультиархетипного тенанта — 4+
экрана. Этот модуль даёт ОДИН обзор: read + тумблер видимости + переход к РОДНОЙ форме
(единый CRUD НЕ делаем — родные формы с вариантами/комбо/фото остаются авторитетными).

Зеркало `transactions.manage_sections_for` по оси КАТАЛОГА (sellable), а не транзакций.
Заявки/jobs — НЕ sellable (транзакция, место на доске «Verkäufe»). Модели резолвим
лениво; display-поля берём через `sellable.display_fields` (тот же адаптер, что витрина).
"""

from dataclasses import dataclass

from django.urls import NoReverseMatch, reverse

from apps.core import sellable

# kind → конфиг управления. edit/add: (url_name, per_pk). toggle=True → простой флип
# is_active (product/service/stay/combo); event публикуется через FSM (draft↔published) —
# инлайн-тумблера нет, только статус + переход к форме.
_MANAGE = {
    "product": {
        "model": "catalog.Product",
        "module": "catalog",
        "label": "Produkte",
        "edit": ("catalog:product-edit", True),
        "add": ("catalog:product-create", False),
        "toggle": True,
    },
    "service": {
        "model": "booking.Service",
        "module": "booking",
        "label": "Leistungen",
        "edit": ("booking:services", False),
        "add": ("booking:services", False),
        "toggle": True,
    },
    "stay": {
        "model": "stays.StayUnit",
        "module": "stays",
        "label": "Zimmer & Einheiten",
        "edit": ("stays:units", False),
        "add": ("stays:units", False),
        "toggle": True,
    },
    "event": {
        "model": "events.Event",
        "module": "events",
        "label": "Veranstaltungen",
        "edit": ("events:edit", True),
        "add": ("events:create", False),
        "toggle": False,
    },
    "combo": {
        "model": "catalog.Combo",
        "module": "catalog",
        "label": "Kombis",
        "edit": ("catalog:combo-edit", True),
        "add": ("catalog:combo-create", False),
        "toggle": True,
    },
}

MANAGE_KINDS = tuple(_MANAGE)


@dataclass(frozen=True)
class ManagedSellable:
    kind: str
    pk: object
    name: str
    price_display: str
    image_url: str
    is_visible: bool
    can_toggle: bool
    status_label: str
    edit_url: str


def _model(kind):
    from django.apps import apps as django_apps

    return django_apps.get_model(_MANAGE[kind]["model"])


def _reverse(spec, pk) -> str:
    name, per_pk = spec
    try:
        return reverse(name, args=[pk]) if per_pk else reverse(name)
    except NoReverseMatch:
        return ""


def _is_visible(kind, obj) -> bool:
    if kind == "event":
        from apps.events.models import Event

        return obj.status == Event.STATUS_PUBLISHED
    return bool(getattr(obj, "is_active", True))


def _managed(kind, obj, locale) -> ManagedSellable:
    cfg = _MANAGE[kind]
    f = sellable.display_fields(kind, obj, locale)
    status_label = obj.get_status_display() if kind == "event" else ""
    return ManagedSellable(
        kind=kind,
        pk=obj.pk,
        name=f["name"],
        price_display=f["price_display"],
        image_url=f["image_url"],
        is_visible=_is_visible(kind, obj),
        can_toggle=cfg["toggle"],
        status_label=status_label,
        edit_url=_reverse(cfg["edit"], obj.pk),
    )


def _locale(tenant) -> str | None:
    return getattr(tenant, "default_locale", None) or None


def sellable_manage_sections_for(tenant, limit: int = 200) -> list[dict]:
    """Секции обзора: по одному активному sellable-kind С ХОТЯ БЫ одной сущностью
    (пустые не шумят — их «＋ Neu» есть в `add_options`). Порядок — MANAGE_KINDS."""
    locale = _locale(tenant)
    out = []
    for kind in MANAGE_KINDS:
        cfg = _MANAGE[kind]
        if not tenant.is_module_active(cfg["module"]):
            continue
        qs = _model(kind).objects.all()
        # event использует status (нет is_active) → сортируем только по дате.
        qs = (
            qs.order_by("-is_active", "-created_at")
            if cfg["toggle"]
            else qs.order_by("-created_at")
        )
        items = [_managed(kind, obj, locale) for obj in qs[:limit]]
        if not items:
            continue
        out.append({"kind": kind, "label": cfg["label"], "items": items, "count": len(items)})
    return out


def add_options(tenant) -> list[dict]:
    """Кнопки «＋ Neu» по активным sellable-kind (вход в РОДНУЮ форму создания)."""
    out = []
    for kind in MANAGE_KINDS:
        cfg = _MANAGE[kind]
        if not tenant.is_module_active(cfg["module"]):
            continue
        url = _reverse(cfg["add"], None)
        if url:
            out.append({"kind": kind, "label": cfg["label"], "url": url})
    return out


def toggle_visibility(kind: str, pk):
    """FB-8: флип видимости (is_active) для product/service/stay/combo. Event (публикация
    через FSM) не поддержан — Http404. Возвращает объект. Схема тенанта изолирует выборку."""
    from django.http import Http404
    from django.shortcuts import get_object_or_404

    cfg = _MANAGE.get(kind)
    if not cfg or not cfg["toggle"]:
        raise Http404("kind not toggleable")
    obj = get_object_or_404(_model(kind), pk=pk)
    obj.is_active = not obj.is_active
    obj.save(update_fields=["is_active"])
    return obj
