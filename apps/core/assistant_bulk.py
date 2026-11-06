"""AIS A-4d: «alle Kuchen 10 % teurer / скрой все товары категории Торты» — массовое изменение
товаров одной категории (≤ 50) с предпросмотром.

План — docs/ais-a4-ki-actions-plan-2026-11-06.md §13. Без ИИ: слово «все» на пяти языках +
имя СУЩЕСТВУЮЩЕЙ категории + действие (цена ± % / ± € / = €, скрыть, показать). Сервер сам
разворачивает категорию (она и её прямые подкатегории — как страница категории KAT-1) в
обычные пункты `product.price` / `product.visibility`: применение, блокировки, журнал и
«Rückgängig» — те же, что у одиночного изменения (A-4b). Формула цены — общая с массовой
правкой экрана «Sortiment» (`catalog.bulk_price`, WR-6).
"""

from __future__ import annotations

import logging
import re
from decimal import Decimal

from django.utils.translation import gettext as _

logger = logging.getLogger(__name__)

BULK_MAX = 50  # решение владельца: массовые — не больше 50 за раз, с предпросмотром
TEXT_MAX = 400
#: «все» рядом с категорией (иначе «alle» из другого места фразы); с любой стороны —
#: tr «Kuchen kategorisindeki tüm ürünler» ставит его после имени
QUANT_WINDOW = 60

_W, _E = r"(?<!\w)", r"(?!\w)"
_ALL = re.compile(
    _W + r"(?:alle|allen|aller|sämtlich\w*|all|every|все|всех|всё|весь|вся|всю"
    r"|усі|всі|увесь|tüm|bütün|hepsi\w*)" + _E,
    re.IGNORECASE,
)
_UP = re.compile(
    _W + r"(?:erhöh\w*|teurer|anheb\w*|raise|increase|pricier|увелич\w*|подним\w*"
    r"|подними|повыс\w*|дороже|збільш\w*|підвищ\w*|підніми|дорожч\w*|artır\w*|zam(?:la\w*)?"
    r"|pahalı\w*)" + _E,
    re.IGNORECASE,
)
_DOWN = re.compile(
    _W + r"(?:senk\w*|reduzier\w*|billiger|günstiger|verbillig\w*|lower|reduce|decrease"
    r"|cheaper|уменьш\w*|сниз\w*|снизь|сбавь|дешевле|опусти\w*|зменш\w*|зниз\w*|знизь"
    r"|дешевш\w*|düşür\w*|azalt\w*|indir(?!im)\w*|ucuz\w*)" + _E,
    re.IGNORECASE,
)
#: «покажи все товары категории X» — это «посмотреть», а не «включить»: массовое «показать»
#: только с явным «снова/wieder» или глаголом включения
_REACTIVATE = re.compile(
    _W + r"(?:wieder|erneut|einblenden|aktivier\w*|again|enable|reactivate|снова|опять|включ\w*"
    r"|верни|знову|увімкн\w*|tekrar|yeniden|aktif)" + _E,
    re.IGNORECASE,
)
#: ru/uk «на 2 €» без «дороже/дешевле» — «на сколько» или «до скольких», не угадываем
_NA_AMOUNT = re.compile(r"(?<!\w)на\s+[+\-−]?\d", re.IGNORECASE)
_CURRENCY = r"(?:€|eur\b|euro\b|евро\b|євро\b|avro\b)"
#: знак — только вплотную к числу и не после слова/дефиса: «Kuchen- 10 %», «Torten - 10 %»
#: минусом не считаются; «1.250 €» — тысячи (иначе взяли бы «250 €»)
_SIGN = r"(?:(?<![\w\-−+])(?P<sign>[+\-−]))?"
_NUM = r"(?<![\d.,])(?P<num>\d{1,3}(?:\.\d{3})+(?:,\d{1,2})?|\d{1,6}(?:[.,]\d{1,2})?)(?![\d.,]\d)"
#: «+10 %», «−10%», «10 Prozent», «на 10 процентов», tr «%10»
_PCT = re.compile(
    _SIGN + _NUM + r"\s*(?:%|prozent\b|percent\b|процент\w*|відсот\w*|yüzde\b)"
    r"|%\s*(?P<tr>\d{1,3}(?:[.,]\d{1,2})?)(?![\d.,]\d)",
    re.IGNORECASE,
)
_EUR = re.compile(_SIGN + _NUM + r"\s*" + _CURRENCY, re.IGNORECASE)


def _quantified(low: str, start: int, end: int) -> bool:
    return any(max(m.start() - end, start - m.end(), 0) <= QUANT_WINDOW for m in _ALL.finditer(low))


def _category(tenant, low: str):
    """(категория, начало, конец) — ровно одна существующая категория целыми словами."""
    from apps.core import assistant_changes

    rows = assistant_changes._index(tenant, ("category",))
    found, start, end = assistant_changes._matches(low, rows, ("category",))
    if len({r["obj"].pk for r in found}) != 1:
        return None, -1, -1
    return found[0]["obj"], start, end


def _verb(text: str) -> str:
    """price | hide | show | "" (создание и перенос — не массовое действие v1)."""
    from apps.core import assistant_changes

    if assistant_changes._CREATE.search(text) or assistant_changes._MOVE.search(text):
        return ""
    has_amount = bool(_PCT.search(text) or _EUR.search(text))
    verb = assistant_changes._verb(text)
    hide_show = verb in ("hide", "show")
    if hide_show and has_amount and not assistant_changes._PRICE.search(text):
        return ""  # «blende alle Kuchen unter 2 € aus» — фильтр по цене не поддержан: не наше
    if has_amount or assistant_changes._PRICE.search(text):
        return "price"
    if verb == "show" and not _REACTIVATE.search(text):
        return ""
    return verb if hide_show else ""


def _number(raw: str) -> Decimal | None:
    from apps.core.money import parse_money

    try:
        value = parse_money(raw)
    except ValueError:
        return None
    return value if value is not None and value.is_finite() else None


def price_change(text: str) -> tuple[str, Decimal | None, str]:
    """(режим, сумма, причина отказа): «+10 %» → pct 10, «2 € billiger» → eur −2,
    «auf 3 €» → set 3. Направление — знаком или словом; нет направления у процента или
    у суммы со словом «um/на» — не угадываем."""
    from apps.catalog import bulk_price
    from apps.core import assistant_changes

    pcts, eurs = list(_PCT.finditer(text)), list(_EUR.finditer(text))
    if len(pcts) + len(eurs) != 1:
        if not pcts and not eurs:
            return "", None, _("Um wie viel? Zum Beispiel „alle Kuchen 10 Prozent teurer“.")
        return "", None, _("Mehrere Beträge gefunden — bitte nur einen nennen.")
    m = (pcts or eurs)[0]
    sign = m.group("sign") or ""
    raw = m.group("num") or (m.groupdict().get("tr") or "")
    if re.fullmatch(r"\d{1,3}(?:\.\d{3})+(?:,\d{1,2})?", raw):
        raw = raw.replace(".", "")
    amount = _number(raw)
    if amount is None:
        return "", None, _("Den Betrag verstehe ich nicht — bitte z. B. „10 Prozent“ oder „2 €“.")
    up, down = bool(_UP.search(text)), bool(_DOWN.search(text))
    word = 0 if up == down else (1 if up else -1)
    signed = (-1 if sign in "-−" else 1) if sign else 0
    if signed and word and signed != word:  # «+10 % billiger» — не выбираем молча
        return "", None, _("Teurer oder günstiger? Zum Beispiel „alle Kuchen 10 Prozent teurer“.")
    direction = signed or word
    if pcts:
        if not direction:
            return (
                "",
                None,
                _("Teurer oder günstiger? Zum Beispiel „alle Kuchen 10 Prozent teurer“."),
            )
        mode, value = "pct", amount * direction
    elif direction or assistant_changes._RELATIVE.search(text) or _NA_AMOUNT.search(text):
        if not direction:
            return "", None, _("Teurer oder günstiger? Zum Beispiel „alle Kuchen 2 € teurer“.")
        mode, value = "eur", amount * direction
    else:
        mode, value = "set", amount
    if not bulk_price.valid(mode, value):
        if mode == "pct":
            return "", None, _("Prozent zwischen −90 und 500.")
        return "", None, _("Bitte einen Betrag zwischen 0 und 100.000 € angeben.")
    return mode, value, ""


def direction_missing(text: str) -> bool:
    """Одна сумма/процент без знака и без слова «teurer/günstiger» — спрашиваем направление."""
    from apps.core import assistant_changes

    pcts, eurs = list(_PCT.finditer(text)), list(_EUR.finditer(text))
    if len(pcts) + len(eurs) != 1:
        return False
    m = (pcts or eurs)[0]
    if m.group("sign"):
        return False
    if bool(_UP.search(text)) != bool(_DOWN.search(text)):
        return False
    return bool(pcts) or bool(assistant_changes._RELATIVE.search(text) or _NA_AMOUNT.search(text))


def change_text(mode: str, value: Decimal) -> str:
    num = f"{abs(value):.2f}".rstrip("0").rstrip(".").replace(".", ",")
    if mode == "pct":
        return f"{'+' if value >= 0 else '−'}{num} %"
    if mode == "eur":
        return f"{'+' if value >= 0 else '−'}{abs(value):.2f} €".replace(".", ",")
    return f"= {value:.2f} €".replace(".", ",")


def _find(tenant, user, text: str):
    """(verb, category, text) или None — общий разбор intent и build."""
    from apps.core import assistant_changes
    from apps.core.permissions import has_perm

    text = (text or "").strip()[:TEXT_MAX]
    if len(text) < 6 or not _ALL.search(text):
        return None
    if assistant_changes._looks_like_question(text):
        return None
    verb = _verb(text)
    if not verb:
        return None
    # без права видеть ассортимент и без каталога детектор молчит (как A-4b)
    if user is None or not has_perm(user, "sortiment.view"):
        return None
    if not tenant.is_module_active("catalog"):
        return None
    from apps.core import assistant_pages

    # «покажи все товары категории Торты списком» — это вид страницы (A-4c), не «включить»
    if verb == "show" and assistant_pages.intent(tenant, user, text):
        return None
    low = text.casefold()
    cat, start, end = _category(tenant, low)
    if cat is None or not _quantified(low, start, end):
        return None
    return verb, cat, text


def intent(tenant, user, text: str) -> bool:
    """Есть ли во фразе массовое изменение категории (без ИИ). Никогда не бросает."""
    try:
        return _find(tenant, user, text) is not None
    except Exception:  # noqa: BLE001 — fail closed: обычный вопрос
        logger.warning("assistant bulk: intent failed", exc_info=True)
        return False


def _products(cat):
    """Живые товары категории и её прямых подкатегорий (страница категории KAT-1)."""
    from django.db.models import Q

    from apps.catalog.models import Product

    qs = Product.objects.filter(
        Q(category_id=cat.pk)
        # удалённая подкатегория не видна на витрине — её товары не трогаем
        | Q(category__parent_id=cat.pk, category__deleted_at__isnull=True)
    )
    rows = list(
        qs.only("pk", "name", "is_active", "base_price", "category_id").order_by("pk")[
            : BULK_MAX + 1
        ]
    )  # огромная категория не грузится в память целиком: число — отдельным COUNT
    return rows, (qs.count() if len(rows) > BULK_MAX else len(rows))


def _notice(action: str, title: str, reason: str) -> list[dict]:
    """Пункт без кнопки: объясняет, почему массово не получится."""
    return [
        {
            "action": action,
            "target": {"kind": "product", "pk": ""},
            "values": {"name": title},
            "before": "",
            "note": "",
            "blocked": reason,
            "bulk": {"title": title, "change": "", "count": 0, "skipped": []},
        }
    ]


def build(tenant, user, text: str) -> list[dict]:
    """Пункты пакета: по одному на товар категории (≤ 50), или [] — не наше."""
    got = _find(tenant, user, text)
    if got is None:
        return []
    verb, cat, text = got
    return expand(tenant, cat, verb, text)


def expand(tenant, cat, verb: str, text: str) -> list[dict]:
    """Категория → пункты по товарам (≤ 50) — общая развёртка правил (A-4d) и ИИ (A-4e):
    количество и цены считает сервер, а не модель. verb: price | hide | show."""
    from apps.catalog import bulk_price
    from apps.catalog.models import ProductVariant
    from apps.core import assistant_actions as aa
    from apps.core import assistant_changes

    title = _("Alle Produkte in „%(name)s“") % {"name": cat.get_i18n("name")}
    action = aa.PRODUCT_PRICE if verb == "price" else aa.PRODUCT_VISIBILITY
    products, total = _products(cat)
    if total > BULK_MAX:
        return _notice(
            action,
            title,
            _(
                "Das sind %(n)s Produkte — mehr als %(max)s auf einmal ändere ich nicht. "
                "Bitte im Sortiment mehrere auswählen."
            )
            % {"n": total, "max": BULK_MAX},
        )
    mode, value, reason = ("", None, "")
    if verb == "price":
        mode, value, reason = price_change(text)
        if reason:
            items = _notice(action, title, reason)
            if direction_missing(text):  # A-5b: «um 10 %» — спросить «teurer/günstiger?»
                items[0]["clarify"] = {
                    "slot": "direction",
                    "options": [
                        {"id": "up", "label": _("teurer")},
                        {"id": "down", "label": _("günstiger")},
                    ],
                    "cat": str(cat.pk),
                    "text": text,
                }
            return items
    with_variants = set()
    if verb == "price":
        with_variants = set(
            ProductVariant.objects.filter(
                product_id__in=[p.pk for p in products], is_active=True
            ).values_list("product_id", flat=True)
        )
    items, unchanged, zero, too_high = [], 0, 0, 0
    for product in sorted(products, key=lambda p: p.get_i18n("name").casefold()):
        if product.pk in with_variants:
            continue
        before = assistant_changes.current("product", aa.ACTIONS[action].verb, product)
        values = {"name": product.get_i18n("name")}
        if verb == "price":
            new = bulk_price.new_price(product.base_price, mode, value)
            if str(new) == before:
                unchanged += 1
                continue
            if new <= 0 < Decimal(before) and mode != "set":
                zero += 1  # «2 € billiger» не делает товар бесплатным молча
                continue
            if new > aa.MAX_PRICE:
                too_high += 1  # иначе одна строка уронила бы весь пакет без объяснения
                continue
            values["price"] = f"{new:.2f}".replace(".", ",")
        else:
            want = "1" if verb == "show" else ""
            if want == before:
                unchanged += 1
                continue
            values["visible"] = want
        items.append(
            {
                "action": action,
                "target": {"kind": "product", "pk": str(product.pk)},
                "values": values,
                "before": before,
                "note": "",
                "blocked": "",
                # цену/видимость посчитал сервер: POST её не меняет (предпросмотр == запись)
                "fixed": True,
            }
        )
    skipped = []
    if with_variants:
        skipped.append(
            _("%(n)s mit Varianten — den Preis bitte im Formular ändern.")
            % {"n": len(with_variants)}
        )
    if unchanged:
        skipped.append(_("%(n)s schon so — bleiben unverändert.") % {"n": unchanged})
    if zero:
        skipped.append(_("%(n)s würden 0 € kosten — bleiben unverändert.") % {"n": zero})
    if too_high:
        skipped.append(
            _("%(n)s würden über 100.000 € kosten — bleiben unverändert.") % {"n": too_high}
        )
    if not items:
        return _notice(action, title, " ".join(skipped) or _("In dieser Kategorie ist nichts."))
    change = change_text(mode, value) if verb == "price" else ""
    if verb == "hide":
        change = _("ausblenden")
    elif verb == "show":
        change = _("wieder anzeigen")
    items[0]["bulk"] = {
        "title": title,
        "change": change,
        "count": len(items),
        "skipped": skipped,
    }
    return items


def meta(items: list[dict]) -> dict | None:
    """Шапка массового пакета (первый пункт несёт её), или None — обычный пакет."""
    if items and isinstance(items[0].get("bulk"), dict):
        return items[0]["bulk"]
    return None
