"""AIS-A A-0: ядро шторки «✨ Assistent» — без ИИ, только чтение.

Четыре блока (план `docs/ais-a0-assistant-plan-2026-11-05.md`):
- «Auf dieser Seite fehlt» — пункты реестра готовности, относящиеся к открытому экрану;
- «Gerade wichtig» — до трёх карточек на весь бизнес;
- «Funktioniert etwas nicht?» — диагнозы `apps.core.diagnoses` (зовут настоящие гейты);
- «Wo stelle ich das ein?» — поиск по тому же индексу, что палитра Ctrl+K.

Каждая ссылка проходит `link()` — те же три гейта, что кабинет (Mini App, пакет, право),
плюс гейт записи меню (выключенный модуль = 404). «Не знаю» никогда не печатается как
«готово»: readiness читается с `unknown_on_error=True`, сбой блока — пустой блок + флаг."""

from __future__ import annotations

import logging
from dataclasses import dataclass

from django.urls import NoReverseMatch, reverse
from django.utils.translation import gettext as _

from apps.core import diagnoses

logger = logging.getLogger(__name__)

MAX_IMPORTANT = 3
MAX_WHERE = 8
MAX_HERE = 6
QUERY_MAX = 80
BREAK_DAYS = 7

#: Действия вне зоны прав кабинета (свой путь, не `dashboard/`): только владельцу.
OWNER_ACTIONS = frozenset({"owner-confirm-resend"})
#: Экраны, которые сотруднику не показываются вовсе (решение В-1), даже текстом.
STAFF_HIDDEN = frozenset({"billing", "team", "team-invite", "team-member"})
#: Лёгкий пакет / Mini App: у полного экрана есть лёгкий двойник (None — двойника нет).
LITE_ALIASES = {"settings": "lite-business", "legal-docs": "lite-business", "site-home": None}
#: Экран ↔ доп. url_name пунктов готовности, которые на нём заполняются.
SCREEN_EXTRA = {
    "dashboard": (),
    "setup": (),
    "lite-business": ("settings", "legal-docs"),
    "catalog:product-list": ("catalog:product-create",),
    "sellable-manage": ("catalog:product-create", "booking:services", "stays:units"),
}

BLOCK_OWNER = "owner"
BLOCK_PACKAGE = "package"
BLOCK_BROWSER = "browser"


@dataclass(frozen=True)
class Link:
    url: str = ""
    method: str = "GET"
    blocked: str = ""  # "" | owner | package | browser

    @property
    def note(self) -> str:
        return {
            BLOCK_OWNER: _("Bitte den Inhaber fragen."),
            BLOCK_PACKAGE: _("Nicht in Ihrem Paket."),
            BLOCK_BROWSER: _("Im Browser öffnen."),
        }.get(self.blocked, "")


def _is_owner(request) -> bool:
    """Уровень владельца — через реестр прав (пол «Abo» = только владелец), не по роли."""
    from apps.core import permissions, view_perms

    user = getattr(request, "user", None)
    if user is None or not permissions.is_member(user):
        return True  # не член команды — кабинет его не пускает; прятать нечего
    return view_perms.allowed_quiet(user, "billing", "GET")


def _staff_hidden(request, url_name: str) -> bool:
    """Abo/Team: без права пункт не показывается вовсе (В-1), даже пометкой."""
    from apps.core import permissions, view_perms

    user = getattr(request, "user", None)
    if user is None or not permissions.is_member(user):
        return False
    return not view_perms.allowed_quiet(user, url_name, "GET")


def _is_lite(request) -> bool:
    from apps.core import lite_cabinet

    return lite_cabinet.is_lite_request(request)


def _nav_entry(url_name: str):
    from apps.core import nav_registry

    for e in nav_registry.ENTRIES:
        if e.url_name == url_name:
            return e
    return None


def link(request, url_name: str, *, args=(), query: str = "", method: str = "GET") -> Link | None:
    """Ссылка на экран для ЭТОГО запроса. None — пункт не показывать вовсе."""
    from apps.core import nav_registry, packages, setup_assistant, tg_login

    if not url_name:
        return Link()
    if url_name in STAFF_HIDDEN and _staff_hidden(request, url_name):
        return None
    if _is_lite(request) and url_name in LITE_ALIASES:
        alias = LITE_ALIASES[url_name]
        if alias is None:
            return Link()  # текст без ссылки: в лёгком кабинете экрана нет
        url_name, args, query = alias, (), ""
    if url_name in OWNER_ACTIONS:
        if not _is_owner(request):
            return Link(blocked=BLOCK_OWNER)
        try:
            return Link(url=reverse(url_name), method=method)
        except NoReverseMatch:
            logger.warning("assistant: no url for %s", url_name)
            return Link()
    try:
        if not setup_assistant.reachable(request, url_name):
            if tg_login.is_tg_session(request) and url_name not in tg_login.TG_LITE_VIEWS:
                return Link(blocked=BLOCK_BROWSER)
            if not packages.view_allowed(request.tenant, url_name):
                return Link(blocked=BLOCK_PACKAGE)
            return Link(blocked=BLOCK_OWNER)
        entry = _nav_entry(url_name)
        if entry is not None and not nav_registry.entry_visible(entry, request.tenant):
            return Link()  # модуль выключен — ссылка вела бы в 404
        url = reverse(url_name, args=list(args))
    except NoReverseMatch:
        logger.warning("assistant: no url for %s", url_name)
        return Link()
    except Exception:  # noqa: BLE001 — сомнение → пункт без ссылки, кабинет не падает
        logger.warning("assistant: link check failed for %s", url_name, exc_info=True)
        return Link()
    if query:
        url = f"{url}?{query}"
    return Link(url=url, method=method)


def _row(
    request, text, url_name="", *, args=(), query="", method="GET", level="", owner_only=False
):
    if owner_only and not _is_owner(request):
        return None
    target = link(request, url_name, args=args, query=query, method=method)
    if target is None:
        return None
    return {"text": str(text), "level": level, "link": target}


# --- «Auf dieser Seite fehlt» ------------------------------------------------------------


def _readiness_rows(request):
    from apps.core import readiness

    memo = getattr(request, "_assistant_rows", None)
    if memo is None:
        memo = readiness.items_for(request.tenant, unknown_on_error=True)
        request._assistant_rows = memo
    return memo


def screen_names(seite: str) -> set[str]:
    return {seite, *SCREEN_EXTRA.get(seite, ())} if seite else set()


def missing_here(request, seite: str) -> list[dict]:
    names = screen_names(seite)
    if not names:
        return []
    out = []
    for row in _readiness_rows(request):
        if row["done"] is True or row.get("url_name") not in names:
            continue
        level = diagnoses.UNKNOWN if row["done"] is None else diagnoses.PROBLEM
        item = _row(request, row["label"], row["url_name"], level=level)
        if item:
            out.append(item)
    return out[:MAX_HERE]


# --- «Gerade wichtig» --------------------------------------------------------------------


def important(request) -> list[dict]:
    from django.utils import formats, timezone

    from apps.core import closures, readiness, storefront_state
    from apps.tenants import onboarding

    tenant = request.tenant
    out: list[dict | None] = []
    reasons = storefront_state.hidden_reasons(tenant)
    if "email_pending" in reasons:
        out.append(
            _row(
                request,
                _("E-Mail-Adresse bestätigen — erst dann sehen Kunden Ihre Website."),
                "owner-confirm-resend",
                method="POST",
                level=diagnoses.PROBLEM,
            )
        )
    if "unpublished" in reasons:
        n = len(onboarding.publish_blockers(tenant, fresh=False))
        text = (
            _("Website veröffentlichen — fehlende Angaben: %(n)s.") % {"n": n}
            if n
            else _("Website veröffentlichen.")
        )
        out.append(_row(request, text, "setup", query="step=recht", level=diagnoses.PROBLEM))
    rng = closures.current_or_next(timezone.localdate(), tenant, horizon=BREAK_DAYS)
    if rng:
        out.append(
            _row(
                request,
                _("Betriebsferien %(von)s – %(bis)s.")
                % {
                    "von": formats.date_format(rng["von"], "SHORT_DATE_FORMAT"),
                    "bis": formats.date_format(rng["bis"], "SHORT_DATE_FORMAT"),
                },
                "betriebsferien",
                level=diagnoses.INFO,
            )
        )
    rows = _readiness_rows(request)
    must = [r for r in rows if r["level"] == readiness.MUST and r["done"] is False]
    if must:
        first = must[0]
        text = (
            _("%(item)s (+%(n)s weitere)") % {"item": first["label"], "n": len(must) - 1}
            if len(must) > 1
            else str(first["label"])
        )
        out.append(_row(request, text, first.get("url_name", ""), level=diagnoses.PROBLEM))
    if any(r["done"] is None for r in rows):
        out.append(
            _row(
                request,
                _("Einige Prüfungen konnten nicht ausgeführt werden."),
                level=diagnoses.UNKNOWN,
            )
        )
    items = [i for i in out if i][:MAX_IMPORTANT]
    if not items:
        items = [{"text": _("Alles Wichtige ist erledigt."), "level": diagnoses.OK, "link": Link()}]
    return items


# --- «Funktioniert etwas nicht?» ---------------------------------------------------------


def _findings(request, found) -> list[dict]:
    out = []
    for f in found:
        item = _row(
            request,
            f.text,
            f.url_name,
            args=f.args,
            query=f.query,
            method=f.method,
            level=f.level,
            owner_only=f.owner_only,
        )
        if item:
            out.append(item)
    return out


def _unknown():
    return [
        {
            "text": _("Konnte nicht geprüft werden — bitte später erneut versuchen."),
            "level": diagnoses.UNKNOWN,
            "link": Link(),
        }
    ]


def diagnosis_cards(request, run_key: str = "") -> list[dict]:
    """Дешёвые диагнозы считаются сразу; тяжёлый — только тот, что запросили кнопкой."""
    cards = []
    for d, known in diagnoses.applicable_status(request.tenant):
        ran = d.cost == diagnoses.CHEAP or d.key == run_key
        if not known:
            found = _unknown()
        elif ran:
            found = _findings(request, diagnoses.run(request.tenant, d.key))
            if not found:  # всё отфильтровано правами — не пустой список под «prüfen»
                found = [
                    {
                        "text": _("Bitte den Inhaber fragen."),
                        "level": diagnoses.INFO,
                        "link": Link(),
                    }
                ]
        else:
            found = None
        cards.append(
            {
                "key": d.key,
                "symptom": d.symptom,
                "heavy": d.cost == diagnoses.HEAVY,
                "findings": found,
                "ok": bool(found) and all(f["level"] == diagnoses.OK for f in found),
            }
        )
    return cards


# --- «Wo stelle ich das ein?» ------------------------------------------------------------


def where_search(request, q: str) -> list[dict]:
    from apps.core import nav_registry

    words = [w for w in (q or "").lower()[:QUERY_MAX].split() if w]
    if not words:
        return []
    out = []
    for e in nav_registry.palette_entries_for(request):
        if not all(w in e["haystack"] for w in words):
            continue
        target = link(request, e["url_name"], query=e.get("query", "").lstrip("?"))
        if target is None or not target.url:
            continue  # палитра не знает белый список Mini App — пост-фильтр
        out.append({"text": str(e["label"]), "area": str(e["area"]), "link": target})
        if len(out) >= MAX_WHERE:
            break
    return out


# --- сборка ------------------------------------------------------------------------------


def _safe(fn, *args, default):
    try:
        return fn(*args), False
    except Exception:  # noqa: BLE001 — сбой блока виден как «nicht geprüft», шторка открывается
        logger.warning("assistant: block %s failed", fn.__name__, exc_info=True)
        return default, True


def build(
    request, *, seite: str = "", q: str = "", run_key: str = "", diagnose: bool = True
) -> dict:
    """`diagnose=False` — поиск/лимит: диагнозы не пересчитываются на каждый ввод."""
    here, here_failed = _safe(missing_here, request, seite, default=[])
    top, top_failed = _safe(important, request, default=[])
    cards, cards_failed = (
        _safe(diagnosis_cards, request, run_key, default=[]) if diagnose else ([], False)
    )
    where, where_failed = _safe(where_search, request, q, default=[])
    return {
        "seite": seite,
        "q": (q or "")[:QUERY_MAX],
        "here": here,
        "important": top,
        "diagnoses": cards,
        "where": where,
        "failed": here_failed or top_failed or cards_failed or where_failed,
        "where_failed": where_failed,
        "diagnosed": diagnose,
    }
