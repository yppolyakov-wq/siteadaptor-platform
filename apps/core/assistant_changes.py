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
#: глагол должен стоять рядом с именем объекта (в пределах стольких символов) — иначе
#: «Preise für Kaffee anzeigen lassen …» в длинном вопросе не превращается в команду
VERB_WINDOW = 40

_W = r"(?<!\w)"
_E = r"(?!\w)"
_PRICE = re.compile(
    _W + r"(?:preis\w*|kostet|kosten|price|costs?|цен[аеуы]\w*|стоит|стоимост\w*|цін[аиу]\w*"
    r"|коштує|fiyat\w*)" + _E,
    re.IGNORECASE,
)
_HIDE = re.compile(
    _W + r"(?:ausblenden|versteck\w*|deaktivier\w*|hide|disable|скр[ыо]\w*|спряч\w*"
    r"|спрятать|выключ\w*|убер[иу]|сховай\w*|сховати|приховай\w*|приховати|вимкн\w*|gizle\w*"
    r"|blende|aus)" + _E,
    re.IGNORECASE,
)
_SHOW = re.compile(
    _W + r"(?:einblenden|aktivier\w*|show|enable|покаж\w*|включ\w*"
    r"|верни|показати|увімкн\w*|göster\w*)" + _E,
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
    _W + r"(?:anlegen|erstell\w*|hinzufüg\w*|füge|add|create|созда\w*|добав\w*"
    r"|створ\w*|дода\w*|ekle\w*|oluştur\w*)" + _E + r"|\blege\b.*\ban\b",
    re.IGNORECASE,
)
#: «um 2 € erhöhen», «увеличь на 10 %» — относительное изменение: сумму не пересчитываем
_RELATIVE = re.compile(
    _W + r"(?:erhöh\w*|senk\w*|reduzier\w*|raise|lower|increase|reduce|decrease|увелич\w*"
    r"|уменьш\w*|сниз\w*|подним\w*|опусти\w*|збільш\w*|зменш\w*|знизь\w*|artır\w*"
    r"|düşür\w*|azalt\w*)" + _E + r"|\b(?:um|by)\s+\d|%",
    re.IGNORECASE,
)
_CURRENCY = r"(?:€|eur\b|euro\b|евро\b|евр\b\.?|євро\b|avro\b)"
#: «1.250 €» — тысячи с точкой (иначе общий разбор взял бы «250 €»)
_AMOUNT_K = re.compile(r"(?<![\d.,])(\d{1,3}(?:\.\d{3})+(?:,\d{1,2})?)\s*" + _CURRENCY, re.I)
#: после имени — продолжение названия с заглавной («Käsekuchen Mini»): это ДРУГОЙ товар
_NAME_TAIL_OK = frozenset({"preis", "price", "kategorie", "category", "euro", "eur"})


def _verb(text: str) -> str:
    """Глагол изменения. Создание — не наше; «Preis … ausblenden» без суммы — скрыть."""
    from apps.core import setup_assistant

    if _CREATE.search(text):
        return ""
    if _MOVE.search(text):
        return "move"
    has_amount = bool(setup_assistant._PRICE_RE.search(text))
    if _PRICE.search(text) and has_amount:
        return "price"
    if any(m.group(0).casefold() not in ("aus", "blende") for m in _HIDE.finditer(text)) or (
        _has_blende(text) and re.search(r"(?<!\w)aus(?!\w)", text, re.IGNORECASE)
    ):
        return "hide"
    if _SHOW.search(text):
        return "show"
    if _PRICE.search(text):
        return "price"
    return ""


def _has_blende(text: str) -> bool:
    return bool(re.search(r"(?<!\w)blende(?!\w)", text, re.IGNORECASE))


_VERB_RE = {"price": _PRICE, "hide": _HIDE, "show": _SHOW, "move": _MOVE}


def _near(text_cf: str, verb: str, start: int, end: int) -> bool:
    """Глагол (или для цены — сумма) в пределах VERB_WINDOW символов от имени."""
    from apps.core import setup_assistant

    patterns = [_VERB_RE[verb]]
    if verb == "price":
        patterns.append(setup_assistant._PRICE_RE)
    for pattern in patterns:
        for m in pattern.finditer(text_cf):
            gap = max(m.start() - end, start - m.end(), 0)
            if gap <= VERB_WINDOW:
                return True
    return False


def _names(value) -> list[str]:
    if isinstance(value, dict):
        return [str(v) for v in value.values() if v]
    return [str(value)] if value else []


_VERB_PERM = {"price": "preise.edit"}  # прочие изменения — sortiment.edit


def _kinds_for(tenant, user, verb: str) -> tuple[str, ...]:
    """Виды объектов, в которых ищем имя: модуль включён и пользователь вообще видит
    ассортимент (`sortiment.view`). Без него детектор молчит — сотрудник кухни не узнает
    через помощник даже о существовании скрытого товара. Право САМОГО действия (цена —
    `preise.edit`) проверяет `assistant_actions.allowed`: без него пункт без кнопки и без
    текущих значений (ревью безопасности A-4b)."""
    from apps.core.permissions import has_perm

    base = {"price": ("product", "service"), "move": ("product",)}.get(
        verb, ("product", "service", "category")
    )
    if user is None or not has_perm(user, "sortiment.view"):
        return ()
    module = {"product": "catalog", "category": "catalog", "service": "booking"}
    return tuple(k for k in base if tenant.is_module_active(module[k]))


def _index(tenant, kinds=("product", "category", "service")) -> list[dict]:
    """Имена существующих объектов нужных видов: [{kind, obj, names}] (живые, с капами;
    сначала недавно изменённые — их и правят)."""
    from apps.catalog.models import Category, Product

    rows = []
    if "product" in kinds:
        qs = Product.objects.only("pk", "name", "is_active", "base_price", "category_id")
        for obj in qs.order_by("-updated_at", "pk")[:MAX_PRODUCTS]:
            rows.append({"kind": "product", "obj": obj, "names": _names(obj.name)})
    if "category" in kinds:
        qs = Category.objects.only("pk", "name", "is_active")
        for obj in qs.order_by("-updated_at", "pk")[:MAX_CATEGORIES]:
            rows.append({"kind": "category", "obj": obj, "names": _names(obj.name)})
    if "service" in kinds:
        from apps.booking.models import Service

        qs = Service.objects.only(
            "pk", "name", "name_i18n", "is_active", "price_cents", "deposit_cents"
        )
        for obj in qs.order_by("-updated_at", "pk")[:MAX_SERVICES]:
            names = [obj.name, *_names(obj.name_i18n)]
            rows.append({"kind": "service", "obj": obj, "names": [n for n in names if n]})
    return rows


def _matches(low: str, rows: list[dict], kinds: tuple[str, ...]) -> tuple[list[dict], int, int]:
    """Объекты с самым длинным именем, встречающимся в УЖЕ casefold-тексте целыми словами
    (позиции — в нём же: casefold меняет длину «ß»). → (кандидаты, начало, конец)."""
    best, found, span = 0, [], (-1, -1)
    for row in rows:
        if row["kind"] not in kinds:
            continue
        for name in row["names"]:
            cf = name.strip().casefold()
            if len(cf) < 3 or len(cf) < best or cf not in low:
                continue
            m = re.search(r"(?<!\w)" + re.escape(cf) + r"(?!\w)", low)
            if not m:
                continue
            if len(cf) > best:
                best, found, span = len(cf), [], (m.start(), m.end())
            if row not in found:
                found.append(row)
    return found, span[0], span[1]


def _extends_name(text: str, found: list[dict]) -> bool:
    """«Käsekuchen Mini kostet 4 €» при существующем «Käsekuchen»: за именем идёт слово с
    заглавной — владелец называет ДРУГОЙ товар (это создание, а не изменение)."""
    for row in found:
        for name in row["names"]:
            m = re.search(r"(?<!\w)" + re.escape(name.strip()) + r"(?!\w)", text, re.I)
            if not m:
                continue
            nxt = re.match(r"\s+([^\W\d_][\w-]*)", text[m.end() :])
            if not nxt:
                return False
            word = nxt.group(1)
            return (
                word[:1].isupper()
                and word.casefold() not in _NAME_TAIL_OK
                and not any(p.fullmatch(word) for p in _VERB_RE.values())
            )
    return False


def _display(kind: str, obj) -> str:
    if kind == "service":
        return obj.name
    return obj.get_i18n("name")


def _looks_like_question(text: str) -> bool:
    from apps.core import setup_assistant

    # «Wie ändere ich den Preis von Käsekuchen, z. B. auf 3,50 €?» — вопрос о том, КАК
    return setup_assistant._looks_like_question(text) or bool(
        setup_assistant._QUESTION_START_RE.match(text)
    )


def _find(tenant, user, text: str):
    """(verb, kinds, rows, found, low, end) или None — общий разбор intent и build."""
    text = (text or "").strip()[:TEXT_MAX]
    verb = _verb(text) if len(text) >= 4 else ""
    if not verb or _looks_like_question(text):
        return None
    kinds = _kinds_for(tenant, user, verb)
    if not kinds:
        return None
    rows = _index(tenant, (*kinds, "category") if verb == "move" else kinds)
    low = text.casefold()
    found, start, end = _matches(low, rows, kinds)
    if not found or not _near(low, verb, start, end) or _extends_name(text, found):
        return None
    return verb, kinds, rows, found, low, end, text


def intent(tenant, user, text: str) -> bool:
    """Есть ли во фразе изменение существующего объекта (без ИИ). Никогда не бросает."""
    try:
        return _find(tenant, user, text) is not None
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


def _new_price(text: str) -> tuple[str, str]:
    """(новая цена как написал владелец, подсказка). Только ОДНА абсолютная сумма с €:
    относительное («um 2 € erhöhen», «на 10 %») и несколько сумм — не угадываем."""
    from apps.core import setup_assistant
    from apps.core.money import parse_money

    if _RELATIVE.search(text):
        return "", _("Bitte den neuen Preis eintragen — um wie viel, rechne ich nicht um.")
    amounts = [m.group(0) for m in setup_assistant._PRICE_RE.finditer(text)]
    thousands = _AMOUNT_K.search(text)
    if thousands:
        try:
            value = parse_money(thousands.group(1).replace(".", ""))
        except ValueError:
            value = None
        if value is not None and len(amounts) <= 1:
            return f"{value:.2f}".replace(".", ","), ""
    if len(amounts) > 1:
        return "", _("Mehrere Beträge gefunden — bitte den neuen Preis eintragen.")
    price = setup_assistant._price_in(text)
    return price, "" if price else _("Keinen Preis gefunden — bitte eintragen.")


def build(tenant, user, text: str) -> list[dict]:
    """Один пункт пакета из фразы (или [] — нечего менять)."""
    from apps.core import assistant_actions as aa

    got = _find(tenant, user, text)
    if got is None:
        return []
    verb, _kinds, rows, found, low, end, text = got
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
        price, note = _new_price(text)
        item["values"]["price"] = price
        item["note"] = note
        item["blocked"] = item["blocked"] or _price_blocked(kind, obj)
    elif verb in ("hide", "show"):
        want = "1" if verb == "show" else ""
        item["values"]["visible"] = want
        if want == item["before"]:
            item["blocked"] = _("Ist schon sichtbar.") if want else _("Ist schon ausgeblendet.")
    else:  # move — цель ищем ПОСЛЕ имени товара, в том же casefold-тексте
        cats, _s, _e = _matches(low[end:] if end >= 0 else "", rows, ("category",))
        ref = ""
        if len({c["obj"].pk for c in cats}) == 1:
            ref = f"pk:{cats[0]['obj'].pk}"
        item["values"]["category"] = ref
        if not ref:
            item["note"] = _("Zielkategorie nicht gefunden — bitte wählen.")
        elif ref == f"pk:{item['before']}":
            item["blocked"] = _("Ist schon in dieser Kategorie.")
    return [item]
