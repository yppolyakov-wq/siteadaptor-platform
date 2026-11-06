"""AIS-M M-1e: какие живые бизнесы держат исторический пресет модулей.

Тенант, чей `disabled_modules` совпадает с одним из исторических пресетов своего типа,
модули «выключил пресет», а не владелец — таким `--apply` включает ровно то, что новый
пресет включает (§5.7). Любое расхождение = выбор владельца: не трогаем, только отчёт.
План docs/ais-m1-directions-screen-plan-2026-11-05.md §M-1e."""

from __future__ import annotations

from itertools import product

from apps.core import modules, storefront_profile
from apps.core.module_presets import LEGACY_DISABLED

CLASS_PRESET = "preset"
CLASS_OWNER = "owner"
CLASS_SAME = "same"  # уже совпадает с новым пресетом — делать нечего


def legacy_variants(business_type: str) -> list[frozenset[str]]:
    """Все исторические формы пресета: снимок M-1a, он же без blog (до E8.7), у отеля
    без booking (до E8.11), с добавками миграций tenants/0012 (stays) и 0017
    (customer_account)."""
    base = set(LEGACY_DISABLED.get(business_type or "", ()))
    drops = [("blog",)]
    if business_type == "hotel":
        drops.append(("booking",))
    adds = [("stays",), ("customer_account",)]
    out: set[frozenset[str]] = set()
    for flags in product((False, True), repeat=len(drops) + len(adds)):
        s = set(base)
        for on, keys in zip(flags[: len(drops)], drops, strict=True):
            if on:
                s -= set(keys)
        for on, keys in zip(flags[len(drops) :], adds, strict=True):
            if on:
                s |= set(keys)
        out.add(frozenset(s))
    return sorted(out, key=sorted)


def classify(tenant) -> tuple[str, list[str]]:
    """(класс, ключи к включению). Ключи — только для класса preset."""
    current = frozenset(tenant.disabled_modules or [])
    new_preset = frozenset(modules.default_disabled_for(tenant.business_type))
    if storefront_profile.is_aktionen(tenant):
        return CLASS_OWNER, []  # лёгкий пакет: быстрый старт сам правит набор
    if not current - new_preset:
        return CLASS_SAME, []  # включать нечего (в т.ч. после --apply)
    if current not in legacy_variants(tenant.business_type):
        return CLASS_OWNER, []
    enable = sorted(current - new_preset)
    return (CLASS_PRESET, enable) if enable else (CLASS_SAME, [])


def skip_reason(tenant) -> str:
    if tenant.schema_name == "public":
        return "public"
    if getattr(tenant, "is_demo", False):
        return "demo"
    if getattr(tenant, "provisioning_status", "ready") != "ready":
        return "provisioning"
    return ""


def report_for(tenant) -> dict:
    cls, enable = classify(tenant)
    disabled = set(tenant.disabled_modules or [])
    base_off = sorted(s.key for s in modules.REGISTRY if s.layer == "base" and s.key in disabled)
    return {
        "schema": tenant.schema_name,
        "type": tenant.business_type,
        "class": cls,
        "enable": enable,
        "base_off": base_off if cls == CLASS_OWNER else [],
    }


def apply_for(tenant) -> list[str]:
    """Включает модули пресета под блокировкой с повторной проверкой класса — гонка с
    владельцем (он успел переключить) оставляет строку как есть. Ничего не выключает."""
    from django.db import transaction

    with transaction.atomic():
        locked = type(tenant).objects.select_for_update().get(pk=tenant.pk)
        cls, enable = classify(locked)
        if cls != CLASS_PRESET:
            return []
        enable = [k for k in enable if not modules.module_switch_problem(locked, k, True)]
        if not enable:
            return []
        locked.disabled_modules = [m for m in (locked.disabled_modules or []) if m not in enable]
        locked.auto_create_schema = False
        locked.save(update_fields=["disabled_modules", "updated_at"])
    tenant.disabled_modules = locked.disabled_modules
    return enable
