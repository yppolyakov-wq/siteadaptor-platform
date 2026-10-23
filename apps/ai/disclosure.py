"""AI-2: что писать о ИИ в Datenschutzerklärung — из ЖИВОЙ конфигурации.

Какие задачи включены (`api.is_enabled(task)` + вторичные флаги поиска/модерации),
какие провайдеры стоят в маршрутах и все ли они в ЕС. Текст платформы (для владельцев
бизнесов) и абзац тенанта (для его клиентов) строятся отсюда: переключили `.env` на
маршрут ЕС — текст сам перестал говорить о США. Правила — docs/ai-usage-policy-2026-10-23.md.

Правовой немецкий текст; вычитка — за владельцем. Ничего не утверждаем, чего нет в
документах проекта (например, сертификацию по EU-US Data Privacy Framework)."""

from __future__ import annotations

import logging

from django.conf import settings

from . import config

logger = logging.getLogger(__name__)

# маршрут → (получатель, страна/регион, ЕС ли)
PROCESSORS = {
    "anthropic": ("Anthropic PBC", "San Francisco, USA", False),
    "openai": ("OpenAI, L.L.C.", "San Francisco, USA", False),
    "bedrock": ("Amazon Web Services EMEA SARL", "Rechenzentren in der EU", True),
    "azure": ("Microsoft Ireland Operations Ltd.", "Dublin, Rechenzentren in der EU", True),
    "mistral": ("Mistral AI SAS", "Paris, Frankreich", True),
}

# задача → (что уходит в модель, правовое основание, круг лиц)
TASK_DATA = {
    "site_import_extract": (
        "Import Ihres Sortiments von Ihrer Website: Text der Seiten Ihrer Website",
        "Art. 6 Abs. 1 lit. b DSGVO",
        "owner",
    ),
    "promo_photo_draft": (
        "Vorschlag für eine Aktion aus einem Foto (im Kundenbereich und im Telegram-Bot): "
        "Fotos (ohne Standort- und Kameradaten) und Ihre Bildunterschrift; was auf dem Foto "
        "sonst zu sehen ist, wird mit übermittelt",
        "Art. 6 Abs. 1 lit. b DSGVO",
        "owner",
    ),
    "promo_text_check": (
        "Prüfung des Aktionstexts: Text der Aktion und ihre Angaben (Preis, Vergleichspreis, "
        "Rabatt, Laufzeit, Menge)",
        "Art. 6 Abs. 1 lit. b DSGVO",
        "owner",
    ),
    "catalog_moderation": (
        "Prüfung öffentlicher Einträge im Stadtkatalog: Text, Preis und Rabatt des Eintrags",
        "Art. 6 Abs. 1 lit. f DSGVO (Schutz der Nutzer vor irreführenden Angeboten)",
        "public",
    ),
    "search_phrase_filters": (
        "Suche im Stadtportal: die eingegebene Suchphrase; die daraus abgeleiteten Filter "
        "(nicht die Phrase) werden bis zu 24 Stunden zwischengespeichert",
        "Art. 6 Abs. 1 lit. f DSGVO (passende Suchergebnisse)",
        "public",
    ),
    "search_query_expand": (
        "Suche im Stadtportal ohne passende Treffer: der Suchtext (ohne Kontaktdaten), um "
        "deutsche Suchbegriffe zu finden; nur die gefundenen Begriffe (nicht der Suchtext) "
        "werden bis zu 24 Stunden zwischengespeichert",
        "Art. 6 Abs. 1 lit. f DSGVO (passende Suchergebnisse)",
        "public",
    ),
    "inbox_reply_draft": (
        "Antwortvorschläge auf Kundennachrichten: Nachrichten und Angaben zur Bestellung",
        "Art. 6 Abs. 1 lit. b DSGVO",
        "customer",
    ),
}

_SECONDARY_GATES = {
    "catalog_moderation": "AI_CATALOG_MODERATION",
    "search_phrase_filters": "AI_SEARCH_ENABLED",
    "search_query_expand": "AI_SEARCH_ENABLED",
}


def active_tasks() -> list[str]:
    from .api import is_enabled

    out = []
    for task in TASK_DATA:
        gate = _SECONDARY_GATES.get(task)
        if gate and not config.get(gate, False):
            continue
        if is_enabled(task):
            out.append(task)
    return out


def active_processors() -> list[tuple[str, str, bool]]:
    """Получатели по настроенным маршрутам, без фейка и неизвестных имён, без дублей."""
    from . import providers, routing

    seen, out = set(), []
    from .registry import TIERS

    for tier in TIERS:
        for name in routing.configured(tier):
            if name in providers.FAKE_ROUTES or name in seen or name not in PROCESSORS:
                continue
            try:
                route = routing.describe(name, tier)
            except Exception:  # noqa: BLE001 — неизвестный провайдер не роняет правовую страницу
                continue
            if not routing.allowed(route):
                continue
            seen.add(name)
            legal, place, eu = PROCESSORS[name]
            out.append((legal, place, bool(eu and route.eu)))
    return out


def _transfer_sentence(processors) -> str:
    if all(eu for _l, _p, eu in processors):
        return "Die Verarbeitung erfolgt auf Servern in der EU."
    if any(eu for _l, _p, eu in processors):
        return (
            "Die Verarbeitung erfolgt teils auf Servern in der EU, teils in den USA. Für die "
            "Übermittlung in die USA gelten die Standardvertragsklauseln der EU-Kommission "
            "(Art. 46 Abs. 2 lit. c DSGVO)."
        )
    return (
        "Dabei werden Daten in die USA übermittelt. Grundlage sind die "
        "Standardvertragsklauseln der EU-Kommission (Art. 46 Abs. 2 lit. c DSGVO)."
    )


def _who(processors) -> str:
    return "; ".join(f"{legal}, {place}" for legal, place, _eu in processors)


def platform_section() -> str:
    """Раздел «KI-Dienste» Datenschutz платформы. Пусто — ИИ не используется."""
    try:
        tasks = [t for t in active_tasks() if TASK_DATA[t][2] != "customer"]
        processors = active_processors()
        if not tasks or not processors:
            return ""
        lines = [
            "Für einzelne Funktionen setzen wir KI-Dienste als Auftragsverarbeiter ein "
            "(Art. 28 DSGVO). Ein Vorschlag der KI ist als „KI-generiert“ gekennzeichnet; "
            "veröffentlicht oder versendet wird nur, was du selbst bestätigst.",
        ]
        for task in tasks:
            what, basis, _scope = TASK_DATA[task]
            lines.append(f"– {what} ({basis}).")
        lines.append(f"Empfänger: {_who(processors)}. {_transfer_sentence(processors)}")
        lines.append(
            "Erkennbare E-Mail-Adressen, Telefon- und Kontonummern entfernen wir vor der "
            "Übermittlung aus Texten. Die Inhalte speichern wir nicht; wir protokollieren nur "
            "Aufgabe, Umfang und Dauer der Anfrage "
            f"({settings.AI_USAGE_RETENTION_DAYS} Tage)."
        )
        return "\n".join(lines)
    except Exception:  # noqa: BLE001 — правовая страница не падает
        logger.exception("ai disclosure: platform section failed")
        return ""


def tenant_paragraph() -> str:
    """Абзац для клиентов бизнеса — только про задачу, касающуюся их данных (переписка)."""
    try:
        if "inbox_reply_draft" not in active_tasks():
            return ""
        processors = active_processors()
        if not processors:
            return ""
        return (
            "Antworten auf Ihre Nachrichten können wir mit Hilfe von KI-Diensten "
            "vorbereiten lassen. Dabei werden die Inhalte der Nachrichten (erkennbare "
            "E-Mail-Adressen, Telefon- und Kontonummern werden vorher entfernt), Angaben "
            "zu Ihrer Bestellung oder Anfrage und zu unserem Angebot an "
            f"Auftragsverarbeiter übermittelt (Art. 28 DSGVO): {_who(processors)}. "
            f"{_transfer_sentence(processors)} "
            "Jede Antwort wird von unseren Mitarbeitenden geprüft und selbst versendet.\n\n"
        )
    except Exception:  # noqa: BLE001
        logger.exception("ai disclosure: tenant paragraph failed")
        return ""
