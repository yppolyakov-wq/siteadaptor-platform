"""T-8.10e (D2a-1): «Text-Check» — детерминированные правила текста акции без ИИ.

План — docs/d2-ai-text-check-plan-2026-10-17.md §3. Движок не зависит от приложений и
ничего не пишет: на вход — тексты и факты из полей формы (`CheckInput`), на выход —
подсказки (`Finding`). Ничего не блокирует: решение всегда за владельцем. Правило,
упавшее с исключением, пропускается (подсказки не стоят 500).

Немецкие правила (UWG/PAngV/LMIV-слова) работают только на немецком тексте; правила
без языка (цифры, контакты, капс) — на всех локалях. Числа в предложениях правил
берутся ТОЛЬКО из полей формы — правило не придумывает цену и дату.

Здесь же живут общие регулярки цен/скидок/утверждений: Д1 (`promotions.ai_draft`)
реэкспортирует их под прежними именами."""

from __future__ import annotations

import logging
import re
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from dataclasses import field as dc_field
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation

from django.conf import settings
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

logger = logging.getLogger(__name__)

SEVERITY_ORDER = {"high": 0, "medium": 1, "low": 2}
OWNER, CATALOG = "owner", "catalog"
MAX_TEXT = 2000  # на поле: подсказки к объявлению, а не к роману
# Ревью безопасности D2a-1: форма входа приходит и из POST — потолки по числу текстов,
# попаданий и подсказок, длина цитаты; ключи поля/локали — короткие слова.
MAX_TEXTS = 12
MAX_HITS = 5  # на (правило, поле, локаль)
MAX_FINDINGS = 50
QUOTE_MAX = 80
_KEY_RE = re.compile(r"^[a-z_]{1,20}$")
_LOCALE_RE = re.compile(r"^[a-z]{2}(?:-[a-z]{2,4})?$", re.I)

# --- общие регулярки (переехали из Д1 `ai_draft`, имена там — реэкспорты) ------------

# Слова перед ценой («nur 49 €») уходят вместе с ней — иначе в заголовке висит «nur».
PRICE_LEAD = ("nur", "ab", "für", "jetzt", "statt")
NUMBER_WORDS = (
    "ein",
    "eine",
    "einen",
    "zwei",
    "drei",
    "vier",
    "fünf",
    "sechs",
    "sieben",
    "acht",
    "neun",
    "zehn",
    "zwanzig",
    "fünfzig",
    "hundert",
    "halbe",
    "halben",
    "halber",
)
FOR = "für"
NUM = r"\d{1,3}(?:[ .\u00a0]\d{3})+(?:[.,]\d+)?|\d+(?:[.,]\d+)?"
AMOUNT = (
    r"(?:[−\-–]\s?)?(?:" + NUM + r")\s?(?:€|eur\b|euro\b|%|％|prozent\b|,-|\.-)"
    r"|(?:€|\beur\b|\beuro\b)\s?(?:" + NUM + r")"
    r"|\b\d+\s?(?:\+|" + FOR + r")\s?\d+\b"  # «2 für 1», «1+1»
    r"|\b(?:" + "|".join(NUMBER_WORDS) + r")\s+(?:euro|prozent|preis)\b"
)
PRICE_RE = re.compile(r"(?i)(?:\b(?:" + "|".join(PRICE_LEAD) + r")\s+)?(?:" + AMOUNT + r")")
# Слова скидки без цифр («Rabatt», «Sale», «reduziert») — тоже обещание цены.
DISCOUNT_STEMS = (
    "statt",
    "gratis",
    "kostenlos",
    "umsonst",
    "geschenkt",
    "rabatt",
    "reduziert",
    "sale",
    "aktionspreis",
    "angebotspreis",
    "sonderpreis",
    "schnäppchen",
    "preiswert",
    "billig",
    "günstig",
    "spar",
    "deal",
)
DISCOUNT_RE = re.compile(r"(?i)(?<!\w)(?:" + "|".join(DISCOUNT_STEMS) + r")\w*")
# Ссылки/почта/телефоны.
CONTACT_RE = re.compile(
    r"(?i)https?://\S+|\bwww\.\S+|[\w.+-]+@[\w-]+\.[\w.]+|\+?\d[\d\s/()-]{6,}\d"
)
# Слова-утверждения (основы — ловят и «vegane», «biologisch», «glutenfreies»).
CLAIM_STEMS = (
    "bio",
    "öko",
    "vegan",
    "vegetar",
    "glutenfrei",
    "laktosefrei",
    "halal",
    "gesund",
    "garantier",
    "regional",
    "nachhaltig",
    "beste",
    "billigst",
    "günstigst",
    "nur heute",
)
CLAIM_RE = re.compile(r"(?i)(?<!\w)((?:" + "|".join(re.escape(w) for w in CLAIM_STEMS) + r")\w*)")
NUMBER_RE = re.compile(r"\d+(?:[.,]\d+)*")

# --- регулярки правил -----------------------------------------------------------------

_CUR = r"(?:€|eur\b|euro\b|,-|\.-)"
_NO_UNIT_PRICE = r"(?!\s?/|\s?(?:pro|je)\b)"  # «1,20 €/kg» — Grundpreis, не цена акции
MONEY_RE = re.compile(
    r"(?i)(?<![\w.,])("
    + NUM
    + r")\s?"
    + _CUR
    + _NO_UNIT_PRICE
    + r"|(?:€|\beur\b|\beuro\b)\s?("
    + NUM
    + r")"
    + _NO_UNIT_PRICE
)
PERCENT_RE = re.compile(r"(?i)(?<![\w.,])(" + NUM + r")\s?(?:%|％|prozent\b)")
_MONEY_PLAIN = r"(?:(?:" + NUM + r")\s?" + _CUR + r"|(?:€|\beur\b|\beuro\b)\s?(?:" + NUM + r"))"

STATT_WORDS = ("statt", "uvp", "regulär", "normalpreis")
STATT_BRIDGE = ("nur", "bisher", "sonst", "vorher", "früher")
_STATT_RE = re.compile(
    r"(?i)(?<!\w)(?:" + "|".join(STATT_WORDS) + r")(?!\w):?\s*"
    r"(?:(?:" + "|".join(STATT_BRIDGE) + r")\s+)?" + _MONEY_PLAIN
)
FREE_WORDS = ("gratis", r"kostenlos\w*", "umsonst", "geschenkt")
# «kostenlose Lieferung», «gratis dazu» — законные формулировки, не «бесплатный товар».
FREE_OK_AFTER = (
    r"lieferung\w*",
    r"anlieferung\w*",
    r"versand\w*",
    r"zustellung\w*",
    r"park\w*",
    "wlan",
    "wifi",
    r"beratung\w*",
    r"probe\w*",
    r"verkostung\w*",
    r"stornierung\w*",
    r"abholung\w*",
    r"rückgabe\w*",
    r"umtausch\w*",
    r"montage\w*",
    r"aufbau\w*",
    r"geschenkverpackung\w*",
    r"verpackung\w*",
    r"anfahrt\w*",
    "dazu",
)
_FREE_RE = re.compile(
    r"(?i)(?<!\w)(?:" + "|".join(FREE_WORDS) + r")(?!\w)"
    r"(?!\s+(?:" + "|".join(FREE_OK_AFTER) + r")(?!\w))"
)
# «Lieferung kostenlos», «Versand ist gratis» — то же существительное ПЕРЕД словом.
_FREE_OK_BEFORE = re.compile(
    r"(?i)(?<!\w)(?:" + "|".join(FREE_OK_AFTER) + r")\s+(?:(?:ist|sind|immer)\s+)?$"
)
TODAY_PHRASES = (
    r"nur\s+noch\s+heute",
    r"nur\s+heute",
    r"heute\s+nur",
    r"letzter\s+tag",
    r"nur\s+bis\s+heute",
)
_TODAY_RE = re.compile(r"(?i)(?<!\w)(?:" + "|".join(TODAY_PHRASES) + r")(?!\w)")
UNTIL_WORDS = ("nur", "bis")
STOCK_UNITS = (
    r"stück\w*",
    r"stk\.?",
    r"portion\w*",
    r"plätze",
    "platz",
    "exemplare",
    r"packung\w*",
    r"flasche\w*",
    r"gläser",
    r"tüte\w*",
    r"box\w*",
    r"kiste\w*",
    "paar",
    r"ticket\w*",
    r"karte\w*",
    "teile",
)
_STOCK_RE = re.compile(
    r"(?i)(?<!\w)nur\s+noch\s+(\d{1,5})\s+(?:" + "|".join(STOCK_UNITS) + r")(?!\w)"
)
SUPERLATIVES = (
    r"beste[nrsm]?",
    r"billigste[nrsm]?",
    r"günstigste[nrsm]?",
    r"nr\.?\s?1",
    r"nummer\s+(?:1|eins)",
    r"einzigartig\w*",
    r"unschlagbar\w*",
    r"konkurrenzlos\w*",
    r"testsieger\w*",
)
_SUPERLATIVE_RE = re.compile(r"(?i)(?<!\w)(?:" + "|".join(SUPERLATIVES) + r")(?!\w)")
HEALTH = (
    r"gesund(?:e[nrsm]?)?",
    r"gesundheitsfördernd\w*",
    r"für\s+die\s+gesundheit",
    "heilt",
    r"heilend\w*",
    r"heilwirkung\w*",
    r"heilkr[aä]ft\w*",
    r"gegen\s+(?:erkältung\w*|schmerz\w*|kopfschmerz\w*|grippe|husten|stress)",
    "immunsystem",
    "immunabwehr",
    r"immunstärk\w*",
    r"entgift\w*",
    r"detox\w*",
    r"entschlack\w*",
    r"macht\s+schlank",
    r"schlank\s+(?:machen|werden)",
    "abnehmen",
    r"abnehmkur\w*",
    r"abnehmprodukt\w*",
    "fatburner",
    r"fettverbrenn\w*",
    r"superfood\w*",
)
_HEALTH_RE = re.compile(r"(?i)(?<!\w)(?:" + "|".join(HEALTH) + r")(?!\w)")
BIO_WORDS = ("bio", "öko", r"biologisch\w*", r"ökologisch\w*")
_BIO_RE = re.compile(r"(?i)(?<!\w)(?:" + "|".join(BIO_WORDS) + r")(?!\w)")
# Диет-слово → аллергены (food.VALID_CODES), с которыми оно несовместимо.
DIET_CONFLICTS = (
    (r"vegan\w*", frozenset({"milch", "eier", "fisch", "krebstiere", "weichtiere"})),
    (r"vegetar\w*", frozenset({"fisch", "krebstiere", "weichtiere"})),
    (r"glutenfrei\w*", frozenset({"gluten"})),
)
_DIET_RES = tuple(
    (re.compile(r"(?i)(?<!\w)" + stem + r"(?!\w)"), allergens) for stem, allergens in DIET_CONFLICTS
)
_MASS_RE = re.compile(r"(?i)(?<![\w.,])\d+(?:[.,]\d+)?\s?(?:g|kg|ml|l)(?!\w)")
CLEARANCE = (
    r"räumungsverkauf\w*",
    "geschäftsaufgabe",
    r"totalausverkauf\w*",
    r"alles\s+muss\s+raus",
)
_CLEARANCE_RE = re.compile(r"(?i)(?<!\w)(?:" + "|".join(CLEARANCE) + r")(?!\w)")
_GUARANTEE_RE = re.compile(r"(?i)(?<!\w)garanti\w*")
_EMOJI_RE = re.compile("[\U0001f300-\U0001faff☀-➿]")
_SHOUT_RE = re.compile(r"!{3,}")


# --- модель -----------------------------------------------------------------------------


@dataclass(frozen=True)
class Finding:
    code: str
    severity: str
    field: str
    locale: str
    quote: str
    message: str
    norm: str
    suggestion: str | None = None  # None — нет предложения, "" — «слово убрать»
    source: str = "rule"

    def as_dict(self) -> dict:
        """Для JSON: ленивые переводы — строкой (json.dumps не знает proxy)."""
        return {
            "code": self.code,
            "severity": self.severity,
            "field": self.field,
            "locale": self.locale,
            "quote": self.quote,
            "message": str(self.message),
            "norm": self.norm,
            "suggestion": self.suggestion,
            "source": self.source,
        }


@dataclass(frozen=True)
class CheckInput:
    """Тексты ({поле: {локаль: текст}}) и факты из полей формы — не из текста."""

    texts: dict = dc_field(default_factory=dict)
    new_price: Decimal | None = None
    old_price: Decimal | None = None  # цена сравнения, которую витрина ПОКАЗЫВАЕТ
    percent: int | None = None
    ends_at: datetime | None = None
    quantity: int | None = None
    price_condition: dict | None = None
    mystery: bool = False
    perishable: bool = False
    is_food: bool = False
    has_product: bool = False
    allergens: frozenset = frozenset()
    diets: frozenset = frozenset()
    product_unit: str = ""
    grundpreis_ok: bool | None = None
    ingredients_present: bool = False
    today: date | None = None


@dataclass(frozen=True)
class Hit:
    field: str
    locale: str
    quote: str
    suggestion: str | None = None


@dataclass(frozen=True)
class Rule:
    code: str
    severity: str | Callable[[CheckInput, str], str]
    fn: Callable[[CheckInput], Iterable[Hit]]
    message: str = ""
    norm: str = ""
    scopes: tuple = (OWNER,)
    german: bool = True

    def severity_for(self, inp: CheckInput, scope: str) -> str:
        return self.severity(inp, scope) if callable(self.severity) else self.severity


# --- помощники ----------------------------------------------------------------------------


def _texts(inp: CheckInput, *, german: bool):
    texts = inp.texts if isinstance(inp.texts, dict) else {}
    seen = 0
    for name, by_locale in texts.items():
        if not isinstance(by_locale, dict) or not _KEY_RE.match(str(name)):
            continue
        for locale, text in by_locale.items():
            if not isinstance(text, str) or not text.strip():
                continue
            if not _LOCALE_RE.match(str(locale)):
                continue
            seen += 1
            if seen > MAX_TEXTS:
                return
            if german and str(locale).split("-")[0] != "de":
                continue
            yield name, str(locale), text[:MAX_TEXT]


def to_decimal(raw: str) -> Decimal | None:
    """«1.299,00» / «2,99» / «2.99» / «1 299» → Decimal (немецкая запятая)."""
    s = (raw or "").replace("\u00a0", " ").strip()
    if re.fullmatch(r"\d{1,3}(?:[ .]\d{3})+(?:,\d+)?", s):
        s = s.replace(".", "").replace(" ", "").replace(",", ".")
    else:
        s = s.replace(" ", "").replace(",", ".")
    try:
        return Decimal(s)
    except (InvalidOperation, ValueError):
        return None


def _num(value) -> Decimal | None:
    if value is None or value == "":
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        return None


def _computed_percent(inp: CheckInput) -> int | None:
    old, new = _num(inp.old_price), _num(inp.new_price)
    if old and new is not None and old > 0 and new < old:
        return int(((Decimal(1) - new / old) * 100).quantize(Decimal(1)))
    return None


def _today(inp: CheckInput) -> date:
    return inp.today or timezone.localdate()


def _ends_after_today(inp: CheckInput) -> bool:
    if inp.ends_at is None:
        return True
    end = inp.ends_at
    if timezone.is_aware(end):
        end = timezone.localtime(end)
    day = end.date()
    if (end.hour, end.minute, end.second, end.microsecond) == (0, 0, 0, 0):
        day -= timedelta(days=1)  # «bis 00:00» — это конец предыдущего дня
    return day > _today(inp)


def _scan(regex, inp: CheckInput, *, german=True, suggestion=None):
    for name, locale, text in _texts(inp, german=german):
        for m in regex.finditer(text):
            yield Hit(name, locale, m.group(0).strip(), suggestion)


# --- правила ---------------------------------------------------------------------------------


def _statt(inp):
    if inp.old_price is not None:
        return []
    return _scan(_STATT_RE, inp)


# Суммы и проценты, которые законно стоят рядом с ценой акции: порог доставки, ваучер,
# залог, НДС, жирность/алкоголь. Слово в том же отрывке ДО или сразу ПОСЛЕ числа.
CONTEXT_WORDS = (
    "ab",
    r"mindest\w*",
    r"bestellwert\w*",
    r"gutschein\w*",
    r"wertgutschein\w*",
    "pfand",
    r"versand\w*",
    r"liefer\w*",
    r"einkauf\w*",
    r"einkaufswert\w*",
    "mwst",
    "ust",
    "inkl",
    "zzgl",
    "fett",
    "vol",
    r"alkohol\w*",
    "alc",
    "kakao",
    "frucht",
    "kakaoanteil",
)
_CONTEXT_BEFORE = re.compile(
    r"(?i)(?<!\w)(?:" + "|".join(CONTEXT_WORDS) + r")\.?\s*[^\s.!?;]{0,12}\s*$"
)
_CONTEXT_AFTER = re.compile(r"(?i)^\s*(?:" + "|".join(CONTEXT_WORDS) + r")(?!\w)")


def _in_context(text: str, start: int, end: int) -> bool:
    return bool(
        _CONTEXT_BEFORE.search(text[max(0, start - 30) : start])
        or _CONTEXT_AFTER.match(text[end : end + 20])
    )


def _price_conflict(inp):
    if inp.price_condition or inp.mystery:
        return []
    money_ok = [v for v in (_num(inp.new_price), _num(inp.old_price)) if v is not None]
    if len(money_ok) == 2:
        money_ok.append(abs(money_ok[1] - money_ok[0]))  # «Sie sparen 3 €»
    percents = {p for p in (inp.percent, _computed_percent(inp)) if p is not None}
    hits = []
    for name, locale, text in _texts(inp, german=False):
        if money_ok:
            for m in MONEY_RE.finditer(text):
                if _in_context(text, m.start(), m.end()):
                    continue
                value = to_decimal(m.group(1) or m.group(2) or "")
                if value is not None and all(abs(value - ok) > Decimal("0.01") for ok in money_ok):
                    hits.append(Hit(name, locale, m.group(0).strip()))
        if percents:
            for m in PERCENT_RE.finditer(text):
                if _in_context(text, m.start(), m.end()):
                    continue
                value = to_decimal(m.group(1))
                if value is not None and all(abs(value - p) > 1 for p in percents):
                    hits.append(Hit(name, locale, m.group(0).strip()))
    return hits


def _implausible(inp):
    if inp.perishable:
        return []
    pct = inp.percent or _computed_percent(inp)
    limit = getattr(settings, "TEXT_CHECK_PLAUSIBLE_DISCOUNT", 70)
    if pct is not None and pct > limit:
        return [Hit("price", "", f"−{pct} %")]
    return []


def _strike_no_end(inp):
    if inp.old_price is not None and inp.ends_at is None:
        return [Hit("price", "", "")]
    return []


def _free(inp):
    price = _num(inp.new_price)
    if inp.price_condition or price is None or price <= 0:
        return []
    hits = []
    for name, locale, text in _texts(inp, german=True):
        for m in _FREE_RE.finditer(text):
            if not _FREE_OK_BEFORE.search(text[max(0, m.start() - 40) : m.start()]):
                hits.append(Hit(name, locale, m.group(0).strip(), ""))
    return hits


def _urgency_today(inp):
    if not _ends_after_today(inp):
        return []
    suggestion = None
    if inp.ends_at is not None:
        end = timezone.localtime(inp.ends_at) if timezone.is_aware(inp.ends_at) else inp.ends_at
        suggestion = " ".join(UNTIL_WORDS) + f" {end:%d.%m.}"
    hits = []
    for hit in _scan(_TODAY_RE, inp):
        text = suggestion
        if text and hit.quote[:1].isupper():
            text = text[0].upper() + text[1:]
        hits.append(Hit(hit.field, hit.locale, hit.quote, text))
    return hits


def _urgency_stock(inp):
    hits = []
    for name, locale, text in _texts(inp, german=True):
        for m in _STOCK_RE.finditer(text):
            if inp.quantity is None or int(m.group(1)) != inp.quantity:
                hits.append(Hit(name, locale, m.group(0).strip()))
    return hits


def _superlative(inp):
    return _scan(_SUPERLATIVE_RE, inp, suggestion="")


def _health(inp):
    return _scan(_HEALTH_RE, inp)


def _bio(inp):
    if "bio" in inp.diets:
        return []
    return _scan(_BIO_RE, inp)


def _diet(inp):
    if not inp.has_product:
        return []
    hits = []
    for regex, allergens in _DIET_RES:
        if allergens & set(inp.allergens):
            hits.extend(_scan(regex, inp))
    return hits


def _allergens_missing(inp):
    if inp.is_food and inp.has_product and not inp.allergens and not inp.ingredients_present:
        return [Hit("product", "", "")]
    return []


def _grundpreis(inp):
    if inp.has_product and inp.product_unit and inp.grundpreis_ok is False:
        return [Hit("price", "", "")]
    if inp.new_price is None or inp.grundpreis_ok:
        return []
    return list(_scan(_MASS_RE, inp, german=False))[:1]


def _clearance(inp):
    return _scan(_CLEARANCE_RE, inp)


def _mystery(inp):
    if not inp.mystery:
        return []
    hits = []
    for name, locale, text in _texts(inp, german=False):
        for regex in (MONEY_RE, PERCENT_RE):
            hits.extend(Hit(name, locale, m.group(0).strip()) for m in regex.finditer(text))
    return hits


def _contact(inp):
    # Телефон — от 8 цифр: «Mo-Fr 9-12 / 14-18» по форме похоже, но это часы работы.
    return [
        hit
        for hit in _scan(CONTACT_RE, inp, german=False, suggestion="")
        if not hit.quote[:1].isdigit()
        and not hit.quote.startswith("+")
        or sum(c.isdigit() for c in hit.quote) >= 8
    ]


def _shouting(inp):
    hits = []
    for name, locale, text in _texts(inp, german=False):
        letters = [c for c in text if c.isalpha()]
        upper = sum(1 for c in letters if c.isupper())
        if len(letters) >= 12 and upper / len(letters) > 0.6:
            hits.append(Hit(name, locale, text[:60].strip()))
        elif m := _SHOUT_RE.search(text):
            hits.append(Hit(name, locale, m.group(0)))
        elif len(_EMOJI_RE.findall(text)) > 5:
            hits.append(Hit(name, locale, "".join(_EMOJI_RE.findall(text))[:12]))
    return hits


def _guarantee(inp):
    return _scan(_GUARANTEE_RE, inp)


def _health_severity(inp, scope):
    return "high" if inp.is_food else "medium"


def _contact_severity(inp, scope):
    return "medium" if scope == CATALOG else "low"


BOTH = (OWNER, CATALOG)

RULES: tuple[Rule, ...] = (
    Rule(
        "statt_ohne_referenz",
        "high",
        _statt,
        _("Der Text nennt einen früheren Preis, das Angebot hat aber keinen Vergleichspreis."),
        "UWG § 5, PAngV § 11",
        BOTH,
    ),
    Rule(
        "preis_widerspruch",
        "medium",
        _price_conflict,
        _("Ein Preis oder Prozentsatz im Text passt nicht zu den Preisfeldern."),
        "UWG § 5",
        BOTH,
        german=False,
    ),
    Rule(
        "rabatt_unplausibel",
        "medium",
        _implausible,
        _("Sehr hoher Rabatt: Bitte prüfen, ob der Vergleichspreis wirklich verlangt wurde."),
        "UWG § 5",
        BOTH,
        german=False,
    ),
    Rule(
        "streich_ohne_ende",
        "medium",
        _strike_no_end,
        _("Ein durchgestrichener Preis braucht ein Enddatum der Aktion."),
        "UWG § 5, PAngV § 11",
        BOTH,
        german=False,
    ),
    Rule(
        "gratis_mit_preis",
        "high",
        _free,
        _("„Gratis“ oder „kostenlos“ passt nicht zu einem Preis über 0 €."),
        "UWG Anhang Nr. 21",
        BOTH,
    ),
    Rule(
        "dringlichkeit_heute",
        "high",
        _urgency_today,
        _("„Nur heute“ steht im Text, die Aktion läuft aber länger."),
        "UWG Anhang Nr. 7",
        BOTH,
    ),
    Rule(
        "dringlichkeit_menge",
        "high",
        _urgency_stock,
        _("Die genannte Restmenge passt nicht zur Menge im Angebot."),
        "UWG Anhang Nr. 7",
    ),
    Rule(
        "alleinstellung",
        "medium",
        _superlative,
        _("Aussagen wie „der beste“ oder „Nr. 1“ müssen belegbar sein."),
        "UWG § 5",
    ),
    Rule(
        "gesundheit",
        _health_severity,
        _health,
        _("Gesundheitsversprechen sind bei Lebensmitteln nur mit zugelassenen Angaben erlaubt."),
        "EU-VO 1924/2006, LMIV Art. 7, HWG § 3",
        BOTH,
    ),
    Rule(
        "bio_claim",
        "medium",
        _bio,
        _("„Bio“ oder „Öko“ darf nur mit Öko-Kontrollnummer verwendet werden."),
        "EU-Öko-VO 2018/848",
    ),
    Rule(
        "diaet_widerspruch",
        "high",
        _diet,
        _("Die Angabe im Text widerspricht den Allergenen des Produkts."),
        "LMIV Art. 7, Art. 36",
    ),
    Rule(
        "allergene_fehlen",
        "low",
        _allergens_missing,
        _("Beim Produkt sind weder Allergene noch Zutaten angegeben."),
        "LMIV Art. 9",
        german=False,
    ),
    Rule(
        "grundpreis_fehlt",
        "medium",
        _grundpreis,
        _("Für Ware nach Gewicht oder Volumen fehlt der Grundpreis (Preis pro kg oder l)."),
        "PAngV § 4",
        german=False,
    ),
    Rule(
        "raeumung",
        "medium",
        _clearance,
        _("Räumungsverkauf darf nur bei echter Geschäftsaufgabe angekündigt werden."),
        "UWG Anhang Nr. 15",
        BOTH,
    ),
    Rule(
        "mystery_verraten",
        "high",
        _mystery,
        _("Bei einer Überraschungsaktion verrät der Text den Preis."),
        "Mystery",
        german=False,
    ),
    Rule(
        "kontakt_im_text",
        _contact_severity,
        _contact,
        _("Links, E-Mail-Adressen und Telefonnummern gehören nicht in den Angebotstext."),
        "Stadtkatalog",
        BOTH,
        german=False,
    ),
    Rule(
        "grossbuchstaben",
        "low",
        _shouting,
        _("Viele Großbuchstaben, Ausrufezeichen oder Emojis wirken wie Werbung."),
        "Lesbarkeit",
        BOTH,
        german=False,
    ),
    Rule(
        "garantie",
        "low",
        _guarantee,
        _("Bei „Garantie“ müssen Inhalt und Dauer der Garantie genannt werden."),
        "BGB § 479",
    ),
)


def run(inp: CheckInput, *, scope: str = OWNER) -> list[Finding]:
    """Все подсказки к тексту: без дублей, от важных к мелким."""
    found: list[Finding] = []
    seen: set[tuple] = set()
    for rule in RULES:
        if scope not in rule.scopes:
            continue
        try:
            hits = list(rule.fn(inp))
            severity = rule.severity_for(inp, scope)
        except Exception:  # noqa: BLE001 — сломанное правило = нет подсказки, не 500
            logger.exception("text_check: rule %s failed", rule.code)
            continue
        per_text: dict[tuple, int] = {}
        for hit in hits:
            key = (rule.code, hit.field, hit.locale, hit.quote.casefold())
            slot = (hit.field, hit.locale)
            if key in seen or per_text.get(slot, 0) >= MAX_HITS:
                continue
            seen.add(key)
            per_text[slot] = per_text.get(slot, 0) + 1
            quote, suggestion = hit.quote, hit.suggestion
            if len(quote) > QUOTE_MAX:
                # Обрезанная цитата не найдётся в тексте — замену по ней не предлагаем.
                quote, suggestion = quote[: QUOTE_MAX - 1] + "…", None
            found.append(
                Finding(
                    code=rule.code,
                    severity=severity,
                    field=hit.field,
                    locale=hit.locale,
                    quote=quote,
                    message=rule.message,
                    norm=rule.norm,
                    suggestion=suggestion,
                )
            )
    found.sort(key=lambda f: SEVERITY_ORDER.get(f.severity, 9))
    return found[:MAX_FINDINGS]
