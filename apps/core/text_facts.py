"""AIS-7: доверенные факты для «✨ Text vorschlagen» — только из СОХРАНЁННЫХ данных.

План — docs/ais-7-texts-from-facts-plan-2026-11-06.md. Браузеру не верим: факты читает
сервер (объект по pk в текущей схеме, тенант — из запроса). Цен в фактах нет намеренно:
цена на витрине показывается отдельно, а «nur 3,99 €» в описании устаревает (PAngV).
Форма — `apps.inbox.ai_facts.Facts`: проверка утверждений и аллергенов переиспользуется.
"""

from __future__ import annotations

from apps.inbox.ai_facts import Facts, _labels_all_languages, _one_line

KIND_PRODUCT = "product"
KIND_SERVICE = "service"
KIND_ABOUT = "about"
KIND_HERO = "hero"
KINDS = (KIND_PRODUCT, KIND_SERVICE, KIND_ABOUT, KIND_HERO)


def _base(value) -> str:
    from django.conf import settings

    if isinstance(value, dict):
        return str(value.get(settings.LANGUAGE_CODE) or next(iter(value.values()), "") or "")
    return str(value or "")


def product_facts(obj) -> Facts:
    from apps.catalog.food import allergen_labels, diet_badges

    facts = Facts()
    name = _base(obj.name)
    facts.lines.append(f"Item: {_one_line(name)}")
    facts.name_text += f" {name}"
    category = getattr(obj, "category", None)
    if category is not None:
        parent = getattr(category, "parent", None)
        path = " / ".join(_base(c.name) for c in (parent, category) if c is not None)
        facts.lines.append(f"- Category: {_one_line(path)}")
        facts.name_text += f" {path}"
    if obj.brand:
        facts.lines.append(f"- Brand: {_one_line(obj.brand)}")
        facts.name_text += f" {obj.brand}"
    if obj.unit and obj.content_amount:
        amount = f"{obj.content_amount.normalize():f}".replace(".", ",")
        facts.lines.append(f"- Content: {amount} {obj.unit}")
    for label, value in (
        ("Origin", obj.origin),
        ("Ingredients", obj.ingredients),
        ("Material", getattr(obj, "material", "")),
        ("Care", getattr(obj, "care", "")),
        ("Condition", getattr(obj, "condition_note", "")),
    ):
        if value:
            facts.lines.append(f"- {label}: {_one_line(value, 400)}")
    facts.claims_text += f" {name} {obj.origin or ''} {obj.ingredients or ''}"
    allergens = [a for a in (obj.allergens or []) if a]
    if allergens:
        facts.allergens_declared = True
        labels = ", ".join(str(a) for a in allergen_labels(allergens))
        facts.lines.append(f"- Allergens (complete declaration): {labels}")
        facts.allergen_text = _labels_all_languages(allergens)
    diets = ", ".join(str(b["label"]) for b in diet_badges(obj.diets or []))
    if diets:
        facts.lines.append(f"- Diet: {diets}")
        facts.claims_text += f" {diets} {' '.join(obj.diets or [])}"
    sizes = set()
    for v in obj.variants.all()[:20]:
        sizes |= {s for s in (v.size, v.color) if s}
    if sizes:
        facts.lines.append(f"- Variants: {_one_line(', '.join(sorted(sizes)))}")
    return facts


def service_facts(obj) -> Facts:
    facts = Facts()
    facts.lines.append(f"Service: {_one_line(obj.name)}")
    facts.name_text += f" {obj.name}"
    if obj.duration_minutes:
        facts.lines.append(f"- Duration: {obj.duration_minutes} min")
    for line in (obj.attributes or [])[:12]:
        if isinstance(line, str) and line.strip():
            facts.lines.append(f"- Detail: {_one_line(line)}")
            facts.claims_text += f" {line}"
    for row in (obj.faq or [])[:8]:
        if isinstance(row, dict) and row.get("q"):
            facts.lines.append(f"- FAQ: {_one_line(row.get('q'))} {_one_line(row.get('a') or '')}")
    for v in obj.variants.filter(is_active=True)[:10]:
        facts.lines.append(f"- Variant: {_one_line(v.name)}")
        facts.name_text += f" {v.name}"
    facts.claims_text += f" {obj.name}"
    return facts


def business_facts(tenant) -> Facts:
    """«Über uns» и баннер: имя, вид бизнеса, город, часы, разделы и позиции."""
    facts = Facts()
    name = getattr(tenant, "name", "") or ""
    facts.lines.append(f"Business: {_one_line(name)}")
    facts.name_text += f" {name}"
    try:
        kind = tenant.get_business_type_display()
    except Exception:  # noqa: BLE001
        kind = ""
    if kind:
        facts.lines.append(f"- Kind of business: {kind}")
    if getattr(tenant, "city", ""):
        facts.lines.append(f"- City: {tenant.city}")
        facts.name_text += f" {tenant.city}"
    try:
        hours = tenant.opening_hours_localized(None)
    except Exception:  # noqa: BLE001 — часы необязательны
        hours = ""
    hours = "; ".join(p.strip() for p in str(hours or "").splitlines() if p.strip())
    if hours:
        facts.lines.append(f"- Opening hours: {_one_line(hours, 400)}")
    names = _offer_names()
    if names:
        facts.lines.append(f"- Offers: {_one_line(', '.join(names), 400)}")
        facts.name_text += " " + " ".join(names)
        facts.claims_text += " " + " ".join(names)
    return facts


def _offer_names() -> list[str]:
    out: list[str] = []
    try:
        from apps.catalog.models import Category, Product

        out += [_base(c.name) for c in Category.objects.filter(is_active=True)[:5]]
        out += [_base(p.name) for p in Product.objects.filter(is_active=True)[:5]]
    except Exception:  # noqa: BLE001 — каталог может быть выключен
        pass
    try:
        from apps.booking.models import Service

        out += [s.name for s in Service.objects.filter(is_active=True)[:5]]
    except Exception:  # noqa: BLE001
        pass
    return [n for n in out if n][:12]


def facts_for(kind: str, obj, tenant) -> Facts:
    if kind == KIND_PRODUCT:
        return product_facts(obj)
    if kind == KIND_SERVICE:
        return service_facts(obj)
    return business_facts(tenant)
