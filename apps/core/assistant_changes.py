"""AIS A-4b: «измени цену / скрой / перенеси» — пункты пакета для СУЩЕСТВУЮЩИХ объектов.

План — docs/ais-a4-ki-actions-plan-2026-11-06.md §11. Без ИИ: глагол изменения на пяти
языках кабинета + имя существующего товара/услуги/категории (самое длинное совпадение
целыми словами). Факты — сервером: цена только числом с €/евро из текста, категория-цель —
только существующая. Пакет применяет и откатывает `assistant_actions` (те же гейты, блокировки
и журнал, что у «создать»).
"""

from __future__ import annotations

import logging
import re
from decimal import Decimal

from django.utils.translation import gettext as _

logger = logging.getLogger(__name__)

MAX_PRODUCTS, MAX_SERVICES, MAX_CATEGORIES = 500, 200, 200
TEXT_MAX = 400

_W = r"(?<!\w)"
_E = r"(?!\w)"
_PRICE = re.compile(
    _W + r"(?:preis\w*|kostet|kosten|price|costs?|цен[аеуы]\w*|стоит|стоимост\w*|цін[аиу]\w*"
    r"|коштує|fiyat\w*)" + _E,
    re.IGNORECASE,
)
_HIDE = re.compile(
    _W + r"(?:ausblenden|versteck\w*|deaktivier\w*|offline|hide|disable|скр[ыо]\w*|спряч\w*"
    r"|спрятать|выключ\w*|убер[иу]|сховай\w*|сховати|приховай\w*|приховати|вимкн\w*|gizle\w*)"
    + _E
    + r"|\bblende\b.*\baus\b",
    re.IGNORECASE,
)
_SHOW = re.compile(
    _W + r"(?:einblenden|anzeigen|zeige|aktivier\w*|online|show|enable|покаж\w*|включ\w*"
    r"|верни|показати|увімкн\w*|göster\w*)" + _E + r"|\bblende\b.*\bein\b",
    re.IGNORECASE,
)
_MOVE = re.compile(
    _W
    + r"(?:verschieb\w*|move|перенес\w*|перенеси|перемест\w*|перемісти\w*|перенести|taşı\w*)"
    + _E,
    re.IGNORECASE,
)
#: глаголы СОЗДАНИЯ — фраза для A-4a («создай…»), не изменение
_CREATE = re.compile(
    _W + r"(?:anlegen|lege\s+\S+\s+an|erstell\w*|hinzufüg\w*|füge|add|create|созда\w*|добав\w*"
    r"|створ\w*|дода\w*|ekle\w*|oluştur\w*)" + _E,
    re.IGNORECASE,
)


def _verb(text: str) -> str:
    if _CREATE.search(text):
        return ""
    if _MOVE.search(text):
        return "move"
    if _PRICE.search(text):
        return "price"
    if _HIDE.search(text):
        return "hide"
    if _SHOW.search(text):
        return "show"
    return ""


def _names(value) -> list[str]:
    if isinstance(value, dict):
        return [str(v) for v in value.values() if v]
    return [str(value)] if value else []


def _index(tenant) -> list[dict]:
    """Имена существующих объектов: [{kind, obj, names}] (живые, с капами)."""
    from apps.catalog.models import Category, Product

    rows = []
    for obj in Product.objects.only("pk", "name", "is_active").order_by("pk")[:MAX_PRODUCTS]:
        rows.append({"kind": "product", "obj": obj, "names": _names(obj.name)})
    for obj in Category.objects.only("pk", "name", "is_active").order_by("pk")[:MAX_CATEGORIES]:
        rows.append({"kind": "category", "obj": obj, "names": _names(obj.name)})
    if tenant.is_module_active("booking"):
        from apps.booking.models import Service

        for obj in Service.objects.only("pk", "name", "name_i18n", "is_active").order_by("pk")[
            :MAX_SERVICES
        ]:
            names = [obj.name, *_names(obj.name_i18n)]
            rows.append({"kind": "service", "obj": obj, "names": [n for n in names if n]})
    return rows


def _matches(text: str, rows: list[dict], kinds: tuple[str, ...]) -> tuple[list[dict], int, int]:
    """Объекты с самым длинным именем, встречающимся в тексте целыми словами.
    → (кандидаты, позиция начала, позиция конца)."""
    low = text.casefold()
    best, found, span = 0, [], (-1, -1)
    for row in rows:
        if row["kind"] not in kinds:
            continue
        for name in row["names"]:
            cf = name.strip().casefold()
            if len(cf) < 3 or len(cf) < best:
                continue
            m = re.search(r"(?<!\w)" + re.escape(cf) + r"(?!\w)", low)
            if not m:
                continue
            if len(cf) > best:
                best, found, span = len(cf), [], (m.start(), m.end())
            if row not in found:
                found.append(row)
    return found, span[0], span[1]


def _display(kind: str, obj) -> str:
    if kind == "service":
        return obj.name
    return obj.get_i18n("name")


def intent(tenant, user, text: str) -> bool:
    """Есть ли во фразе изменение существующего объекта (без ИИ). Никогда не бросает."""
    from apps.core import setup_assistant

    text = (text or "").strip()[:TEXT_MAX]
    if len(text) < 4 or not _verb(text):
        return False
    # «Wie ändere ich den Preis von Käsekuchen?» — вопрос о том, КАК, а не просьба сделать
    if setup_assistant._looks_like_question(text):
        return False
    try:
        kinds = (
            ("product", "service") if _verb(text) == "price" else ("product", "service", "category")
        )
        if _verb(text) == "move":
            kinds = ("product",)
        return bool(_matches(text, _index(tenant), kinds)[0])
    except Exception:  # noqa: BLE001 — fail closed: обычный вопрос
        logger.warning("assistant changes: intent failed", exc_info=True)
        return False


def _price_blocked(kind: str, obj) -> str:
    if kind == "product":
        from apps.catalog.models import ProductVariant

        if ProductVariant.objects.filter(product_id=obj.pk, is_active=True).exists():
            return _("Hat Varianten — den Preis bitte im Formular ändern.")
        return ""
    from apps.booking.models import ServiceSeasonRate, ServiceVariant

    if (
        ServiceVariant.objects.filter(service_id=obj.pk).exists()
        or ServiceSeasonRate.objects.filter(service_id=obj.pk).exists()
    ):
        return _("Hat Varianten oder Saisonpreise — den Preis bitte im Formular ändern.")
    return ""


def current(kind: str, verb: str, obj) -> str:
    """Каноническое текущее значение поля действия (сравнение до/после, откат)."""
    if verb == "price":
        if kind == "product":
            return str(Decimal(obj.base_price).quantize(Decimal("0.01")))
        return str(int(obj.price_cents))
    if verb == "visibility":
        return "1" if obj.is_active else ""
    return str(obj.category_id or "")


def money_text(kind: str, canon: str) -> str:
    if not canon:
        return ""
    value = Decimal(canon) if kind == "product" else Decimal(int(canon)) / 100
    return f"{value:.2f}".replace(".", ",") + " €"


def build(tenant, user, text: str) -> list[dict]:
    """Один пункт пакета из фразы (или [] — нечего менять)."""
    from apps.core import assistant_actions as aa
    from apps.core import setup_assistant

    text = (text or "").strip()[:TEXT_MAX]
    verb = _verb(text)
    if not verb:
        return []
    rows = _index(tenant)
    kinds = {
        "price": ("product", "service"),
        "move": ("product",),
    }.get(verb, ("product", "service", "category"))
    found, _start, end = _matches(text, rows, kinds)
    if not found:
        return []
    row = found[0]
    kind, obj = row["kind"], row["obj"]
    name = _display(kind, obj)
    action = {
        "price": f"{kind}.price",
        "move": aa.PRODUCT_MOVE,
    }.get(verb, f"{kind}.visibility")
    item = {
        "action": action,
        "target": {"kind": kind, "pk": str(obj.pk)},
        "values": {"name": name},
        "note": "",
        "blocked": "",
    }
    if len({(r["kind"], r["obj"].pk) for r in found}) > 1:
        item["blocked"] = _("Mehrere Einträge heißen so — bitte im Sortiment ändern.")
    spec_verb = aa.ACTIONS[action].verb
    item["before"] = current(kind, spec_verb, obj)
    if verb == "price":
        price = setup_assistant._price_in(text)
        item["values"]["price"] = price
        if not price:
            item["note"] = _("Keinen Preis gefunden — bitte eintragen.")
        item["blocked"] = item["blocked"] or _price_blocked(kind, obj)
    elif verb in ("hide", "show"):
        want = "1" if verb == "show" else ""
        item["values"]["visible"] = want
        if want == item["before"]:
            item["blocked"] = _("Ist schon sichtbar.") if want else _("Ist schon ausgeblendet.")
    else:  # move
        rest = text[end:] if end >= 0 else ""
        cats, _s, _e = _matches(rest, rows, ("category",))
        ref = ""
        if len({c["obj"].pk for c in cats}) == 1:
            ref = f"pk:{cats[0]['obj'].pk}"
        item["values"]["category"] = ref
        if not ref:
            item["note"] = _("Zielkategorie nicht gefunden — bitte wählen.")
        elif ref == f"pk:{item['before']}":
            item["blocked"] = _("Ist schon in dieser Kategorie.")
    return [item]
