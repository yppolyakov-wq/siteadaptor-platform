"""AIS A-4a: «KI-Aktionen» — пакет «создать» из помощника с предпросмотром и откатом.

План — docs/ais-a4-ki-actions-plan-2026-11-06.md (§2, §7–§9). Стратегия —
docs/ai-strategy-2026-11-06.md (уровень 2: объект × действие).

Путь: фраза → план помощника (правила, при включённой задаче — ИИ с пост-проверкой фактов)
→ пакет пунктов ЗДЕСЬ (`from_plan`) → предпросмотр с правкой полей и галочками → «Alles
übernehmen» (`apply`) → запись ТЕМИ ЖЕ писателями, что экраны кабинета → «Rückgängig»
10 минут (`undo`).

Инварианты:
* реестр действий ЗАКРЫТ (`ACTIONS`): чего в нём нет, ассистент сделать не может —
  запретный список стратегии (заказы, клиенты, деньги, удаление) выполняется по построению;
* до клика в базе ничего: пакет живёт в кэше задачи (TTL 30 мин), POST меняет только
  значения полей и галочки по индексу, вид действия и объект — из кэша;
* права и пакет проверяются ДО транзакции, всё или ничего, повтор POST — тот же отчёт
  (уникальный `AssistantChange.job`);
* блокировки: сначала Tenant (сериализует применения тенанта), строки — одним запросом
  по pk; `lock_timeout` 3 с — владелец не ждёт за покупателем;
* откат — только автор, только в окне, только если объект с тех пор не меняли (снимок
  полей) и на него ничего не ссылается; товар/категория — мягкое удаление, услуга со
  ссылками — выключается, а не удаляется.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from datetime import timedelta
from decimal import Decimal

from django.db import IntegrityError, OperationalError, connection, transaction
from django.utils import timezone
from django.utils.translation import gettext as _
from django.utils.translation import gettext_lazy

logger = logging.getLogger(__name__)

ACTIONS_TTL = 1800  # пакет до клика — 30 минут в кэше задачи
UNDO_MINUTES = 10
LOCK_TIMEOUT = "3s"
MAX_ITEMS = 10
NAME_MAX = 120
MAX_OPTIONS = 200
MAX_PRICE = Decimal("100000")

CATEGORY_CREATE = "category.create"
PRODUCT_CREATE = "product.create"
SERVICE_CREATE = "service.create"
# A-4b: изменения СУЩЕСТВУЮЩИХ объектов (план §11)
PRODUCT_PRICE = "product.price"
SERVICE_PRICE = "service.price"
PRODUCT_VISIBILITY = "product.visibility"
SERVICE_VISIBILITY = "service.visibility"
CATEGORY_VISIBILITY = "category.visibility"
PRODUCT_MOVE = "product.move"
PAGE_SETTING = "page.setting"  # A-4c: шаблон/сетка/карточка страницы (page_settings)


@dataclass(frozen=True)
class FieldSpec:
    name: str  # имя поля пакета (не формы)
    label: object
    kind: str  # text | money | minutes | category | visible (только показ) | setting
    required: bool = False


@dataclass(frozen=True)
class ActionSpec:
    key: str
    entity: str  # вид setup_assistant (category | product | service)
    label: object
    module: str
    perm: str
    screen: str  # экран создания — тот же гейт пакета, что у формы
    edit_screen: str  # экран объекта после создания (ссылка в отчёте)
    fields: tuple[FieldSpec, ...]
    verb: str = "create"  # create | price | visibility | move | page


ACTIONS: dict[str, ActionSpec] = {
    CATEGORY_CREATE: ActionSpec(
        CATEGORY_CREATE,
        "category",
        gettext_lazy("Kategorie anlegen"),
        "catalog",
        "sortiment.edit",
        "catalog:category-create",
        "catalog:category-edit",
        (
            FieldSpec("name", gettext_lazy("Name"), "text", True),
            FieldSpec("parent", gettext_lazy("Übergeordnete Kategorie"), "category"),
        ),
    ),
    PRODUCT_CREATE: ActionSpec(
        PRODUCT_CREATE,
        "product",
        gettext_lazy("Produkt anlegen"),
        "catalog",
        "sortiment.edit",
        "catalog:product-create",
        "catalog:product-edit",
        (
            FieldSpec("name", gettext_lazy("Name"), "text", True),
            FieldSpec("price", gettext_lazy("Preis (€)"), "money", True),
            FieldSpec("category", gettext_lazy("Kategorie"), "category"),
        ),
    ),
    SERVICE_CREATE: ActionSpec(
        SERVICE_CREATE,
        "service",
        gettext_lazy("Leistung anlegen"),
        "booking",
        "sortiment.edit",
        "booking:service-new",
        "booking:service-edit",
        (
            FieldSpec("name", gettext_lazy("Name"), "text", True),
            FieldSpec("price", gettext_lazy("Preis (€)"), "money"),
            FieldSpec("duration", gettext_lazy("Dauer (Min.)"), "minutes"),
        ),
    ),
}

_PRICE_FIELD = (FieldSpec("price", gettext_lazy("Neuer Preis (€)"), "money", True),)
_VISIBLE_FIELD = (FieldSpec("visible", gettext_lazy("Auf der Website"), "visible"),)
_MOVE_FIELD = (FieldSpec("category", gettext_lazy("Neue Kategorie"), "category"),)
for _key, _entity, _label, _module, _perm, _screen, _fields, _verb in (
    (
        PRODUCT_PRICE,
        "product",
        gettext_lazy("Preis ändern"),
        "catalog",
        "preise.edit",
        "catalog:product-edit",
        _PRICE_FIELD,
        "price",
    ),
    (
        SERVICE_PRICE,
        "service",
        gettext_lazy("Preis ändern"),
        "booking",
        "preise.edit",
        "booking:service-edit",
        _PRICE_FIELD,
        "price",
    ),
    (
        PRODUCT_VISIBILITY,
        "product",
        gettext_lazy("Sichtbarkeit ändern"),
        "catalog",
        "sortiment.edit",
        "catalog:product-edit",
        _VISIBLE_FIELD,
        "visibility",
    ),
    (
        SERVICE_VISIBILITY,
        "service",
        gettext_lazy("Sichtbarkeit ändern"),
        "booking",
        "sortiment.edit",
        "booking:service-edit",
        _VISIBLE_FIELD,
        "visibility",
    ),
    (
        CATEGORY_VISIBILITY,
        "category",
        gettext_lazy("Sichtbarkeit ändern"),
        "catalog",
        "sortiment.edit",
        "catalog:category-edit",
        _VISIBLE_FIELD,
        "visibility",
    ),
    (
        PRODUCT_MOVE,
        "product",
        gettext_lazy("In andere Kategorie verschieben"),
        "catalog",
        "sortiment.edit",
        "catalog:product-edit",
        _MOVE_FIELD,
        "move",
    ),
):
    ACTIONS[_key] = ActionSpec(
        _key, _entity, _label, _module, _perm, _screen, _screen, _fields, _verb
    )
ACTIONS[PAGE_SETTING] = ActionSpec(
    PAGE_SETTING,
    "page",
    gettext_lazy("Seite einstellen"),
    "",  # модуль типа страницы проверяет сам page_settings.validate
    "website.edit",
    "page-templates-website",
    "page-templates-website",
    (FieldSpec("value", gettext_lazy("Neue Einstellung"), "setting", True),),
    "page",
)

#: Объекты, которых в реестре не может быть никогда (стратегия В-2, запретный список).
FORBIDDEN_OBJECTS = frozenset(
    {"order", "customer", "invoice", "payment", "refund", "voucher", "booking", "member", "user"}
)
FORBIDDEN_VERBS = frozenset({"delete", "refund", "pay", "send", "export"})

ENTITY_ACTION = {"category": CATEGORY_CREATE, "product": PRODUCT_CREATE, "service": SERVICE_CREATE}


class ApplyError(Exception):
    def __init__(self, code: str, errors: dict | None = None):
        super().__init__(code)
        self.code = code
        self.errors = errors or {}


# ───────────────────────── пакет из плана ─────────────────────────


def _cat_name(cat) -> str:
    return cat.get_i18n("name") if hasattr(cat, "get_i18n") else ""


def _find_category(tenant, name: str) -> str:
    """'pk:<id>' единственной живой категории с таким именем (без регистра), иначе ''."""
    from apps.catalog.models import Category

    wanted = (name or "").strip().casefold()
    if not wanted:
        return ""
    hits = [
        c
        for c in Category.objects.only("pk", "name").order_by("pk")[:MAX_OPTIONS]
        if any(str(v).strip().casefold() == wanted for v in (c.name or {}).values())
    ]
    return f"pk:{hits[0].pk}" if len(hits) == 1 else ""


_IN_CATEGORY = re.compile(
    r"\s+(?:in|im|unter|в|во|у|до)\s+(?:(?:der\s+)?kategorie\s+|категори[июї]\s+)?"
    r"[\"„«]?([^\"“»]{2,60}?)[\"“»]?$",
    re.IGNORECASE,
)


def from_plan(plan, tenant) -> list[dict]:
    """Пункты пакета из шагов плана, которые ассистент умеет создать сам.

    Категория шага ищется сначала среди категорий ЭТОГО пакета («Kategorie Kuchen,
    Käsekuchen 3,20 €»), затем среди существующих (одно совпадение имени); не нашлась —
    пусто и подсказка, владелец выберет в предпросмотре."""
    items: list[dict] = []
    new_cats: dict[str, int] = {}
    for step in plan.steps:
        action = ENTITY_ACTION.get(step.entity)
        if action is None or len(items) >= MAX_ITEMS:
            continue
        got = {f.name: f.value for f in step.fields}
        name = (got.get("name_de") or got.get("name") or "").strip()[:NAME_MAX]
        values = {"name": name}
        note = ""
        if action != CATEGORY_CREATE:
            values["price"] = (got.get("base_price") or got.get("price_eur") or "").strip()
        if action == SERVICE_CREATE:
            values["duration"] = (got.get("duration") or "").strip()
        if action in (CATEGORY_CREATE, PRODUCT_CREATE):
            key = "parent" if action == CATEGORY_CREATE else "category"
            parent = (got.get("parent") or got.get("category") or "").strip()
            ref = ""
            # «Käsekuchen 3,20 € in Kuchen»: хвост «in <Kategorie>» снимаем с имени ТОЛЬКО если
            # это и есть категория шага или такая категория есть (в пакете или одна у
            # владельца) — иначе это часть названия («Brot in Scheiben»)
            tail = _IN_CATEGORY.search(name)
            if tail:
                cand = tail.group(1).strip()
                hit = new_cats.get(cand.casefold())
                found = f"item:{hit}" if hit is not None else _find_category(tenant, cand)
                if found or (parent and cand.casefold() == parent.casefold()):
                    name = name[: tail.start()].strip()
                    values["name"] = name
                    if not parent:
                        ref = found
            if parent:
                idx = new_cats.get(parent.casefold())
                ref = f"item:{idx}" if idx is not None else _find_category(tenant, parent)
                if not ref:
                    note = _("Kategorie „%(name)s“ gibt es noch nicht — bitte wählen.") % {
                        "name": parent
                    }
            values[key] = ref
        if action == CATEGORY_CREATE and name:
            new_cats[name.casefold()] = len(items)
        items.append({"action": action, "values": values, "note": note})
    return items


# ───────────────────────── права и показ ─────────────────────────


def allowed(request, spec: ActionSpec) -> tuple[bool, str]:
    """(можно, причина) — модуль, право и те же три гейта, что у экрана создания (пакет,
    белый список Mini App, права экрана): ассистент не делает того, чего не дал бы экран."""
    from apps.core import packages, setup_assistant
    from apps.core.permissions import has_perm

    try:
        if spec.module and not request.tenant.is_module_active(spec.module):
            return False, _("Diese Funktion ist bei Ihnen nicht eingeschaltet.")
        if not has_perm(request.user, spec.perm):
            return False, _("Dafür fehlt Ihnen die Berechtigung — bitte die Inhaberin fragen.")
        if not packages.view_allowed(request.tenant, spec.screen):
            return False, _("In Ihrem Paket nicht enthalten.")
        if not setup_assistant.reachable(request, spec.screen):
            return False, _("Das geht hier nicht — bitte im Kabinett im Browser anlegen.")
    except Exception:  # noqa: BLE001 — неизвестно → не предлагаем кнопку
        logger.warning("assistant actions: gate failed for %s", spec.key, exc_info=True)
        return False, _("Gerade nicht prüfbar — bitte im Formular anlegen.")
    return True, ""


def _existing_options(tenant) -> list[tuple[str, str]]:
    from apps.catalog.models import Category

    return [
        (f"pk:{cat.pk}", _cat_name(cat))
        for cat in Category.objects.only("pk", "name").order_by("pk")[:MAX_OPTIONS]
    ]


def _new_options(items: list[dict], upto: int) -> list[tuple[str, str]]:
    """Новые категории пакета ВЫШЕ пункта `upto`: их создают раньше (категория не
    ссылается сама на себя и на ещё не созданную)."""
    return [
        (f"item:{i}", _("Neu: %(name)s") % {"name": item["values"]["name"]})
        for i, item in enumerate(items[:upto])
        if item.get("action") == CATEGORY_CREATE and (item.get("values") or {}).get("name")
    ]


def category_options(tenant, items: list[dict], upto: int, existing=None) -> list[tuple[str, str]]:
    """Выбор категории в предпросмотре пункта `upto`: без категории · новые · существующие."""
    if existing is None:
        existing = _existing_options(tenant)
    return [("", _("— ohne Kategorie —")), *_new_options(items, upto), *existing]


def present(request, items: list[dict], *, errors: dict | None = None) -> list[dict]:
    """Пункты для шаблона: подписи, значения, право (перепроверка при показе)."""
    from apps.core import setup_assistant

    existing = _existing_options(request.tenant)
    out = []
    for i, item in enumerate(items):
        spec = ACTIONS.get(item.get("action"))
        if spec is None:
            continue
        ok, reason = allowed(request, spec)
        if ok and item.get("blocked"):
            ok, reason = False, item["blocked"]
        # «переместить» — только в существующую категорию (новых в пакете изменений нет)
        upto = 0 if spec.verb == "move" else i
        if spec.verb == "page":  # A-4c: доступные варианты настройки (как на экране кабинета)
            from apps.core import assistant_pages

            options = assistant_pages.options(request.tenant, _target_pk(item))
        else:
            options = category_options(request.tenant, items, upto, existing)
        values = item.get("values") or {}
        fields = [
            {
                "name": f.name,
                "label": f.label,
                "kind": f.kind,
                "required": f.required,
                "value": values.get(f.name, ""),
                "input": f"f_{i}_{f.name}",
                "error": (errors or {}).get(f"{i}:{f.name}", ""),
            }
            for f in spec.fields
        ]
        if spec.verb == "create":
            prefill = {setup_assistant._NAME_FIELD[spec.entity]: values.get("name", "")}
            price_field = setup_assistant._PRICE_FIELD.get(spec.entity)
            if price_field:
                prefill[price_field] = values.get("price", "")
            form_url = (
                setup_assistant._form_url(spec.entity, prefill)
                if setup_assistant.reachable(request, spec.screen)
                else ""
            )
        elif spec.verb == "page":
            form_url = _page_url(request, spec, values.get("type", ""))
        else:
            form_url = _object_url(request, spec, _target_pk(item))
        out.append(
            {
                "index": i,
                "label": spec.label,
                "name": values.get("name", ""),
                "fields": fields,
                "allowed": ok,
                "take": item.get("take", True),
                "reason": reason,
                "note": item.get("note", ""),
                "options": options,
                "form_url": form_url,
                "verb": spec.verb,
                # без права — без текущих значений (цена/видимость скрытого товара)
                **(
                    _change_texts(request, spec, item, values, existing)
                    if ok
                    else {"before_text": "", "after_text": "", "warning": ""}
                ),
            }
        )
    return out


def _target_pk(item: dict) -> str:
    return str((item.get("target") or {}).get("pk") or "")


def _page_url(request, spec: ActionSpec, type_code: str) -> str:
    """Экран кабинета «Seitenvorlage» этого типа страницы (если открывается здесь)."""
    from apps.core import page_templates, setup_assistant

    if not type_code or not setup_assistant.reachable(request, spec.edit_screen):
        return ""
    try:
        return page_templates.cabinet_url(type_code)
    except Exception:  # noqa: BLE001 — ссылка-дополнение
        return ""


def _object_url(request, spec: ActionSpec, pk: str) -> str:
    from django.urls import NoReverseMatch, reverse

    from apps.core import setup_assistant

    if not pk or not setup_assistant.reachable(request, spec.edit_screen):
        return ""
    try:
        return reverse(spec.edit_screen, args=[pk])
    except NoReverseMatch:
        return ""


def _value_text(spec: ActionSpec, canon: str, existing=None, tenant=None, code: str = "") -> str:
    """Каноническое значение поля изменения → подпись «vorher/nachher»."""
    from apps.core import assistant_changes

    if spec.verb == "page":
        from apps.core import assistant_pages

        return assistant_pages.value_label(tenant, code, canon) if tenant is not None else canon
    if spec.verb == "price":
        return assistant_changes.money_text(spec.entity, canon)
    if spec.verb == "visibility":
        return str(_("sichtbar")) if canon else str(_("ausgeblendet"))
    if spec.verb == "move":
        if not canon:
            return str(_("ohne Kategorie"))
        labels = dict(existing if existing is not None else _existing_options(None))
        return labels.get(f"pk:{canon}", "")
    return ""


def _change_texts(request, spec, item, values, existing) -> dict:
    """«vorher → nachher» и предупреждение § 11 PAngV для пункта изменения."""
    if spec.verb == "create":
        return {"before_text": "", "after_text": "", "warning": ""}
    before = str(item.get("before") or "")
    after = ""
    try:
        after = _canon(spec, values)
    except ValueError:
        after = ""
    warning = ""
    if spec.key == CATEGORY_VISIBILITY and not after:
        warning = _(
            "Die Kategorie verschwindet aus Menü, Filtern und Stadtkatalog; ihre Produkte "
            "werden dabei nicht einzeln ausgeblendet."
        )
    if spec.verb == "price" and spec.entity == "product" and before and after:
        if Decimal(after) < Decimal(before):
            warning = _(
                "Der niedrigere Preis bleibt 30 Tage im Preisverlauf (§ 11 PAngV) — auch wenn "
                "Sie ihn zurücksetzen."
            )
    code = _target_pk(item)
    tenant = request.tenant
    return {
        "before_text": _value_text(spec, before, existing, tenant, code),
        "after_text": (
            _value_text(spec, after, existing, tenant, code)
            if after or spec.verb != "price"
            else ""
        ),
        "warning": warning,
    }


def _canon(spec: ActionSpec, values: dict) -> str:
    """Новое значение изменения в каноническом виде (как `assistant_changes.current`)."""
    from apps.core.money import parse_amount, to_cents

    if spec.verb == "price":
        amount = parse_amount(values.get("price", ""), max_value=MAX_PRICE)
        if amount is None:
            raise ValueError("no price")
        if spec.entity == "product":
            return str(amount.quantize(Decimal("0.01")))
        return str(to_cents(amount))
    if spec.verb == "visibility":
        return "1" if values.get("visible") else ""
    if spec.verb == "page":
        return str(values.get("value") or "")
    ref = values.get("category", "")
    return ref[3:] if ref.startswith("pk:") else ""


# ───────────────────────── применение ─────────────────────────


def merge_post(items: list[dict], post) -> list[dict]:
    """Значения полей спеки из POST поверх пунктов (по индексу); остальное — из кэша."""
    out = []
    for i, item in enumerate(items):
        spec = ACTIONS.get(item.get("action"))
        values = dict(item.get("values") or {})
        for f in spec.fields if spec and not item.get("fixed") else ():
            if f.kind == "visible":
                continue  # «скрыть/показать» — направление из кэша, не из формы
            key = f"f_{i}_{f.name}"
            if key in post:
                values[f.name] = str(post.get(key) or "").strip()[:NAME_MAX]
        take = item.get("take", True)
        if post.get("items_present") == "1":
            take = bool(post.get(f"take_{i}"))
        out.append({**item, "values": values, "take": take})
    return out


def _clean(items: list[dict], post, existing: list, tenant=None) -> tuple[list[dict], dict]:
    """Значения из POST поверх кэша (только поля спеки по индексу) + проверка формы."""
    from apps.core.money import parse_amount

    cleaned, errors = [], {}
    present_flag = post.get("items_present") == "1"
    merged = merge_post(items, post)
    for i, item in enumerate(items):
        spec = ACTIONS.get(item.get("action"))
        if spec is None:
            continue
        if present_flag and not post.get(f"take_{i}"):
            continue  # галочку «übernehmen» сняли
        values = dict(merged[i]["values"])
        for f in spec.fields:
            raw = str(values.get(f.name) or "").strip()
            err = ""
            if f.kind == "text":
                raw = raw[:NAME_MAX]
                if f.required and not raw:
                    err = _("Bitte einen Namen angeben.")
            elif f.kind == "money":
                try:
                    amount = parse_amount(raw, max_value=MAX_PRICE)  # ≤ 2 знака, 0…100 000
                except ValueError:
                    amount, err = None, _("Bitte einen Betrag zwischen 0 und 100.000 € angeben.")
                if not err and amount is None and f.required:
                    err = _("Bitte einen Preis angeben.")
            elif f.kind == "minutes" and raw:
                if not raw.isdigit() or not (5 <= int(raw) <= 1440):
                    err = _("Bitte Minuten zwischen 5 und 1440 angeben.")
            elif f.kind == "setting":
                from apps.core import assistant_pages

                allowed_values = {v for v, _l in assistant_pages.options(tenant, _target_pk(item))}
                if raw not in allowed_values:
                    err = _("Bitte eine Einstellung aus der Liste wählen.")
            elif f.kind == "category" and raw not in {
                v
                for v, _label in category_options(
                    None, items, 0 if spec.verb == "move" else i, existing
                )
            }:
                err = _("Bitte eine Kategorie aus der Liste wählen.")
            if err:
                errors[f"{i}:{f.name}"] = err
            values[f.name] = raw
        cleaned.append({"index": i, "spec": spec, "values": values, "item": item})
    return cleaned, errors


def _ref_pk(ref: str, created: dict[int, str]) -> str:
    if ref.startswith("pk:"):
        return ref[3:]
    if ref.startswith("item:"):
        idx = ref[5:]
        return created.get(int(idx), "") if idx.isdigit() else ""
    return ""


def snapshot(kind: str, obj) -> dict:
    """Канонический снимок полей объекта (сравнивается при откате)."""
    if kind == "product":
        # цена — с двумя знаками: из формы приходит Decimal("5"), из базы — Decimal("5.00")
        return {
            "name": dict(obj.name or {}),
            "description": dict(obj.description or {}),
            "base_price": str(Decimal(obj.base_price).quantize(Decimal("0.01"))),
            "category": str(obj.category_id or ""),
            "is_active": bool(obj.is_active),
            "stock": obj.stock_quantity,
            "sku": obj.sku or "",
            "images": len(obj.images or []),
        }
    if kind == "category":
        return {
            "name": dict(obj.name or {}),
            "description": dict(obj.description or {}),
            "parent": str(obj.parent_id or ""),
            "is_active": bool(obj.is_active),
            "images": len(obj.images or []),
        }
    return {
        "name": obj.name,
        "description": obj.description or "",
        "price_cents": int(obj.price_cents),
        "duration_minutes": int(obj.duration_minutes),
        "is_active": bool(obj.is_active),
        "images": len(obj.images or []) if isinstance(obj.images, list) else bool(obj.images),
    }


def _write(tenant, spec: ActionSpec, values: dict, created: dict[int, str], actor: str):
    from apps.booking import writers as booking_writers
    from apps.catalog import writers

    if spec.key == CATEGORY_CREATE:
        return writers.create_category(
            tenant,
            {"name_de": values["name"], "parent": _ref_pk(values.get("parent", ""), created)},
        )
    if spec.key == PRODUCT_CREATE:
        return writers.create_product(
            tenant,
            {
                "name_de": values["name"],
                "base_price": values.get("price", ""),
                "category": _ref_pk(values.get("category", ""), created),
            },
            actor=actor,
        )
    return booking_writers.create_service(
        tenant,
        {
            "name": values["name"],
            "price_eur": values.get("price", ""),
            "duration": values.get("duration", ""),
        },
    )


def _is_lock_timeout(exc: Exception) -> bool:
    cause = getattr(exc, "__cause__", None)
    code = getattr(cause, "sqlstate", None) or getattr(cause, "pgcode", None)
    # 55P03 — lock_timeout; 40P01 — взаимная блокировка с покупкой (снята сервером первой)
    return code in ("55P03", "40P01")


def _lock_tenant(tenant) -> None:
    from apps.tenants.models import Tenant

    with connection.cursor() as cur:
        cur.execute(f"SET LOCAL lock_timeout = '{LOCK_TIMEOUT}'")
    # NO KEY UPDATE: сериализует применения тенанта, но не мешает вставкам строк со
    # ссылкой на Tenant (FOR KEY SHARE: домены, биллинг, поддержка)
    Tenant.objects.select_for_update(no_key=True).only("pk").get(pk=tenant.pk)


def apply(request, job: str, entry: dict, post) -> dict:
    """«Alles übernehmen» → отчёт {change, items:[{action, kind, pk, name}]}.

    Бросает ApplyError(code, errors): expired | nothing | forbidden | invalid | busy."""
    from apps.core.audit import audit_event
    from apps.core.models import AssistantChange

    prior = AssistantChange.objects.filter(job=job).first()
    if prior is not None:
        if prior.user_id != request.user.pk:
            raise ApplyError("expired")
        return report(prior)  # повтор POST — тот же отчёт, ничего второй раз
    items = list(entry.get("actions") or [])
    if not items:
        raise ApplyError("expired")
    cleaned, errors = _clean(items, post, _existing_options(request.tenant), request.tenant)
    if errors:
        raise ApplyError("invalid", errors)
    if not cleaned:
        raise ApplyError("nothing")
    for row in cleaned:
        ok, _reason = allowed(request, row["spec"])
        if not ok or row["item"].get("blocked"):
            raise ApplyError("forbidden")
        if row["spec"].verb != "create":
            try:
                row["after"] = _canon(row["spec"], row["values"])
            except ValueError:
                errors[f"{row['index']}:price"] = _("Bitte einen Preis angeben.")
        if row["spec"].verb == "page":
            from apps.core import page_settings

            # ~10 EXISTS-запросов гейта — ДО блокировки строки Tenant (как page_settings.write)
            row["gate"] = page_settings.composition_gate(request.tenant.site_config or {})
        ref = row["values"].get("category") or row["values"].get("parent") or ""
        if ref.startswith("item:"):
            idx = ref[5:]
            if not idx.isdigit() or int(idx) not in {r["index"] for r in cleaned}:
                field = "parent" if row["spec"].key == CATEGORY_CREATE else "category"
                errors[f"{row['index']}:{field}"] = _(
                    "Die neue Kategorie wird nicht übernommen — bitte eine andere wählen."
                )
    if errors:
        raise ApplyError("invalid", errors)
    actor = getattr(request.user, "email", "") or str(request.user.pk)
    try:
        with transaction.atomic():
            _lock_tenant(request.tenant)
            change = AssistantChange.objects.create(
                user=request.user,
                job=job,
                undo_until=timezone.now() + timedelta(minutes=UNDO_MINUTES),
            )
            created: dict[int, str] = {}
            snaps = []
            targets = _lock_targets(
                [
                    (row["spec"].entity, (row["item"].get("target") or {}).get("pk", ""))
                    for row in cleaned
                    if row["spec"].verb != "create"
                ]
            )
            for row in cleaned:
                from apps.catalog.writers import WriteError

                if row["spec"].verb != "create":
                    snaps.append(_change(row, targets, request.tenant))
                    continue
                try:
                    obj = _write(request.tenant, row["spec"], row["values"], created, actor)
                except WriteError as exc:
                    raise ApplyError("invalid", _form_errors(row["index"], exc.errors)) from exc
                created[row["index"]] = str(obj.pk)
                kind = row["spec"].entity
                snaps.append(
                    {
                        "action": row["spec"].key,
                        "kind": kind,
                        "pk": str(obj.pk),
                        "name": row["values"]["name"],
                        "after": snapshot(kind, obj),
                    }
                )
            change.items = snaps
            change.save(update_fields=["items"])
            # аудит в той же транзакции и строго: без записи в журнал пакет не проводится
            audit_event(
                action="assistant.apply",
                resource_type="assistant_change",
                resource_id=str(change.pk),
                actor=request.user,
                changes={"items": [_audit_item(s) for s in snaps]},
                strict=True,
            )
    except IntegrityError:
        prior = AssistantChange.objects.filter(job=job, user=request.user).first()
        if prior is None:
            raise
        return report(prior)  # параллельный двойной клик: применил первый
    except OperationalError as exc:
        if _is_lock_timeout(exc):
            raise ApplyError("busy") from exc
        raise
    return report(change)


def _lock_targets(pairs: list[tuple[str, str]]) -> dict:
    """Строки целей изменений: по виду ОДНИМ запросом, по pk, FOR UPDATE (после Tenant)."""
    out = {}
    for kind in ("product", "category", "service"):
        pks = sorted({pk for k, pk in pairs if k == kind and pk})
        if not pks:
            continue
        for obj in _manager(kind).filter(pk__in=pks).order_by("pk").select_for_update():
            out[(kind, str(obj.pk))] = obj
    return out


def _manager(kind: str):
    from apps.booking.models import Service
    from apps.catalog.models import Category, Product

    return {
        "product": Product.all_objects,
        "category": Category.all_objects,
        "service": Service.objects,
    }[kind]


def _set_value(spec: ActionSpec, obj, canon: str, *, stamp: bool = True) -> None:
    """Узкая запись одного поля на заблокированной строке (save → post_save: журнал цен,
    листинг города; не update(), который обошёл бы сигналы)."""
    if spec.verb == "price":
        if spec.entity == "product":
            obj.base_price = Decimal(canon)
            obj.save(update_fields=["base_price", "updated_at"])
        else:
            obj.price_cents = int(canon)
            obj.save(update_fields=["price_cents", "updated_at"])
        return
    if spec.verb == "visibility":
        obj.is_active = bool(canon)
        fields = ["is_active", "updated_at"]
        # Г3: включение = подтверждение актуальности; откат скрытия — не подтверждение
        if stamp and obj.is_active and hasattr(obj, "confirmed_at"):
            from apps.core import freshness

            freshness.stamp(obj)
            fields.append("confirmed_at")
        obj.save(update_fields=fields)
        return
    obj.category_id = canon or None
    obj.save(update_fields=["category", "updated_at"])


def _page_raw(cfg: dict, code: str):
    """Сохранённое значение настройки как есть (весь подсловарь сетки — с рядами, темпом…)."""
    from apps.core import studio_pages

    setting = studio_pages.SETTINGS.get(code)
    if setting is None:
        return None
    node = cfg or {}
    for key in setting.site_key:
        if not isinstance(node, dict) or key not in node:
            return None
        node = node[key]
    return node


def _unset_page(cfg: dict, code: str) -> dict:
    """Убрать ключ настройки из конфига (её не было до пакета — presence-minimal)."""
    from apps.core import studio_pages

    out = dict(cfg or {})
    setting = studio_pages.SETTINGS.get(code)
    if setting is None:
        return out
    path = setting.site_key
    if len(path) == 1:
        out.pop(path[0], None)
        return out
    parent = dict(out.get(path[0]) or {})
    parent.pop(path[1], None)
    if parent:
        out[path[0]] = parent
    else:
        out.pop(path[0], None)
    return out


def _write_page(
    tenant, code: str, value: str, *, validate: bool = True, unset: bool = False, gate=None
) -> dict:
    """Настройка страницы внутри транзакции пакета (Tenant уже заблокирован): тот же путь,
    что `page_settings.write` — проверка по схеме, одна запись ключа, сброс кэша витрины."""
    from apps.core import page_settings
    from apps.core.pagecache import bump_storefront_cache
    from apps.tenants.models import Tenant

    # полная строка: проверки validate читают модули/тип бизнеса (без отложенных полей под замком)
    fresh = Tenant.objects.get(pk=tenant.pk)
    if unset:
        new_cfg = _unset_page(fresh.site_config or {}, code)
    else:
        cleaned = page_settings.validate(fresh, code, value, gate) if validate else value
        new_cfg = page_settings.apply_override(fresh.site_config or {}, code, cleaned)
    Tenant.objects.filter(pk=tenant.pk).update(site_config=new_cfg)
    schema = fresh.schema_name

    def _after_commit():
        bump_storefront_cache(schema)
        tenant.site_config = new_cfg  # в памяти — только после коммита (откат пакета не врёт)

    transaction.on_commit(_after_commit)
    return new_cfg


def _page_current(tenant, code: str) -> str:
    from apps.core import assistant_pages
    from apps.tenants.models import Tenant

    fresh = Tenant.objects.only("pk", "site_config").get(pk=tenant.pk)
    return assistant_pages.current(fresh, code)


def _page_stored(tenant, code: str):
    from apps.tenants.models import Tenant

    fresh = Tenant.objects.only("pk", "site_config").get(pk=tenant.pk)
    return _page_raw(fresh.site_config or {}, code)


def _page_options(tenant, code: str):
    from apps.core import assistant_pages

    return assistant_pages.options(tenant, code)


def _change_page(row: dict, tenant) -> dict:
    from apps.core import page_settings

    spec, item = row["spec"], row["item"]
    code = _target_pk(item)
    before = str(item.get("before") or "")
    if _page_current(tenant, code) != before:
        raise ApplyError(
            "invalid", {f"{row['index']}:value": _("Inzwischen geändert — bitte neu fragen.")}
        )
    try:
        new_cfg = _write_page(tenant, code, row["after"], gate=row.get("gate"))
    except page_settings.PageSettingError as exc:
        allowed_values = {v for v, _l in _page_options(tenant, code)}
        msg = (
            _("Bitte eine Einstellung aus der Liste wählen.")
            if allowed_values
            else _("Diese Einstellung ist hier nicht mehr verfügbar.")
        )
        raise ApplyError("invalid", {f"{row['index']}:value": msg}) from exc
    return {
        "action": spec.key,
        "kind": "page",
        "pk": code,
        "type": row["values"].get("type", ""),
        "name": row["values"].get("name", ""),
        "before": before,
        "before_set": bool(item.get("before_set", True)),
        "after": row["after"],
        # весь сохранённый блок после применения: откат сверяет его целиком (ряды, темп…)
        "after_raw": _page_raw(new_cfg, code),
    }


def _change(row: dict, targets: dict, tenant=None) -> dict:
    """Применить изменение: объект жив и значение то же, что видел владелец в предпросмотре."""
    from apps.core import assistant_changes

    spec, item = row["spec"], row["item"]
    if spec.verb == "page":
        return _change_page(row, tenant)
    pk = str((item.get("target") or {}).get("pk") or "")
    obj = targets.get((spec.entity, pk))
    field = spec.fields[0].name
    if obj is None or getattr(obj, "deleted_at", None):
        raise ApplyError("invalid", {f"{row['index']}:{field}": _("Inzwischen gelöscht.")})
    before = str(item.get("before") or "")
    if assistant_changes.current(spec.entity, spec.verb, obj) != before:
        raise ApplyError(
            "invalid",
            {f"{row['index']}:{field}": _("Inzwischen geändert — bitte neu fragen.")},
        )
    if spec.verb == "price":
        blocked = assistant_changes._price_blocked(spec.entity, obj)
        if not blocked and spec.entity == "service" and int(row["after"]) < obj.deposit_cents:
            blocked = _("Der Preis darf nicht unter der Anzahlung liegen.")
        if blocked:
            raise ApplyError("invalid", {f"{row['index']}:{field}": blocked})
    if spec.verb == "move" and row["after"]:
        from apps.catalog.models import Category

        # цель могли удалить между предпросмотром и кликом
        if not Category.objects.filter(pk=row["after"]).exists():
            raise ApplyError(
                "invalid",
                {f"{row['index']}:{field}": _("Bitte eine Kategorie aus der Liste wählen.")},
            )
    _set_value(spec, obj, row["after"])
    return {
        "action": spec.key,
        "kind": spec.entity,
        "pk": pk,
        "name": row["values"].get("name", ""),
        "before": before,
        "after": row["after"],
    }


def _audit_item(snap: dict) -> dict:
    """В журнал: действие и pk; у изменения — значения до/после (цена — восстановима из
    аудита и после 90-дневной чистки AssistantChange). Текста фразы нет."""
    out = {"action": snap["action"], "pk": snap["pk"]}
    if "before" in snap:
        out.update(before=snap["before"], after=snap["after"])
    return out


def _form_errors(index: int, errors: dict) -> dict:
    """Ошибки формы писателя → ошибки полей пакета (подпись — первая ошибка формы)."""
    mapping = {"name_de": "name", "name": "name", "base_price": "price", "price_eur": "price"}
    out = {}
    for field, errs in (errors or {}).items():
        msg = errs[0].get("message") if isinstance(errs, list) and errs else str(errs)
        out[f"{index}:{mapping.get(field, 'name')}"] = msg or _("Bitte prüfen.")
    return out or {f"{index}:name": _("Bitte prüfen.")}


def report(change) -> dict:
    return {
        "change": change.pk,
        "items": list(change.items or []),
        "undo_until": change.undo_until,
        "undone_at": change.undone_at,
        "undo_report": list(change.undo_report or []),
    }


def report_for(request, job: str) -> dict | None:
    """Отчёт применённого пакета этого пользователя (для показа) или None."""
    from apps.core.models import AssistantChange

    try:
        change = AssistantChange.objects.filter(job=job, user=request.user).first()
    except Exception:  # noqa: BLE001 — нет таблицы до миграции
        logger.warning("assistant actions: report read failed", exc_info=True)
        return None
    return report(change) if change else None


def present_report(request, rep: dict) -> dict:
    """Отчёт для шаблона: ссылки на созданное (с правами), можно ли откатить."""
    from django.urls import NoReverseMatch, reverse

    from apps.core import setup_assistant

    rows = []
    undone = {r.get("pk"): r for r in rep.get("undo_report") or []}
    existing = None
    if any(
        (ACTIONS.get(i.get("action")) or ACTIONS[PRODUCT_CREATE]).verb == "move"
        for i in rep.get("items") or []
    ):
        existing = _existing_options(None)
    for item in rep.get("items") or []:
        spec = ACTIONS.get(item.get("action"))
        if spec is None:
            continue
        url = ""
        if spec.verb == "page":
            url = _page_url(request, spec, str(item.get("type") or ""))
        elif setup_assistant.reachable(request, spec.edit_screen):
            try:
                url = reverse(spec.edit_screen, args=[item["pk"]])
            except NoReverseMatch:
                url = ""
        back = undone.get(item.get("pk"))
        change_text = ""
        if spec.verb != "create":
            code = str(item.get("pk") or "")
            before = _value_text(
                spec, str(item.get("before") or ""), existing, request.tenant, code
            )
            after = _value_text(spec, str(item.get("after") or ""), existing, request.tenant, code)
            change_text = f"{before} → {after}"
        rows.append(
            {
                "label": spec.label,
                "name": item.get("name", ""),
                "change_text": change_text,
                "url": url,
                "undone": bool(back and back.get("done")),
                "undo_note": (back or {}).get("reason", ""),
            }
        )
    now = timezone.now()
    can_undo = not rep.get("undone_at") and rep.get("undo_until") and now < rep["undo_until"]
    return {
        "rows": rows,
        "count": len(rows),
        "undo_until": rep.get("undo_until"),
        "undone": bool(rep.get("undone_at")),
        "can_undo": bool(can_undo),
    }


# ───────────────────────── откат ─────────────────────────


def _has_links(obj, *, allow=None) -> bool:
    """Есть ли на объект ссылки (обратные FK/M2M), кроме разрешённых `allow(model, qs)`."""
    relations = [
        f
        for f in obj._meta.get_fields(include_hidden=True)
        if f.auto_created and not f.concrete and (f.one_to_many or f.one_to_one or f.many_to_many)
    ]
    for rel in relations:
        try:
            if rel.one_to_one:
                if rel.related_model._default_manager.filter(**{rel.field.name: obj}).exists():
                    return True
                continue
            if rel.many_to_many:
                qs = rel.related_model._default_manager.filter(**{rel.field.name: obj})
            else:
                manager = getattr(rel.related_model, "all_objects", None)
                manager = manager if manager is not None else rel.related_model._default_manager
                qs = manager.filter(**{rel.field.name: obj})
            if allow is not None:
                qs = allow(rel.related_model, qs)
            if qs is not None and qs.exists():
                return True
        except Exception:  # noqa: BLE001 — не смогли проверить ссылку → считаем «используется»
            logger.warning("assistant actions: link check failed for %s", rel, exc_info=True)
            return True
    return False


def _product_allow(model, qs):
    label = model._meta.label_lower
    if label == "catalog.pricelog":
        return None  # первая запись журнала цен — своя (§ 11 PAngV, не чистится)
    if label == "inventory.stockmovement":
        # стартовое движение склада (первое из формы создания) — своё; любые последующие,
        # в т. ч. правка остатка в форме товара, — уже изменение
        first = qs.filter(source="catalog").order_by("created_at", "pk").first()
        return qs.exclude(pk=first.pk) if first else qs
    return qs


def _generic_links(kind: str, pk: str) -> bool:
    """Ссылки без FK (доп. услуги, отзывы). Сбой проверки — «используется» (не удаляем)."""
    from apps.core.models import Extra
    from apps.reviews.models import Review

    try:
        return (
            Extra.objects.filter(entity_kind=kind, entity_id=pk).exists()
            or Review.objects.filter(entity_kind=kind, entity_id=pk).exists()
        )
    except Exception:  # noqa: BLE001
        logger.warning("assistant actions: generic link check failed", exc_info=True)
        return True


def _undo_item(item: dict, obj, tenant=None) -> dict:
    """Откатить один пункт на уже заблокированной строке. → {pk, done, reason}."""
    from apps.catalog.models import Product

    kind, pk = item["kind"], item["pk"]
    out = {"pk": pk, "done": False, "reason": ""}
    if kind == "page":  # A-4c: настройка страницы — без строки объекта
        changed = (
            _page_stored(tenant, pk) != item["after_raw"]
            if "after_raw" in item
            else _page_current(tenant, pk) != str(item.get("after") or "")
        )
        if changed:
            out["reason"] = _("Inzwischen geändert — nicht zurückgesetzt.")
            return out
        # прежнее значение уже стояло — восстанавливаем без повторной проверки доступности
        _write_page(
            tenant,
            pk,
            str(item.get("before") or ""),
            validate=False,
            unset=not item.get("before_set", True),
        )
        out["done"] = True
        return out
    if obj is None or getattr(obj, "deleted_at", None):
        out["reason"] = _("Inzwischen gelöscht.")
        return out
    spec = ACTIONS.get(item.get("action"))
    if spec is not None and spec.verb != "create":
        return _undo_change(spec, item, obj, out)
    if snapshot(kind, obj) != item.get("after"):
        out["reason"] = _("Inzwischen geändert — nicht zurückgesetzt.")
        return out
    if kind == "product":
        if _has_links(obj, allow=_product_allow) or _generic_links("product", pk):
            out["reason"] = _("Schon verwendet (z. B. bestellt) — nicht zurückgesetzt.")
            return out
        obj.delete()  # мягкое удаление, как на экране
    elif kind == "category":
        if Product.objects.filter(category=obj).exists() or obj.children.filter().exists():
            out["reason"] = _("Enthält Produkte oder Unterkategorien — nicht zurückgesetzt.")
            return out
        obj.delete()
    else:
        if _has_links(obj) or _generic_links("service", pk):
            obj.is_active = False
            obj.save(update_fields=["is_active", "updated_at"])
            out.update(done=True, reason=_("Schon verwendet — ausgeblendet statt gelöscht."))
            return out
        obj.delete()
    out["done"] = True
    return out


def _undo_change(spec: ActionSpec, item: dict, obj, out: dict) -> dict:
    """Изменение: вернуть прежнее значение, только если с тех пор его не меняли."""
    from apps.core import assistant_changes

    if assistant_changes.current(spec.entity, spec.verb, obj) != str(item.get("after") or ""):
        out["reason"] = _("Inzwischen geändert — nicht zurückgesetzt.")
        return out
    _set_value(spec, obj, str(item.get("before") or ""), stamp=False)
    out["done"] = True
    if spec.verb == "price" and spec.entity == "product":
        try:
            lowered = Decimal(item["after"]) < Decimal(item["before"])
        except Exception:  # noqa: BLE001 — нет чисел — нет оговорки
            lowered = False
        if lowered:
            out["reason"] = _(
                "Zurückgesetzt. Der niedrigere Preis bleibt 30 Tage im Preisverlauf (§ 11 PAngV)."
            )
    return out


def undo(request, job: str) -> dict:
    """«Rückgängig»: обратный порядок, по снимку; → отчёт. ApplyError(expired|forbidden|busy)."""
    from apps.booking.models import Service
    from apps.catalog.models import Category, Product
    from apps.core.audit import audit_event
    from apps.core.models import AssistantChange

    models = {"product": Product.all_objects, "category": Category.all_objects}
    try:
        with transaction.atomic():
            _lock_tenant(request.tenant)
            change = (
                AssistantChange.objects.select_for_update()
                .filter(job=job, user=request.user)
                .first()
            )
            if change is None:
                raise ApplyError("expired")
            if change.undone_at:
                return report(change)  # повтор — no-op
            if timezone.now() >= change.undo_until:
                raise ApplyError("too_late")
            for item in change.items or []:
                spec = ACTIONS.get(item.get("action"))
                if spec is None or not allowed(request, spec)[0]:
                    raise ApplyError("forbidden")
            rows = list(change.items or [])
            locked = {}
            for kind in ("product", "category", "service"):
                pks = [r["pk"] for r in rows if r.get("kind") == kind]
                if not pks:
                    continue
                manager = models.get(kind) or Service.objects
                for obj in manager.filter(pk__in=pks).order_by("pk").select_for_update():
                    locked[(kind, str(obj.pk))] = obj
            results = [
                _undo_item(r, locked.get((r["kind"], r["pk"])), request.tenant)
                for r in reversed(rows)
            ]
            # ничего не откатилось (всё изменено/используется) — пакет НЕ помечаем отменённым:
            # владелец исправит причину и попробует ещё раз в том же окне
            if any(r["done"] for r in results):
                change.undone_at = timezone.now()
            change.undo_report = results
            change.save(update_fields=["undone_at", "undo_report"])
            audit_event(
                action="assistant.undo",
                resource_type="assistant_change",
                resource_id=str(change.pk),
                actor=request.user,
                changes={"items": [{"pk": r["pk"], "done": r["done"]} for r in results]},
                strict=True,
            )
    except OperationalError as exc:
        if _is_lock_timeout(exc):
            raise ApplyError("busy") from exc
        raise
    return report(change)


def error_text(code: str) -> str:
    return {
        "expired": _("Der Vorschlag ist abgelaufen — bitte neu fragen."),
        "nothing": _("Nichts ausgewählt."),
        "forbidden": _("Dafür fehlt Ihnen die Berechtigung."),
        "invalid": _("Bitte die markierten Felder prüfen."),
        "busy": _("Gerade in Benutzung — bitte gleich erneut versuchen."),
        "too_late": _("Rückgängig ist nur 10 Minuten lang möglich."),
        "quota": _("Zu viele Fragen in kurzer Zeit — bitte später erneut versuchen."),
        "sent": _("An den Support gesendet — die Antwort finden Sie unter „Support“."),
    }.get(code, _("Das hat nicht geklappt — bitte erneut versuchen."))


def purge(now=None) -> int:
    """Журнал пакетов — не дольше истории помощника (90 дней) в текущей схеме."""
    from apps.core import assistant_history
    from apps.core.models import AssistantChange

    cutoff = (now or timezone.now()) - timedelta(days=assistant_history.RETENTION_DAYS)
    deleted, _detail = AssistantChange.objects.filter(applied_at__lt=cutoff).delete()
    return deleted
