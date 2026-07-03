"""UC2-4: единый диспетчер инлайн-правки канвы витрины.

Пять моделей с одним wire-контрактом JSON {pk, field, value} (product/event/
stay/service/promotion; все три JS-канала канвы — data-edit-model blur,
data-price-edit и data-dt-edit попапы — шлют его в MODEL_EDIT_URLS[model]).
Прежние пер-модельные вьюхи стали тонкими алиасами `dispatch(request, key)` —
URL-имена/протокол не менялись, семантика КАЖДОГО поля перенесена 1:1
(вкл. осознанные асимметрии bump: product-текст и promotion-title кэш НЕ
бампят — как раньше). Замки — существующие test_inline_edit по моделям.

ВНЕ диспетчера: category_inline_edit ({category_pk, value} — другой контракт)
и site_inline_edit ({field, value} без pk — site_config, авто-bump сигналом).

План/карта эндпоинтов: docs/uc2-4-inline-dispatcher-plan-2026-07-03.md.
"""

import json
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation

from django.core.exceptions import ValidationError
from django.http import HttpResponse, HttpResponseBadRequest
from django.utils import timezone
from django.utils.dateparse import parse_datetime

_MAX_MONEY = Decimal("1000000")


@dataclass(frozen=True)
class Field:
    """Спека одного инлайн-поля.

    kind: text | decimal (Decimal→attr, q0.01) | cents (евро→int-центы в attr) |
    percent (целое 0..100, 0→None) | datetime (ISO, naive→текущая TZ).
    i18n: text пишет в dict-поле attr['de'] (product/promotion), иначе плоско.
    required: пустой text → 400 («главное» поле не затирается).
    clamp: обрезка длины text (0 = нет). gate: имя bool-атрибута объекта,
    True → 400 (has_variants/has_tiers — цена правится в форме).
    bump: сброс кэша витрины после записи (асимметрии легаси сохранены)."""

    kind: str
    attr: str
    i18n: bool = False
    required: bool = False
    clamp: int = 0
    bump: bool = True
    gate: str = ""


INLINE_REGISTRY = {
    "product": {
        "name": Field("text", "name", i18n=True, required=True, bump=False),
        "description": Field("text", "description", i18n=True, bump=False),
        "base_price": Field("decimal", "base_price", gate="has_variants"),
    },
    "event": {
        "title": Field("text", "title", required=True, clamp=200),
        "description": Field("text", "description"),
        "price_eur": Field("cents", "price_cents", gate="has_tiers"),
    },
    "stay": {
        "name": Field("text", "name", required=True, clamp=120),
        "description": Field("text", "description"),
        "price_eur": Field("cents", "price_cents"),
    },
    "service": {
        "name": Field("text", "name", required=True, clamp=120),
        "description": Field("text", "description"),
        "price_eur": Field("cents", "price_cents"),
    },
    "promotion": {
        "title": Field("text", "title", i18n=True, required=True, bump=False),
        "price_override": Field("decimal", "price_override"),
        "compare_at_price": Field("decimal", "compare_at_price"),
        "discount_percent": Field("percent", "discount_percent"),
        "ends_at": Field("datetime", "ends_at"),
    },
}


def _model(model_key):
    """Ленивый резолв модели (core не импортирует tenant-appы на уровне модуля)."""
    from apps.booking.models import Service
    from apps.catalog.models import Product
    from apps.events.models import Event
    from apps.promotions.models import Promotion
    from apps.stays.models import StayUnit

    return {
        "product": Product,
        "event": Event,
        "stay": StayUnit,
        "service": Service,
        "promotion": Promotion,
    }[model_key]


def _bump_storefront(request):
    """SE-5a: правка данных (не site_config) кэш сама не бампит — сбрасываем явно."""
    schema = getattr(getattr(request, "tenant", None), "schema_name", None)
    if schema:
        from apps.core.pagecache import bump_storefront_cache

        bump_storefront_cache(schema)


def _parse_decimal(value):
    """Число канвы: запятая→точка, границы 0..1e6; None = невалид."""
    raw = str(value).strip().replace(",", ".")
    try:
        num = Decimal(raw)
    except (InvalidOperation, ValueError):
        return None
    if num < 0 or num > _MAX_MONEY:
        return None
    return num


def dispatch(request, model_key: str):
    """Единая обработка инлайн-правки: вайтлист → объект → спека → save → bump."""
    fields = INLINE_REGISTRY[model_key]
    try:
        data = json.loads(request.body or b"{}")
    except (ValueError, TypeError):
        return HttpResponseBadRequest()
    pk = data.get("pk")
    field = data.get("field")
    value = data.get("value", "")
    spec = fields.get(field) if field else None
    if not pk or spec is None:
        return HttpResponseBadRequest()
    model = _model(model_key)
    try:
        obj = model.objects.get(pk=pk)
    except (model.DoesNotExist, ValidationError, ValueError):
        return HttpResponseBadRequest()
    if spec.gate and getattr(obj, spec.gate):
        return HttpResponseBadRequest()

    if spec.kind == "text":
        value = value.strip() if isinstance(value, str) else ""
        if spec.required and not value:  # «главное» поле пустым не затираем
            return HttpResponseBadRequest()
        if spec.clamp:
            value = value[: spec.clamp]
        if spec.i18n:
            i18n = dict(getattr(obj, spec.attr) or {})
            i18n["de"] = value
            setattr(obj, spec.attr, i18n)
        else:
            setattr(obj, spec.attr, value)
    elif spec.kind == "decimal":
        num = _parse_decimal(value)
        if num is None:
            return HttpResponseBadRequest()
        setattr(obj, spec.attr, num.quantize(Decimal("0.01")))
    elif spec.kind == "cents":
        num = _parse_decimal(value)
        if num is None:
            return HttpResponseBadRequest()
        setattr(obj, spec.attr, int((num * 100).quantize(Decimal("1"))))
    elif spec.kind == "percent":
        raw = str(value).strip().replace(",", ".")
        try:
            pct = Decimal(raw)
        except (InvalidOperation, ValueError):
            return HttpResponseBadRequest()
        if pct != pct.to_integral_value() or not (0 <= pct <= 100):
            return HttpResponseBadRequest()
        setattr(obj, spec.attr, int(pct) or None)  # 0 → очистить
    elif spec.kind == "datetime":
        dt = parse_datetime(str(value).strip())
        if dt is None:
            return HttpResponseBadRequest()
        if timezone.is_naive(dt):
            dt = timezone.make_aware(dt)
        setattr(obj, spec.attr, dt)
    else:  # незнакомый kind — ошибка декларации, fail-closed
        return HttpResponseBadRequest()

    obj.save(update_fields=[spec.attr, "updated_at"])
    if spec.bump:
        _bump_storefront(request)
    return HttpResponse(status=204)
