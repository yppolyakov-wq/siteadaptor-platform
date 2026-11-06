"""AIS A-1: статьи справки шторки «✨ Assistent» — реестр в коде, поиск без ИИ.

План — docs/ais-a1-help-articles-plan-2026-11-06.md. Статья = заголовок, 1–2 предложения,
2–6 коротких шагов и ссылки на экраны кабинета. Исходник — немецкий msgid; переводы — в
5 `.po`, как весь интерфейс (один шаг = один короткий msgid: правка длинного абзаца сделала
бы его fuzzy во всех языках). Ключевые слова — один msgid с контекстом «help-keywords»:
переводчик пишет СВОИ синонимы языка.

Каждая ссылка идёт через `assistant.link` (Mini App, пакет, право, выключенный модуль) —
статья про недоступный экран не показывается или показывается с пометкой «почему нет
ссылки». Для A-2: модель вернёт только ключ статьи и ключ ссылки, URL строит сервер
(`for_prompt` отдаёт текст без адресов)."""

from __future__ import annotations

import functools
import logging
import re
import unicodedata
from dataclasses import dataclass, field

from django.utils import translation
from django.utils.translation import gettext_lazy as _
from django.utils.translation import pgettext_lazy

logger = logging.getLogger(__name__)

MAX_RESULTS = 5
MAX_HERE = 3
QUERY_MAX = 80
MIN_WORD = 3
#: Вес совпадения по части статьи.
WEIGHTS = {"title": 3, "keywords": 3, "summary": 2, "steps": 1}


@dataclass(frozen=True)
class ArticleLink:
    key: str  # стабильный id ссылки внутри статьи (A-2 отвечает ключами, не URL)
    url_name: str
    label: object
    query: str = ""  # без «?», только литерал из кода
    method: str = "GET"


@dataclass(frozen=True)
class Article:
    key: str  # ^[a-z0-9_]+$, стабилен навсегда (A-2, ?artikel=)
    title: object
    summary: object
    steps: tuple
    links: tuple
    keywords: object = ""
    screens: frozenset = field(default_factory=frozenset)
    directions: tuple = ()  # любое из направлений активно
    modules_any: tuple = ()  # любой из модулей активен
    owner_only: bool = False
    readiness: tuple = ()  # связанные Item.key реестра готовности
    diagnoses: tuple = ()  # связанные Diagnosis.key
    show_if: str = ""  # ключ SHOW_IF: статья нужна только в этом состоянии бизнеса

    @property
    def main(self) -> ArticleLink:
        return self.links[0]

    @property
    def all_screens(self) -> frozenset:
        return frozenset({self.main.url_name, *self.screens})


L = ArticleLink

REGISTRY: tuple[Article, ...] = (
    Article(
        key="oeffnungszeiten",
        title=_("Öffnungszeiten eintragen"),
        summary=_(
            "Ohne Öffnungszeiten gibt es keine freien Termine und keine Abholzeiten, und "
            "Kunden sehen nicht, ob Sie geöffnet haben."
        ),
        steps=(
            _("Öffnen Sie „Mein Geschäft“."),
            _("Tragen Sie für jeden Tag die Zeiten ein — geschlossene Tage leer lassen."),
            _("Speichern."),
        ),
        links=(L("open", "settings", _("Mein Geschäft")),),
        keywords=pgettext_lazy(
            "help-keywords", "Öffnungszeiten, Uhrzeit, geöffnet, geschlossen, Ruhetag, Zeiten"
        ),
        screens=frozenset({"setup", "lite-business"}),
        readiness=("hours",),
    ),
    Article(
        key="betriebsferien",
        title=_("Betriebsferien eintragen"),
        summary=_(
            "In den Ferien zeigt die Website einen Hinweis, Termine und Bestellungen für "
            "diese Tage sind gesperrt."
        ),
        steps=(
            _("Öffnen Sie „Betriebsferien“."),
            _("Ersten und letzten freien Tag eintragen."),
            _("Speichern — der Hinweis erscheint automatisch."),
        ),
        links=(L("open", "betriebsferien", _("Betriebsferien")),),
        keywords=pgettext_lazy(
            "help-keywords", "Urlaub, Ferien, geschlossen, Pause, Betriebsurlaub"
        ),
    ),
    Article(
        key="kontakt_adresse",
        title=_("Adresse und Kontakt"),
        summary=_(
            "Adresse, Telefon und E-Mail stehen auf Ihrer Website, im Impressum und im "
            "Stadtkatalog."
        ),
        steps=(
            _("Öffnen Sie „Mein Geschäft“."),
            _("Adresse, Telefon und E-Mail prüfen."),
            _("Speichern."),
        ),
        links=(L("open", "settings", _("Mein Geschäft")),),
        keywords=pgettext_lazy(
            "help-keywords", "Adresse, Telefon, E-Mail, Kontakt, Anschrift, Straße"
        ),
        screens=frozenset({"lite-business"}),
    ),
    Article(
        key="email_bestaetigen",
        title=_("E-Mail-Adresse bestätigen"),
        summary=_(
            "Bis die E-Mail-Adresse bestätigt ist, sehen Kunden Ihre Website nicht und Sie "
            "stehen nicht im Stadtkatalog."
        ),
        steps=(
            _("Öffnen Sie die E-Mail von uns und klicken Sie auf den Link."),
            _("Keine E-Mail da? Spam-Ordner prüfen oder die Bestätigung erneut senden."),
        ),
        links=(L("resend", "owner-confirm-resend", _("Bestätigung erneut senden"), method="POST"),),
        keywords=pgettext_lazy(
            "help-keywords", "bestätigen, Bestätigung, E-Mail, Link, nicht sichtbar"
        ),
        diagnoses=("website_hidden",),
        show_if="email_pending",
    ),
    Article(
        key="impressum",
        title=_("Impressum ausfüllen"),
        summary=_(
            "Jede geschäftliche Website in Deutschland braucht ein Impressum. Wir erzeugen "
            "es aus Ihren Angaben."
        ),
        steps=(
            _("Öffnen Sie „Recht & Steuern“."),
            _("Vertretungsberechtigte Person, Rechtsform und Register eintragen."),
            _("Bei Fragen zur Rechtsform: Steuerberater oder IHK fragen."),
        ),
        links=(L("open", "legal-docs", _("Recht & Steuern")),),
        keywords=pgettext_lazy(
            "help-keywords", "Impressum, Pflichtangaben, Rechtsform, Handelsregister, USt-IdNr"
        ),
        screens=frozenset({"setup"}),
    ),
    Article(
        key="agb_datenschutz",
        title=_("AGB, Datenschutz und Widerruf"),
        summary=_(
            "Wir erzeugen Texte als Vorlage aus Ihren Angaben. Lassen Sie sie bitte von einem "
            "Anwalt prüfen — eine Rechtsberatung ersetzen sie nicht."
        ),
        steps=(
            _("Öffnen Sie „Recht & Steuern“."),
            _("Vorlage ansehen und bei Bedarf eigenen Text einfügen."),
            _("Speichern."),
        ),
        links=(L("open", "legal-docs", _("Recht & Steuern")),),
        keywords=pgettext_lazy(
            "help-keywords", "AGB, Datenschutz, Widerruf, Datenschutzerklärung, DSGVO, Rechtstexte"
        ),
    ),
    Article(
        key="website_veroeffentlichen",
        title=_("Website veröffentlichen"),
        summary=_(
            "Kunden sehen Ihre Website erst nach „Website veröffentlichen“. Fehlt noch etwas, "
            "zeigt der Schritt, was."
        ),
        steps=(
            _("Öffnen Sie den Schritt „Rechtliches & Veröffentlichen“."),
            _("Fehlende Angaben ergänzen."),
            _("Auf „Website veröffentlichen“ klicken."),
        ),
        links=(L("open", "setup", _("Rechtliches & Veröffentlichen"), query="step=recht"),),
        keywords=pgettext_lazy(
            "help-keywords", "veröffentlichen, online, sichtbar, Bald online, freischalten"
        ),
        diagnoses=("website_hidden",),
    ),
    Article(
        key="stadtkatalog",
        title=_("Im Stadtkatalog erscheinen"),
        summary=_(
            "Ihre Angebote erscheinen im Stadtkatalog, sobald die Website veröffentlicht und "
            "die E-Mail bestätigt ist. Neue Angebote kommen nach wenigen Minuten dazu."
        ),
        steps=(
            _("E-Mail bestätigen und Website veröffentlichen."),
            _("Angebote mit Preis und Foto anlegen."),
            _("Im Assistenten zeigt „Funktioniert etwas nicht?“, was noch fehlt."),
        ),
        links=(L("open", "settings", _("Mein Geschäft")),),
        keywords=pgettext_lazy(
            "help-keywords", "Stadtkatalog, Stadtportal, Katalog, gefunden werden, sichtbar"
        ),
    ),
    Article(
        key="startseite_gestalten",
        title=_("Startseite gestalten"),
        summary=_("Titelbild, Text „Über uns“ und Reihenfolge der Blöcke ändern Sie im Studio."),
        steps=(
            _("Öffnen Sie das Studio."),
            _("Auf einen Block klicken und rechts ändern."),
            _("Speichern."),
        ),
        links=(L("open", "site-home", _("Studio")),),
        keywords=pgettext_lazy(
            "help-keywords", "Startseite, Titelbild, Design, Über uns, Banner, Studio, Layout"
        ),
    ),
    Article(
        key="erstes_produkt",
        title=_("Produkt anlegen"),
        summary=_("Ein Produkt braucht Namen und Preis. Mit Foto verkauft es sich besser."),
        steps=(
            _("Öffnen Sie „Neues Produkt“."),
            _("Name, Preis und Kategorie eintragen, Foto hinzufügen."),
            _("Speichern — das Produkt ist sofort im Sortiment."),
        ),
        links=(L("open", "catalog:product-create", _("Neues Produkt")),),
        keywords=pgettext_lazy(
            "help-keywords", "Produkt, Artikel, Ware, anlegen, Preis, Foto, Sortiment"
        ),
        screens=frozenset({"catalog:product-list", "sellable-manage"}),
        directions=("waren", "speisekarte"),
    ),
    Article(
        key="kategorien",
        title=_("Kategorien ordnen"),
        summary=_("Kategorien gliedern Ihr Sortiment auf der Website und im Menü."),
        steps=(
            _("Öffnen Sie „Kategorien“."),
            _("Kategorie anlegen oder umbenennen."),
            _("Reihenfolge per Ziehen ändern."),
        ),
        links=(L("open", "catalog:category-list", _("Kategorien")),),
        keywords=pgettext_lazy("help-keywords", "Kategorie, Gruppe, Reihenfolge, Sortierung, Menü"),
        directions=("waren", "speisekarte"),
    ),
    Article(
        key="allergene",
        title=_("Allergene und Zusatzstoffe angeben"),
        summary=_(
            "Bei Speisen gehören Allergene und Zusatzstoffe zur Pflichtkennzeichnung. Sie "
            "tragen sie pro Gericht ein."
        ),
        steps=(
            _("Gericht im Sortiment öffnen."),
            _("Allergene und Zusatzstoffe ankreuzen."),
            _("Speichern — die Angaben stehen auf der Website und in der Speisekarte als PDF."),
        ),
        links=(L("open", "catalog:product-list", _("Sortiment")),),
        keywords=pgettext_lazy(
            "help-keywords", "Allergene, Zusatzstoffe, Kennzeichnung, LMIV, Gluten, Laktose"
        ),
        directions=("speisekarte",),
    ),
    Article(
        key="bezahlung",
        title=_("Bezahlung einrichten"),
        summary=_(
            "Kunden zahlen vor Ort, per Vorkasse oder online mit Karte (Stripe). Ohne eine "
            "Zahlart kann online niemand bestellen."
        ),
        steps=(
            _("Öffnen Sie „Zahlung & Lieferung“."),
            _("Zahlarten auswählen, für Vorkasse IBAN eintragen."),
            _("Für Kartenzahlung Stripe verbinden."),
        ),
        links=(L("open", "payment-settings", _("Zahlung & Lieferung")),),
        keywords=pgettext_lazy(
            "help-keywords", "Bezahlung, Zahlung, Stripe, Karte, Vorkasse, IBAN, PayPal, bar"
        ),
    ),
    Article(
        key="lieferung_abholung",
        title=_("Lieferung und Abholung"),
        summary=_(
            "Sie legen fest, ob Kunden abholen, ob Sie liefern und in welche Postleitzahlen."
        ),
        steps=(
            _("Öffnen Sie „Lieferung & Abholung“."),
            _("Abholung und Lieferung ein- oder ausschalten."),
            _("Für Lieferung Postleitzahlen und Preis eintragen."),
        ),
        links=(L("open", "payment-settings", _("Lieferung & Abholung"), query="tab=lieferung"),),
        keywords=pgettext_lazy(
            "help-keywords", "Lieferung, Liefergebiet, PLZ, Versand, Abholung, Lieferkosten"
        ),
        screens=frozenset({"payment-settings"}),
        directions=("waren", "speisekarte"),
    ),
    Article(
        key="leistung_anlegen",
        title=_("Leistung anlegen"),
        summary=_(
            "Eine Leistung braucht Dauer und Preis — aus der Dauer entstehen die freien Termine."
        ),
        steps=(
            _("Öffnen Sie „Leistungen“."),
            _("Name, Dauer und Preis eintragen."),
            _("Speichern."),
        ),
        links=(L("open", "booking:services", _("Leistungen")),),
        keywords=pgettext_lazy(
            "help-keywords", "Leistung, Dienstleistung, Termin, Dauer, Behandlung, Service"
        ),
        screens=frozenset({"sellable-manage"}),
        directions=("termine",),
    ),
    Article(
        key="mitarbeiter_zeiten",
        title=_("Mitarbeiter, Tische und ihre Zeiten"),
        summary=_("Termine gibt es nur, wenn ein Mitarbeiter oder Tisch zu dieser Zeit frei ist."),
        steps=(
            _("Öffnen Sie „Öffnungszeiten & Ressourcen“."),
            _("Mitarbeiter oder Tisch anlegen."),
            _("Zeiten eintragen, wenn sie von den Öffnungszeiten abweichen."),
        ),
        links=(L("open", "booking:resources", _("Öffnungszeiten & Ressourcen")),),
        keywords=pgettext_lazy(
            "help-keywords", "Mitarbeiter, Ressource, Tisch, Kalender, freie Termine, Arbeitszeit"
        ),
        directions=("termine", "tisch"),
    ),
    Article(
        key="buchungsregeln",
        title=_("Buchungsregeln: Storno und Anzahlung"),
        summary=_(
            "Hier legen Sie fest, bis wann Kunden kostenlos stornieren und ob eine Anzahlung "
            "nötig ist."
        ),
        steps=(
            _("Öffnen Sie „Buchungsregeln“."),
            _("Frist für kostenlose Stornierung wählen."),
            _("Anzahlung und Regel bei Nichterscheinen festlegen."),
        ),
        links=(L("open", "booking:booking-rules", _("Buchungsregeln")),),
        keywords=pgettext_lazy(
            "help-keywords", "Storno, Stornierung, Anzahlung, No-Show, nicht erschienen, absagen"
        ),
        directions=("termine", "tisch"),
    ),
    Article(
        key="zimmer_anlegen",
        title=_("Zimmer anlegen"),
        summary=_(
            "Ein Zimmer braucht Preis pro Nacht, Anzahl Gäste und ein Foto — ohne Foto ist "
            "keine Online-Buchung möglich."
        ),
        steps=(
            _("Öffnen Sie „Zimmer“."),
            _("Name, Gäste und Preis pro Nacht eintragen."),
            _("Foto hinzufügen und speichern."),
        ),
        links=(L("open", "stays:units", _("Zimmer")),),
        keywords=pgettext_lazy(
            "help-keywords", "Zimmer, Unterkunft, Übernachtung, Gäste, Nacht, Ferienwohnung"
        ),
        screens=frozenset({"sellable-manage"}),
        directions=("zimmer",),
    ),
    Article(
        key="zimmerpreise_saison",
        title=_("Preise nach Saison und Tag"),
        summary=_(
            "Im Preiskalender ändern Sie Preise für einzelne Tage oder Zeiträume und sperren "
            "Tage für den Verkauf."
        ),
        steps=(
            _("Öffnen Sie „Preise & Verfügbarkeit“."),
            _("Zeitraum markieren und neuen Preis eintragen."),
            _("Vorschau prüfen und übernehmen."),
        ),
        links=(L("open", "stays:price-calendar", _("Preise & Verfügbarkeit")),),
        keywords=pgettext_lazy(
            "help-keywords", "Saison, Preis, Tagespreis, Hochsaison, Kalender, Verfügbarkeit"
        ),
        directions=("zimmer",),
    ),
    Article(
        key="veranstaltung_anlegen",
        title=_("Veranstaltung anlegen"),
        summary=_("Eine Veranstaltung braucht Datum, Uhrzeit, Plätze und Preis."),
        steps=(
            _("Öffnen Sie „Veranstaltungen“."),
            _("Neue Veranstaltung anlegen: Datum, Uhrzeit, Plätze, Preis."),
            _("Veröffentlichen — Tickets sind sofort buchbar."),
        ),
        links=(L("open", "events:list", _("Veranstaltungen")),),
        keywords=pgettext_lazy(
            "help-keywords", "Veranstaltung, Event, Ticket, Kurs, Workshop, Plätze, Termin"
        ),
        directions=("tickets",),
    ),
    Article(
        key="anfrageformular",
        title=_("Anfrageformular anpassen"),
        summary=_(
            "Im Anfrageformular fragen Sie zum Beispiel Datum, Gästezahl und Anlass ab — so "
            "können Sie gleich ein Angebot schreiben."
        ),
        steps=(
            _("Öffnen Sie „Abläufe & Status“."),
            _("Im Abschnitt „Anfrage-Formular“ Felder auswählen."),
            _("Speichern."),
        ),
        links=(L("open", "ablaeufe", _("Abläufe & Status")),),
        keywords=pgettext_lazy(
            "help-keywords", "Anfrage, Formular, Angebot, Kostenvoranschlag, Catering, Gäste"
        ),
        directions=("anfragen",),
    ),
    Article(
        key="aktion_erstellen",
        title=_("Aktion erstellen"),
        summary=_(
            "Eine Aktion legen Sie in einer Minute an: Foto, Titel, Preis und Laufzeit — "
            "auch vom Handy."
        ),
        steps=(
            _("Öffnen Sie „Schnell-Aktion“."),
            _("Foto aufnehmen, Titel und Preis eintragen."),
            _("Laufzeit wählen und veröffentlichen."),
        ),
        links=(L("open", "promotions:promotion-quick", _("Schnell-Aktion")),),
        keywords=pgettext_lazy(
            "help-keywords", "Aktion, Angebot, Rabatt, Sonderangebot, Coupon, Gutschein"
        ),
        modules_any=("promotions",),
    ),
    Article(
        key="telegram_bot",
        title=_("Telegram-Bot verbinden"),
        summary=_(
            "Über Telegram erhalten Sie Bestellungen und Nachrichten sofort aufs Handy und "
            "legen Aktionen per Chat an."
        ),
        steps=(
            _("Öffnen Sie „Telegram“."),
            _("Gemeinsamen Bot verbinden oder eigenen Bot eintragen."),
            _("Im Bot auf „Start“ tippen."),
        ),
        links=(L("open", "telegram-settings", _("Telegram")),),
        keywords=pgettext_lazy(
            "help-keywords", "Telegram, Bot, Handy, Benachrichtigung, Chat, Mini App"
        ),
        modules_any=("telegram",),
    ),
    Article(
        key="team_rechte",
        title=_("Mitarbeiter einladen und Rechte vergeben"),
        summary=_(
            "Mitarbeiter bekommen einen eigenen Zugang. Was sie sehen und ändern dürfen, legen "
            "Sie pro Person fest."
        ),
        steps=(
            _("Öffnen Sie „Team & Zugriff“."),
            _("Einladung per E-Mail senden."),
            _("Rechte mit einer Vorlage wählen oder einzeln anpassen."),
        ),
        links=(L("open", "team", _("Team & Zugriff")),),
        keywords=pgettext_lazy(
            "help-keywords", "Team, Mitarbeiter, Rechte, Zugang, einladen, Rolle"
        ),
        owner_only=True,
    ),
)

BY_KEY = {a.key: a for a in REGISTRY}
KEY_RE = re.compile(r"[a-z0-9_]{1,40}")


# --- поиск -------------------------------------------------------------------------------

_WORD = re.compile(r"\w+")


def norm(text) -> list[str]:
    """Слова для поиска: без регистра и диакритики (ä→a, ё→е, İ/ı→i), ß→ss."""
    s = str(text or "").casefold().replace("ß", "ss").replace("ı", "i")
    s = "".join(c for c in unicodedata.normalize("NFKD", s) if not unicodedata.combining(c))
    return _WORD.findall(s)


def _parts(article: Article) -> dict[str, list[str]]:
    return {
        "title": norm(article.title),
        "keywords": norm(article.keywords),
        "summary": norm(article.summary),
        "steps": [w for s in article.steps for w in norm(s)],
    }


@functools.lru_cache(maxsize=8)
def _index(language: str) -> tuple:
    """Индекс языка: слова каждой статьи в языке интерфейса И в немецком исходнике
    (немецкое слово находит статью на любом языке)."""
    out = []
    for article in REGISTRY:
        here = _parts(article)
        with translation.override("de"):
            base = _parts(article)
        out.append((article, {k: set(here[k]) | set(base[k]) for k in WEIGHTS}))
    return tuple(out)


def _hit(word: str, tokens: set[str]) -> bool:
    if len(word) >= 4:
        return any(word in t for t in tokens)  # немецкие композиты: «zeiten» → «offnungszeiten»
    return any(t.startswith(word) for t in tokens)


def _score(words, parts) -> tuple[int, int]:
    """(общий вес, число совпавших слов)."""
    total = matched = 0
    for word in words:
        best = max((WEIGHTS[k] for k, toks in parts.items() if _hit(word, toks)), default=0)
        total += best
        matched += bool(best)
    return total, matched


def ranked(q: str) -> list[Article]:
    """Статьи по запросу без гейтов: сначала «все слова», если пусто — «любое слово»."""
    words = [w for w in norm((q or "")[:QUERY_MAX]) if len(w) >= MIN_WORD]
    if not words:
        return []
    scored = []
    for order, (article, parts) in enumerate(_index(translation.get_language() or "de")):
        total, matched = _score(words, parts)
        if matched:
            scored.append((matched == len(words), total, -order, article))
    full = [x for x in scored if x[0]]
    pool = full or scored
    pool.sort(key=lambda x: (x[1], x[2]), reverse=True)
    return [x[3] for x in pool]


# --- видимость и выдача ------------------------------------------------------------------


def _email_pending(tenant) -> bool:
    from apps.core import storefront_state

    return "email_pending" in storefront_state.hidden_reasons(tenant)


#: Состояние бизнеса, в котором статья вообще нужна (подтверждённому владельцу кнопка
#: «Bestätigung erneut senden» не показывается — как у диагноза `website_hidden`).
SHOW_IF = {"email_pending": _email_pending}


def _gate_ok(request, article: Article) -> bool:
    from apps.core import assistant, directions, modules

    tenant = request.tenant
    if article.owner_only and not assistant._is_owner(request):
        return False
    try:
        if article.show_if and not SHOW_IF[article.show_if](tenant):
            return False
        if article.directions and not any(
            directions.is_active(tenant, d) for d in article.directions
        ):
            return False
        if article.modules_any and not any(
            modules.is_module_active(tenant, m) for m in article.modules_any
        ):
            return False
    except Exception:  # noqa: BLE001 — сомнение → не показывать (молчание лучше ложной подсказки)
        logger.warning("help: gate failed for %s", article.key, exc_info=True)
        return False
    return True


def render(request, article: Article, *, open_: bool = False) -> dict | None:
    """Статья для шаблона или None (скрыта гейтом / основная ссылка недоступна)."""
    from apps.core import assistant

    if not _gate_ok(request, article):
        return None
    links = []
    for i, ln in enumerate(article.links):
        target = assistant.link(request, ln.url_name, query=ln.query, method=ln.method)
        if target is None or (not target.url and not target.blocked):
            if i == 0:
                return None  # основной экран недоступен: статья вела бы в никуда
            continue
        links.append({"key": ln.key, "label": str(ln.label), "link": target})
    return {
        "key": article.key,
        "title": str(article.title),
        "summary": str(article.summary),
        "steps": [str(s) for s in article.steps],
        "links": links,
        "open": open_,
    }


def _render_safe(request, article: Article) -> dict | None:
    """Сбой одной статьи (битый перевод, reverse) не гасит всю справку — статья пропускается."""
    try:
        return render(request, article)
    except Exception:  # noqa: BLE001 — одна статья не стоит пустой шторки
        logger.warning("help: article %s failed", article.key, exc_info=True)
        return None


def search(request, q: str, *, skip=frozenset()) -> list[dict]:
    """Статьи по запросу с гейтами ПО ХОДУ (скрытые не вытесняют видимые), кап 5.
    `skip` — статьи, уже показанные выше («Hilfe zu dieser Seite»): без дублей."""
    out = []
    for article in ranked(q):
        if article.key in skip:
            continue
        item = _render_safe(request, article)
        if item:
            out.append(item)
            if len(out) >= MAX_RESULTS:
                break
    return out


def articles_here(request, seite: str, *, skip: str = "") -> list[dict]:
    """«Hilfe zu dieser Seite»: статьи этого экрана (с расширением SCREEN_EXTRA), кап 3."""
    from apps.core import assistant

    names = assistant.screen_names(seite)
    if not names:
        return []
    out = []
    for article in REGISTRY:
        if article.key == skip or not (article.all_screens & names):
            continue
        item = _render_safe(request, article)
        if item:
            out.append(item)
            if len(out) >= MAX_HERE:
                break
    return out


def opened(request, key: str) -> dict | None:
    """`?artikel=<key>`: только известный ключ и только видимая статья; иначе None."""
    key = str(key or "")
    if not KEY_RE.fullmatch(key) or key not in BY_KEY:
        return None
    return render(request, BY_KEY[key], open_=True)


def for_prompt(request, keys) -> list[dict]:
    """Шов A-2: статьи для промпта — только видимые, текст и ключи ссылок, БЕЗ адресов."""
    out = []
    for key in keys:
        article = BY_KEY.get(key)
        item = render(request, article) if article else None
        if item:
            out.append(
                {
                    "key": item["key"],
                    "title": item["title"],
                    "summary": item["summary"],
                    "steps": item["steps"],
                    "links": [{"key": x["key"], "label": x["label"]} for x in item["links"]],
                }
            )
    return out
