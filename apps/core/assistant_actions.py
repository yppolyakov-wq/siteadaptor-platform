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


@dataclass(frozen=True)
class FieldSpec:
    name: str  # имя поля пакета (не формы)
    label: object
    kind: str  # text | money | minutes | category
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
        if not request.tenant.is_module_active(spec.module):
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
        options = category_options(request.tenant, items, i, existing)
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
        prefill = {
            setup_assistant._NAME_FIELD[spec.entity]: values.get("name", ""),
        }
        price_field = setup_assistant._PRICE_FIELD.get(spec.entity)
        if price_field:
            prefill[price_field] = values.get("price", "")
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
                "form_url": setup_assistant._form_url(spec.entity, prefill)
                if setup_assistant.reachable(request, spec.screen)
                else "",
            }
        )
    return out


# ───────────────────────── применение ─────────────────────────


def merge_post(items: list[dict], post) -> list[dict]:
    """Значения полей спеки из POST поверх пунктов (по индексу); остальное — из кэша."""
    out = []
    for i, item in enumerate(items):
        spec = ACTIONS.get(item.get("action"))
        values = dict(item.get("values") or {})
        for f in spec.fields if spec else ():
            key = f"f_{i}_{f.name}"
            if key in post:
                values[f.name] = str(post.get(key) or "").strip()[:NAME_MAX]
        take = item.get("take", True)
        if post.get("items_present") == "1":
            take = bool(post.get(f"take_{i}"))
        out.append({**item, "values": values, "take": take})
    return out


def _clean(items: list[dict], post, existing: list) -> tuple[list[dict], dict]:
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
            elif f.kind == "category" and raw not in {
                v for v, _label in category_options(None, items, i, existing)
            }:
                err = _("Bitte eine Kategorie aus der Liste wählen.")
            if err:
                errors[f"{i}:{f.name}"] = err
            values[f.name] = raw
        cleaned.append({"index": i, "spec": spec, "values": values})
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
    cleaned, errors = _clean(items, post, _existing_options(request.tenant))
    if errors:
        raise ApplyError("invalid", errors)
    if not cleaned:
        raise ApplyError("nothing")
    for row in cleaned:
        ok, _reason = allowed(request, row["spec"])
        if not ok:
            raise ApplyError("forbidden")
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
            for row in cleaned:
                from apps.catalog.writers import WriteError

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
                changes={"items": [{"action": s["action"], "pk": s["pk"]} for s in snaps]},
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
    for item in rep.get("items") or []:
        spec = ACTIONS.get(item.get("action"))
        if spec is None:
            continue
        url = ""
        if setup_assistant.reachable(request, spec.edit_screen):
            try:
                url = reverse(spec.edit_screen, args=[item["pk"]])
            except NoReverseMatch:
                url = ""
        back = undone.get(item.get("pk"))
        rows.append(
            {
                "label": spec.label,
                "name": item.get("name", ""),
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


def _undo_item(item: dict, obj) -> dict:
    """Откатить один пункт на уже заблокированной строке. → {pk, done, reason}."""
    from apps.catalog.models import Product

    kind, pk = item["kind"], item["pk"]
    out = {"pk": pk, "done": False, "reason": ""}
    if obj is None or getattr(obj, "deleted_at", None):
        out["reason"] = _("Inzwischen gelöscht.")
        return out
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
            results = [_undo_item(r, locked.get((r["kind"], r["pk"]))) for r in reversed(rows)]
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
    }.get(code, _("Das hat nicht geklappt — bitte erneut versuchen."))


def purge(now=None) -> int:
    """Журнал пакетов — не дольше истории помощника (90 дней) в текущей схеме."""
    from apps.core import assistant_history
    from apps.core.models import AssistantChange

    cutoff = (now or timezone.now()) - timedelta(days=assistant_history.RETENTION_DAYS)
    deleted, _detail = AssistantChange.objects.filter(applied_at__lt=cutoff).delete()
    return deleted
