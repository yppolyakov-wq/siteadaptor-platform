"""AIS-W W4-2: «Übernehmen» шага «Angebot prüfen» — создание пачки позиций.

Черновик (текст + batch_id) лежит в сессии; таблица присылает строки, сервер ЗАНОВО проверяет
каждую (`offer_lines.validate_row`) и создаёт отмеченные валидные одной транзакцией — по одной
`.create()` (не bulk_create: тот обходит save()/сигналы — slug товара, синк каталога города).
Двойное нажатие и две вкладки: batch_id под блокировкой строки Tenant → второй запрос видит
отметку и отдаёт прежний отчёт. Сбой БД → откат всей пачки и запись в лог; частичного
«7 из 12 тихо» не бывает. Отчёт сходится: created + skipped == отмеченных."""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from decimal import ROUND_HALF_UP, Decimal

from django.db import DatabaseError, transaction
from django.utils.translation import gettext as _

from apps.core import offer_lines

logger = logging.getLogger(__name__)

SESSION_KEY = "setup_offer_draft"
_BATCH_RING = 10

#: Вид ввода → сущность помощника `setup_assistant.ENTITIES` (модуль + право сотрудника).
ENTITY_FOR = {
    "waren": "product",
    "speisekarte": "product",
    "termine": "service",
    "zimmer": "room",
    "tickets": "event",
}


@dataclass
class Report:
    created: list[str] = field(default_factory=list)
    skipped: list[tuple[str, str]] = field(default_factory=list)
    examples: int = 0
    staff: str = ""
    error: str = ""
    replay: bool = False
    staff_missing: bool = False

    def as_dict(self) -> dict:
        return {
            "created": self.created,
            "skipped": [list(x) for x in self.skipped],
            "examples": self.examples,
            "staff": self.staff,
        }

    @classmethod
    def from_dict(cls, data: dict) -> Report:
        return cls(
            created=list(data.get("created") or []),
            skipped=[tuple(x) for x in data.get("skipped") or []],
            examples=int(data.get("examples") or 0),
            staff=str(data.get("staff") or ""),
            replay=True,
        )


def chosen_directions(tenant) -> list[str]:
    """Ответ «Wie verkaufen Sie?» из состояния мастера (ключи направлений)."""
    cfg = tenant.site_config if isinstance(tenant.site_config, dict) else {}
    raw = (cfg.get("onboarding") or {}).get("directions")
    return [k for k in raw if isinstance(k, str)] if isinstance(raw, list) else []


def offer_kinds(tenant, user) -> list[str]:
    """Виды ввода, доступные этому пользователю: активное направление + модуль + право.

    «Waren», выбранные в «Wie verkaufen Sie?», доступны и без включённой онлайн-продажи:
    каталог — базовый модуль, а продажу открывает отдельный шаг (W4-5)."""
    from apps.core import directions, setup_assistant

    allowed = set(setup_assistant.allowed_entities(tenant, user))
    keys = [d.key for d in directions.active(tenant)]
    if "waren" in chosen_directions(tenant) and "waren" not in keys:
        keys.insert(0, "waren")
    return [k for k in keys if k in ENTITY_FOR and ENTITY_FOR[k] in allowed]


#: Типы, у которых «Wie verkaufen Sie?» открыт сразу (направление не очевидно из типа).
ASK_TYPES = frozenset({"other", "cafe", "werkstatt", "tour_operator"})


def direction_choices(tenant) -> list:
    """Направления, осмысленные для типа бизнеса (меню — у гастро, столы — у ресторана/кафе)."""
    from apps.core import directions

    btype = tenant.business_type or ""
    out = []
    for d in directions.REGISTRY:
        if d.key == "speisekarte" and btype not in directions.MENU_TYPES:
            continue
        if d.key == "tisch" and btype not in directions.TABLE_TYPES:
            continue
        if d.key == "termine" and btype in directions.TABLE_TYPES:
            continue
        out.append(d)
    return out


def choose_directions(tenant, keys) -> list[str]:
    """Записать ответ «Wie verkaufen Sie?»: включить модули отмеченных направлений.

    Снятая галочка модуль не выключает (решение владельца). «Waren» онлайн-продажу не
    включает — её открывает шаг «Verkauf öffnen». Возвращает подписи направлений, которые
    включить не удалось (пакет и т. п.) — молча «включено» не говорим."""
    from apps.core import directions, modules, packages
    from apps.tenants.models import Tenant

    allowed = {d.key: d for d in direction_choices(tenant)}
    picked = [k for k in dict.fromkeys(keys) if k in allowed]
    problems = []
    for key in picked:
        if key == "waren":
            continue
        for module in allowed[key].modules:
            if not packages.module_allowed(tenant, module):
                problems.append(str(allowed[key].label))
                break
            modules.enable_module(tenant, module)
    with transaction.atomic():
        locked = Tenant.objects.select_for_update().get(pk=tenant.pk)
        cfg = dict(locked.site_config or {})
        state = dict(cfg.get("onboarding") or {})
        state["directions"] = picked
        cfg["onboarding"] = state
        locked.site_config = cfg
        locked.save(update_fields=["site_config"])
    tenant.site_config = cfg
    tenant.disabled_modules = locked.disabled_modules
    for key in picked:
        if key not in ("waren",) and str(allowed[key].label) not in problems:
            if not directions.is_active(tenant, key):
                problems.append(str(allowed[key].label))
    return problems


def new_draft(request, kind: str, text: str) -> dict:
    draft = {"batch": uuid.uuid4().hex, "kind": kind, "text": text[: offer_lines.MAX_TEXT]}
    request.session[SESSION_KEY] = draft
    return draft


def get_draft(request) -> dict | None:
    draft = request.session.get(SESSION_KEY)
    if not isinstance(draft, dict) or draft.get("kind") not in ENTITY_FOR:
        return None
    return draft


def clear_draft(request) -> None:
    request.session.pop(SESSION_KEY, None)


class TooManyRows(ValueError):
    """Отмеченных строк больше MAX_LINES — отказ целиком (не обрезаем молча)."""


def rows_from_post(post) -> list[dict]:
    """Строки таблицы из POST. Индексы берутся по самим ключам (`row_<i>_name`), а не только
    по `row_count`: подделанный/обрезанный счётчик не прячет отмеченную строку из отчёта."""
    try:
        count = int(post.get("row_count", "0"))
    except ValueError:
        count = 0
    seen = {
        int(k.split("_")[1])
        for k in post
        if k.startswith("row_") and k.split("_")[1].isdigit() and len(k.split("_")[1]) <= 4
    }
    total = max([count, *(i + 1 for i in seen)]) if (seen or count > 0) else 0
    if total > offer_lines.MAX_LINES:
        if any(post.get(f"row_{i}_on") for i in range(offer_lines.MAX_LINES, total)):
            raise TooManyRows(total)
        total = offer_lines.MAX_LINES
    return [
        {
            "on": bool(post.get(f"row_{i}_on")),
            "name": post.get(f"row_{i}_name", ""),
            "price": post.get(f"row_{i}_price", ""),
            "duration": post.get(f"row_{i}_duration", ""),
            "guests": post.get(f"row_{i}_guests", ""),
            "starts_at": post.get(f"row_{i}_starts_at", ""),
        }
        for i in range(total)
    ]


def _existing_names(kind: str) -> set[str]:
    if ENTITY_FOR[kind] == "product":
        from apps.catalog.models import Product

        return {(p.name_text or "").casefold() for p in Product.objects.all()}
    if kind == "termine":
        from apps.booking.models import Service

        return {n.casefold() for n in Service.objects.values_list("name", flat=True)}
    if kind == "zimmer":
        from apps.stays.models import StayUnit

        return {n.casefold() for n in StayUnit.objects.values_list("name", flat=True)}
    from apps.events.models import Event

    return {n.casefold() for n in Event.objects.values_list("title", flat=True)}


def _cents(price: Decimal | None) -> int:
    return int(((price or Decimal("0")) * 100).to_integral_value(ROUND_HALF_UP))


def _create(tenant, kind: str, line: offer_lines.Line) -> None:
    if ENTITY_FOR[kind] == "product":
        from apps.catalog.models import Product
        from apps.core.archetypes import FOOD_BUSINESS_TYPES

        vat = Decimal("7.00") if tenant.business_type in FOOD_BUSINESS_TYPES else Decimal("19.00")
        Product.objects.create(name={"de": line.name}, base_price=line.price, vat_rate=vat)
    elif kind == "termine":
        from apps.booking.models import Service

        Service.objects.create(
            name=line.name, duration_minutes=line.duration_min, price_cents=_cents(line.price)
        )
    elif kind == "zimmer":
        from apps.stays.models import StayUnit

        StayUnit.objects.create(
            name=line.name, price_cents=_cents(line.price), max_guests=line.guests
        )
    else:
        from apps.events.models import Event

        Event.objects.create(
            title=line.name,
            starts_at=line.starts_at,
            price_cents=_cents(line.price),
            status=Event.STATUS_PUBLISHED,
        )


def staff_name(tenant, user) -> str:
    """Имя авто-мастера (решение владельца: не «Ich» — имя владельца, иначе бизнес)."""
    full = " ".join(
        x for x in (getattr(user, "first_name", ""), getattr(user, "last_name", "")) if x
    ).strip()
    return (full or tenant.name or _("Team"))[:100]


def _ensure_staff(tenant, user) -> str | None:
    """Termine: без активного мастера слотов нет — создаём одного на имя владельца.

    "" — мастер уже есть; None — создать нельзя (ресурсы правит право настроек, а не
    ассортимента: сотрудник без него не заводит ресурс мимо своего экрана)."""
    from apps.booking.models import Resource
    from apps.core.permissions import has_perm

    if Resource.objects.filter(is_active=True, type=Resource.TYPE_STAFF).exists():
        return ""
    if not has_perm(user, "einstellungen.edit"):
        return None
    name = staff_name(tenant, user)
    Resource.objects.create(name=name, type=Resource.TYPE_STAFF, capacity=1)
    return name


def _example_names(tenant, kind: str) -> set[str]:
    """Имена образцов «Beispiele einfügen» — считаем их на сервере, не по флагу из POST."""
    from apps.core import offer_examples

    text = offer_examples.examples_for(tenant.business_type, kind)
    return {x.name.casefold() for x in offer_lines.parse_lines(text, kind).lines}


def confirm(request, tenant) -> Report:
    """Создать отмеченные строки черновика. Ничего не пишет при протухшем черновике,
    пустом выборе или если ни одна строка не создана (черновик остаётся — можно поправить)."""
    from apps.core import readiness
    from apps.tenants.models import Tenant

    draft = get_draft(request)
    batch = request.POST.get("batch", "")
    if not draft or not batch or draft.get("batch") != batch:
        return Report(error=_("Vorschau abgelaufen — bitte erneut prüfen."))
    kind = draft["kind"]
    if kind not in offer_kinds(tenant, request.user):
        return Report(error=_("Dafür fehlt Ihnen die Berechtigung."))
    try:
        rows = rows_from_post(request.POST)
    except TooManyRows:
        return Report(error=_("Höchstens 50 Zeilen auf einmal — bitte aufteilen."))
    picked = [(i, r) for i, r in enumerate(rows) if r["on"]]
    if not picked:
        return Report(error=_("Keine Zeile ausgewählt."))
    examples = _example_names(tenant, kind)
    report = Report()
    replay = None
    try:
        with transaction.atomic():
            locked = Tenant.objects.select_for_update().get(pk=tenant.pk)
            cfg = dict(locked.site_config or {})
            state = dict(cfg.get("onboarding") or {})
            ring = [x for x in state.get("offer_batches") or [] if isinstance(x, dict)]
            replay = next((x for x in ring if x.get("id") == batch), None)
            if replay is None:
                _create_rows(tenant, kind, picked, examples, report)
                if kind == "termine" and report.created:
                    staff = _ensure_staff(tenant, request.user)
                    if staff is None:
                        report.staff_missing = True
                    report.staff = staff or ""
                if report.created:
                    ring.append({"id": batch, "report": report.as_dict()})
                    state["offer_batches"] = ring[-_BATCH_RING:]
                    cfg["onboarding"] = state
                    locked.site_config = cfg
                    locked.save(update_fields=["site_config"])
                    tenant.site_config = cfg
                    transaction.on_commit(lambda: readiness.invalidate(tenant))
    except DatabaseError:
        logger.exception("offer batch %s failed (kind=%s)", batch, kind)
        return Report(error=_("Nichts angelegt — bitte erneut versuchen."))
    if replay is not None:
        clear_draft(request)
        return Report.from_dict(replay.get("report") or {})
    if report.created:
        clear_draft(request)
    return report


def _create_rows(tenant, kind, picked, examples, report) -> None:
    """Каждая строка — свой savepoint: сбой одной (длина поля, переполнение) не валит пачку
    и попадает в отчёт с причиной; остальные создаются."""
    seen = _existing_names(kind)
    for i, row in picked:
        line = offer_lines.validate_row(row, kind, idx=i)
        label = line.name or row["name"][:60] or f"#{i + 1}"
        if line.errors:
            report.skipped.append((label, str(line.errors[0])))
            continue
        key = line.name.casefold()
        if key in seen:
            report.skipped.append((line.name, _("gibt es schon")))
            continue
        try:
            with transaction.atomic():
                _create(tenant, kind, line)
        except DatabaseError:
            logger.exception("offer batch row failed (kind=%s, row=%s)", kind, i)
            report.skipped.append((line.name, _("konnte nicht angelegt werden")))
            continue
        seen.add(key)
        report.created.append(line.name)
        report.examples += int(key in examples)
