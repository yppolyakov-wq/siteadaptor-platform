"""AIS W4-5c: карточки «Nächster Schritt» на главной кабинета (мастер v4).

План — docs/ais-w4-5-verkauf-oeffnen-plan-2026-11-06.md §W4-5c; спека —
ais-wizard-v4-structure-2026-11-05.md §4.2/§3a. Правила:
* не больше трёх, порядок — польза (сначала то, без чего нельзя продавать);
* каждая карточка — только вход на существующий экран с объяснением «зачем»; ссылка строится
  `assistant.link` (права, пакет, Mini App, модуль) — нет ссылки → нет карточки;
* проверка карточки упала → карточки нет (fail-closed, в лог);
* «Später» прячет карточку на 14 дней; отметку пишет один писатель `hide` под блокировкой;
* вторая кнопка «✨ Assistent fragen» ведёт в помощник с готовой фразой (`?q=` — правила, без ИИ).
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass
from datetime import timedelta

from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from django.utils.translation import ngettext

logger = logging.getLogger(__name__)

LIMIT = 3
HIDE_DAYS = 14
CFG_KEY = "next_steps"


@dataclass(frozen=True)
class Card:
    key: str
    title: str
    why: Callable  # (tenant) -> str | None: текст «зачем» (None — карточка не нужна)
    url_name: str
    action: str
    query: str = ""
    assistant_q: str = ""


def _unpublished(t):
    if getattr(t, "published_at", True) is None:
        return str(_("Erst nach der Veröffentlichung sehen Kundinnen und Kunden Ihre Website."))
    return None


def _verkauf(t):
    from apps.core import sell_questions

    if not t.is_module_active("orders"):
        return None
    n = sum(1 for q in sell_questions.QUESTIONS if q.applies(t) and _open(t, q))
    if not n:
        return None
    return ngettext(
        "Noch %(n)s kurze Frage, dann können Kunden online bestellen.",
        "Noch %(n)s kurze Fragen, dann können Kunden online bestellen.",
        n,
    ) % {"n": n}


def _open(t, q) -> bool:
    from apps.core import sell_questions

    return sell_questions.state(t, q) == "open"


def _photos(t):
    from django.db.models import Q

    from apps.catalog.models import Product

    if not t.is_module_active("catalog"):
        return None
    n = Product.objects.filter(Q(images=[]) | Q(images__isnull=True), is_active=True).count()
    if not n:
        return None
    return ngettext(
        "%(n)s Angebot hat noch kein Foto — mit Foto wird öfter gekauft.",
        "%(n)s Angebote haben noch kein Foto — mit Foto wird öfter gekauft.",
        n,
    ) % {"n": n}


def _first_promo(t):
    from apps.promotions.models import Promotion

    if not t.is_module_active("promotions") or Promotion.objects.exists():
        return None
    return str(_("Eine Aktion bringt Laufkundschaft — in einer Minute vom Handy aus."))


def _languages(t):
    if len(t.active_locales()) > 1:
        return None
    return str(_("Gäste aus dem Ausland lesen Ihre Seite in ihrer Sprache."))


def _design(t):
    """§3a: Aussehen erst, wenn es eigene Daten gibt (≥ 5 Angebote und ein eigenes Foto)."""
    from apps.catalog.models import Product

    if not t.is_module_active("catalog"):
        return None
    products = Product.objects.filter(is_active=True)
    if products.count() < 5 or not products.exclude(images=[]).exists():
        return None
    cfg = t.site_config if isinstance(t.site_config, dict) else {}
    if (cfg.get("design") or {}).get("look"):  # Look уже выбран владельцем
        return None
    return str(_("Jetzt gibt es genug Inhalt, um das Aussehen auf Ihren Daten zu wählen."))


CARDS: tuple[Card, ...] = (
    Card(
        "publish",
        _("Website veröffentlichen"),
        _unpublished,
        "setup",
        _("Fertigstellen"),
        query="step=recht",
    ),
    Card(
        "verkauf",
        _("Verkauf öffnen"),
        _verkauf,
        "verkauf-oeffnen",
        _("Fragen beantworten"),
    ),
    Card(
        "photos",
        _("Fotos ergänzen"),
        _photos,
        "catalog:product-list",
        _("Zum Sortiment"),
        assistant_q=_("Wie füge ich Fotos zu Produkten hinzu?"),
    ),
    Card(
        "promo",
        _("Erste Aktion starten"),
        _first_promo,
        "promotions:promotion-quick",
        _("Aktion anlegen"),
    ),
    Card(
        "languages",
        _("Weitere Sprachen"),
        _languages,
        "languages",
        _("Sprachen wählen"),
        assistant_q=_("Wie übersetze ich meine Website?"),
    ),
    Card(
        "design",
        _("Aussehen wählen"),
        _design,
        "design",
        _("Varianten ansehen"),
    ),
)
BY_KEY = {c.key: c for c in CARDS}


def _hidden(tenant) -> dict:
    raw = (getattr(tenant, "site_config", None) or {}).get(CFG_KEY) or {}
    return raw.get("hidden") or {} if isinstance(raw, dict) else {}


def _is_hidden(tenant, key: str, now) -> bool:
    until = _hidden(tenant).get(key)
    try:
        from datetime import datetime

        return bool(until) and datetime.fromisoformat(until) > now
    except (TypeError, ValueError):
        return False


def cards(request, limit: int = LIMIT) -> list[dict]:
    from django.urls import reverse

    from apps.core import assistant

    tenant = request.tenant
    now = timezone.now()
    out = []
    for card in CARDS:
        if len(out) >= limit:
            break
        if _is_hidden(tenant, card.key, now):
            continue
        try:
            why = card.why(tenant)
            if not why:
                continue
            target = assistant.link(request, card.url_name, query=card.query)
        except Exception:  # noqa: BLE001 — сломанная карточка не роняет главную (fail-closed)
            logger.exception("next step card %s failed", card.key)
            continue
        if target is None or not target.url:
            continue  # нет права / пакет / модуль — карточки нет
        row = {
            "key": card.key,
            "title": card.title,
            "why": why,
            "action": card.action,
            "url": target.url,
            "assistant_url": "",
        }
        if card.assistant_q:
            from urllib.parse import urlencode

            row["assistant_url"] = (
                f"{reverse('assistant')}?{urlencode({'q': str(card.assistant_q)})}"
            )
        out.append(row)
    return out


def hide(tenant, key: str, days: int = HIDE_DAYS) -> bool:
    """«Später»: спрятать карточку. Единственный писатель ключа — из ЗАБЛОКИРОВАННОЙ строки."""
    from django.db import transaction

    if key not in BY_KEY:
        return False
    until = (timezone.now() + timedelta(days=days)).isoformat()
    with transaction.atomic():
        locked = type(tenant).objects.select_for_update().get(pk=tenant.pk)
        cfg = dict(locked.site_config or {})
        now = timezone.now()
        hidden = {
            k: v for k, v in _hidden(locked).items() if k in BY_KEY and _is_hidden(locked, k, now)
        }
        hidden[key] = until
        cfg[CFG_KEY] = {"hidden": hidden}
        locked.site_config = cfg
        locked.auto_create_schema = False
        locked.save(update_fields=["site_config", "updated_at"])
    tenant.site_config = cfg
    return True
