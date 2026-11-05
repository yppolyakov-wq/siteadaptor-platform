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
from decimal import Decimal

from django.db import transaction
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


def offer_kinds(tenant, user) -> list[str]:
    """Виды ввода, доступные этому пользователю: активное направление + модуль + право."""
    from apps.core import directions, setup_assistant

    allowed = set(setup_assistant.allowed_entities(tenant, user))
    return [
        d.key
        for d in directions.active(tenant)
        if d.key in ENTITY_FOR and ENTITY_FOR[d.key] in allowed
    ]


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


def rows_from_post(post) -> list[dict]:
    """Строки таблицы из POST (не больше MAX_LINES; лишнее — отказ выше)."""
    try:
        count = int(post.get("row_count", "0"))
    except ValueError:
        count = 0
    rows = []
    for i in range(min(max(count, 0), offer_lines.MAX_LINES)):
        rows.append(
            {
                "on": bool(post.get(f"row_{i}_on")),
                "name": post.get(f"row_{i}_name", ""),
                "price": post.get(f"row_{i}_price", ""),
                "duration": post.get(f"row_{i}_duration", ""),
                "guests": post.get(f"row_{i}_guests", ""),
                "starts_at": post.get(f"row_{i}_starts_at", ""),
                "example": bool(post.get(f"row_{i}_example")),
            }
        )
    return rows


def _existing_names(kind: str) -> set[str]:
    if ENTITY_FOR[kind] == "product":
        from apps.catalog.models import Product

        return {(p.name_text or "").casefold() for p in Product.objects.all().only("name")}
    if kind == "termine":
        from apps.booking.models import Service

        return {n.casefold() for n in Service.objects.values_list("name", flat=True)}
    if kind == "zimmer":
        from apps.stays.models import StayUnit

        return {n.casefold() for n in StayUnit.objects.values_list("name", flat=True)}
    from apps.events.models import Event

    return {n.casefold() for n in Event.objects.values_list("title", flat=True)}


def _cents(price: Decimal | None) -> int:
    return int((price or Decimal("0")) * 100)


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


def _ensure_staff(tenant, user) -> str:
    """Termine: без активного мастера слотов нет — создаём одного на имя владельца."""
    from apps.booking.models import Resource

    if Resource.objects.filter(is_active=True, type=Resource.TYPE_STAFF).exists():
        return ""
    name = staff_name(tenant, user)
    Resource.objects.create(name=name, type=Resource.TYPE_STAFF, capacity=1)
    return name


def confirm(request, tenant) -> Report:
    """Создать отмеченные строки черновика. Ничего не пишет при протухшем черновике."""
    from apps.core import readiness
    from apps.tenants.models import Tenant

    draft = get_draft(request)
    batch = request.POST.get("batch", "")
    if not draft or not batch or draft["batch"] != batch:
        return Report(error=_("Vorschau abgelaufen — bitte erneut prüfen."))
    kind = draft["kind"]
    if kind not in offer_kinds(tenant, request.user):
        return Report(error=_("Dafür fehlt Ihnen die Berechtigung."))
    rows = rows_from_post(request.POST)
    picked = [(i, r) for i, r in enumerate(rows) if r["on"]]
    report = Report()
    try:
        with transaction.atomic():
            locked = Tenant.objects.select_for_update().get(pk=tenant.pk)
            cfg = dict(locked.site_config or {})
            state = dict(cfg.get("onboarding") or {})
            ring = [x for x in state.get("offer_batches") or [] if isinstance(x, dict)]
            for done in ring:
                if done.get("id") == batch:
                    return Report.from_dict(done.get("report") or {})
            seen = _existing_names(kind)
            for i, row in picked:
                line = offer_lines.validate_row(row, kind, idx=i)
                if line.errors:
                    report.skipped.append((line.name or row["name"][:60], str(line.errors[0])))
                    continue
                key = line.name.casefold()
                if key in seen:
                    report.skipped.append((line.name, _("gibt es schon")))
                    continue
                _create(tenant, kind, line)
                seen.add(key)
                report.created.append(line.name)
                report.examples += int(row["example"])
            if kind == "termine" and report.created:
                report.staff = _ensure_staff(tenant, request.user)
            ring.append({"id": batch, "report": report.as_dict()})
            state["offer_batches"] = ring[-_BATCH_RING:]
            cfg["onboarding"] = state
            locked.site_config = cfg
            locked.save(update_fields=["site_config"])
            tenant.site_config = cfg
            transaction.on_commit(lambda: readiness.invalidate(tenant))
    except Exception:
        logger.exception("offer batch %s failed (kind=%s)", batch, kind)
        return Report(error=_("Nichts angelegt — bitte erneut versuchen."))
    clear_draft(request)
    return report
