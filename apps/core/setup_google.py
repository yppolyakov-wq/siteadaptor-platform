"""AIS W4-3: «Bei Google suchen» в шаге «Firma» мастера v4.

План — docs/ais-w4-3-google-profile-plan-2026-11-06.md. Один POST-приёмник
(`action` = search | pick | apply | cancel), PRG обратно на шаг — работает без JS.
* Нет ключа Places или не мастер v4 — блока нет, приёмник 404.
* Лимиты ДО запроса в Google (каждый запрос платный): сеть /64 и бизнес; сбой Google
  возвращает попытку.
* Найденное и выбранное лежит в СЕРВЕРНОМ кэше пользователя 15 мин; «Übernehmen» пишет из кэша
  только отмеченные поля (данные из POST не принимаются) + `google_place_id`.
* Поле, где у владельца уже есть значение, по умолчанию не отмечено (класс W0).
"""

from __future__ import annotations

import logging
from dataclasses import asdict

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import Http404
from django.shortcuts import redirect
from django.urls import reverse
from django.utils.translation import gettext as _
from django.views.decorators.http import require_POST

logger = logging.getLogger(__name__)

TTL = 15 * 60
SEARCH_NET, SEARCH_TENANT = (10, 3600), (20, 86400)
PICK_NET, PICK_TENANT = (5, 3600), (10, 86400)
#: поля, которые Google может предложить (ключ данных → поле Tenant)
FIELDS = (
    ("address", "address"),
    ("city", "city"),
    ("phone", "contact_phone"),
    ("website", "website_url"),
    ("hours", "opening_hours_structured"),
)


def enabled(tenant) -> bool:
    from apps.tenants import google_places, onboarding

    try:
        return bool(google_places.api_key()) and onboarding.is_v4(tenant)
    except Exception:  # noqa: BLE001 — блок-дополнение не роняет шаг мастера
        logger.exception("setup google: enabled check failed")
        return False


def _key(request) -> str:
    from django.db import connection

    return f"gplaces:{connection.schema_name}:{request.user.pk}"


def _state(request) -> dict:
    from django.core.cache import cache

    try:
        got = cache.get(_key(request))
    except Exception:  # noqa: BLE001 — Redis недоступен: блок пустой, мастер работает
        logger.warning("setup google: cache read failed", exc_info=True)
        return {}
    return got if isinstance(got, dict) else {}


def _save(request, state: dict) -> None:
    from django.core.cache import cache

    cache.set(_key(request), state, TTL)


def _limited(request, scope: str, net: tuple, per_tenant: tuple) -> list | None:
    """Лимит сети и бизнеса. Возвращает засчитанные попытки (для возврата при сбое) или None."""
    from django.db import connection

    from apps.core import ratelimit

    scopes = [
        (f"{scope}-n", ratelimit.client_net(request), net),
        (f"{scope}-t", connection.schema_name, per_tenant),
    ]
    taken = []
    for name, ident, (limit, window) in scopes:
        if ratelimit.hit(name, ident, limit=limit, window=window):
            for done in taken:
                ratelimit.refund(*done)
            return None
        taken.append((name, ident))
    return taken


def _refund(taken) -> None:
    from apps.core import ratelimit

    for name, ident in taken or ():
        ratelimit.refund(name, ident)


def _lang(request) -> str:
    from django.utils import translation

    return (translation.get_language() or "de")[:2]


def _current(tenant) -> dict:
    from apps.tenants import openinghours

    return {
        "address": tenant.address or "",
        "city": tenant.city or "",
        "phone": tenant.contact_phone or "",
        "website": getattr(tenant, "website_url", "") or "",
        "hours": openinghours.normalize(tenant.opening_hours_structured),
    }


def _hours_text(hours) -> str:
    from apps.tenants import openinghours

    hours = openinghours.normalize(hours)
    return " · ".join(
        f"{openinghours.weekday_abbr(wd)} {hours[str(wd)][0]}–{hours[str(wd)][1]}"
        for wd in range(7)
        if str(wd) in hours
    )


def _labels() -> dict:
    return {
        "address": _("Adresse"),
        "city": _("Stadt"),
        "phone": _("Telefon"),
        "website": _("Website"),
        "hours": _("Öffnungszeiten"),
    }


def context(request) -> dict:
    """Данные блока для шаблона шага: найденные карточки или таблица сравнения."""
    if not enabled(request.tenant):
        return {"google_enabled": False}
    state = _state(request)
    ctx = {"google_enabled": True, "google_hits": state.get("hits") or []}
    data = state.get("data")
    if data:
        now = _current(request.tenant)
        labels = _labels()
        rows = []
        for key, _field in FIELDS:
            new = data.get(key)
            if not new:
                continue
            old = now.get(key)
            show = _hours_text(new) if key == "hours" else new
            show_old = _hours_text(old) if key == "hours" else (old or "")
            rows.append(
                {
                    "key": key,
                    "label": labels[key],
                    "new": show,
                    "old": show_old,
                    "same": new == old,
                    "checked": not old,  # W0: заполненное владельцем — не отмечено
                }
            )
        ctx["google_rows"] = rows
        ctx["google_hours_partial"] = bool(data.get("hours_partial"))
    return ctx


def _log(exc, what: str) -> None:
    from apps.tenants import google_places as gp

    if isinstance(exc, gp.PlacesError):
        logger.warning("setup google: %s failed: %s", what, exc)
    else:
        logger.exception("setup google: %s unexpected answer", what)


def _back():
    return redirect(f"{reverse('setup')}?step=company#google")


@login_required
@require_POST
def setup_google(request):
    from apps.tenants import google_places as gp

    if not enabled(request.tenant):
        raise Http404
    action = request.POST.get("action", "")
    if action == "cancel":
        _save(request, {})
        return _back()
    if action == "search":
        query = " ".join((request.POST.get("g_name") or "").split())[:80]
        city = " ".join((request.POST.get("g_city") or request.tenant.city or "").split())[:80]
        if len(query) < 2:
            messages.error(request, _("Bitte den Namen Ihres Geschäfts eingeben."))
            return _back()
        taken = _limited(request, "gplaces-search", SEARCH_NET, SEARCH_TENANT)
        if taken is None:
            messages.error(request, _("Zu viele Suchen — bitte später erneut versuchen."))
            return _back()
        try:
            hits = gp.search_places(query, city, lang=_lang(request))
        except Exception as exc:  # noqa: BLE001 — PlacesError и неожиданный ответ: попытку назад
            _log(exc, "search")
            _refund(taken)
            messages.error(request, _("Google ist gerade nicht erreichbar — bitte später erneut."))
            return _back()
        _save(request, {"hits": [asdict(h) for h in hits]})
        if not hits:
            messages.info(request, _("Nichts gefunden — bitte Namen oder Ort anders schreiben."))
        return _back()
    if action == "pick":
        state = _state(request)
        pid = request.POST.get("place_id", "")
        # выбрать можно только из СВОИХ найденных (не произвольный id — каждый платный)
        if pid not in {h.get("place_id") for h in state.get("hits") or []}:
            messages.error(request, _("Bitte zuerst suchen und einen Eintrag wählen."))
            return _back()
        taken = _limited(request, "gplaces-pick", PICK_NET, PICK_TENANT)
        if taken is None:
            messages.error(request, _("Zu viele Abrufe — bitte später erneut versuchen."))
            return _back()
        try:
            data = gp.place_details(pid, lang=_lang(request))
        except Exception as exc:  # noqa: BLE001 — PlacesError и неожиданный ответ: попытку назад
            _log(exc, "details")
            _refund(taken)
            messages.error(request, _("Google ist gerade nicht erreichbar — bitte später erneut."))
            return _back()
        _save(request, {"hits": state.get("hits") or [], "data": asdict(data)})
        return _back()
    if action == "apply":
        return _apply(request)
    raise Http404


def _apply(request):
    from apps.tenants import openinghours

    state = _state(request)
    data = state.get("data") or {}
    if not data.get("place_id"):
        messages.error(request, _("Die Google-Daten sind abgelaufen — bitte erneut suchen."))
        return _back()
    tenant = request.tenant
    wanted = set(request.POST.getlist("g_field"))
    fields = []
    for key, field in FIELDS:
        if key not in wanted or not data.get(key):
            continue
        value = data[key]
        if key == "hours":
            value = openinghours.normalize(value)
            if not value:
                continue
        setattr(tenant, field, value)
        fields.append(field)
    if not fields:  # ничего не отмечено — и профиль не привязываем (чужой рейтинг не показать)
        messages.info(request, _("Nichts übernommen."))
        _save(request, {})
        return _back()
    if tenant.google_place_id != data["place_id"]:
        # другое место: рейтинг прежнего не должен висеть на витрине до ночного обновления
        tenant.google_place_id = data["place_id"]
        tenant.google_rating = None
        tenant.google_rating_count = 0
        tenant.google_rating_updated_at = None
        fields += [
            "google_place_id",
            "google_rating",
            "google_rating_count",
            "google_rating_updated_at",
        ]
    tenant.save(update_fields=[*fields, "updated_at"])
    _save(request, {})
    messages.success(request, _("Angaben von Google übernommen — bitte kurz prüfen."))
    return _back()
