"""Кабинет каналов публикации (TENANT, под логином).

Тумблеры включения каналов + панель статусов последних публикаций. Под gated-
статусом middleware блокирует POST (read-only) и уводит на биллинг.
"""

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import DatabaseError, connection
from django.http import Http404, HttpResponse, HttpResponseForbidden
from django.shortcuts import redirect, render
from django.utils.translation import gettext as _
from django.utils.translation import gettext_lazy
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_POST

from . import oauth
from .models import Channel, Publication


def _ensure_channels():
    """По строке Channel на каждый доступный тип (idempotent)."""
    for type_, _label in Channel.CHANNEL_TYPES:
        Channel.objects.get_or_create(type=type_)


@login_required
def channels(request):
    from apps.core.personal_channels import personal_channels
    from apps.core.roles import is_owner

    _ensure_channels()
    return render(
        request,
        "publishing/channels.html",
        {
            "nav": "channels",
            "channels": Channel.objects.all().order_by("type"),
            # Фидбэк владельца 2026-08-25: рядом с каналами публикации — личные
            # каналы связи (WhatsApp, Telegram, e-mail, чат сайта, соцпрофили).
            "personal_channels": personal_channels(getattr(request, "tenant", None)),
            # Д3 (В-7): подключение/ключи/тумблеры — только владельцу (middleware).
            "can_manage": is_owner(request.user),
            "publications": (Publication.objects.select_related("channel", "promotion").all()[:20]),
        },
    )


@login_required
@require_POST
def channel_toggle(request):
    channel = Channel.objects.filter(type=request.POST.get("type", "")).first()
    if channel is not None:
        channel.is_enabled = not channel.is_enabled
        channel.save(update_fields=["is_enabled", "updated_at"])
        messages.success(request, _("Channel updated."))
    return redirect("channels")


# Конфиг-ключи, редактируемые со страницы каналов (per type).
_CONFIG_FIELDS = {
    Channel.GOOGLE_BUSINESS: ("location", "refresh_token"),
    Channel.FACEBOOK: ("page_id", "access_token"),
    Channel.INSTAGRAM: ("ig_user_id", "access_token"),
    Channel.TELEGRAM: ("bot_token", "chat_id"),
    Channel.PINTEREST: ("access_token", "board_id"),
}


@login_required
@require_POST
def channel_config(request):
    """Сохранить настройки канала. Пустое значение не затирает сохранённое."""
    channel = Channel.objects.filter(type=request.POST.get("type", "")).first()
    fields = _CONFIG_FIELDS.get(channel.type) if channel else None
    if channel is not None and fields:
        from apps.secrets import crypto

        from .secrets import SECRET_KEYS

        updates = {}
        for key in fields:
            value = request.POST.get(key, "").strip()
            if value:
                # секретные подключи шифруем at-rest; неизменённые остаются как есть
                updates[key] = crypto.encrypt(value) if key in SECRET_KEYS else value
        Channel.update_config(channel.pk, lambda config: config.update(updates))
        messages.success(request, _("Channel configuration saved."))
    return redirect("channels")


# --- In-app OAuth подключение каналов (OAuth-A) ------------------------------


@login_required
def oauth_start(request, provider):
    """Увести владельца на провайдера для выдачи доступа (GBP/Pinterest)."""
    if not oauth.supports(provider):
        raise Http404
    return redirect(oauth.authorize_url(provider, connection.schema_name))


def oauth_callback(request, provider):
    """Единый callback на основном домене (public): code → токен → Channel.config.

    Без логина: доверяем подписанному state (схема арендатора). Ошибки —
    короткой страницей, успех — редирект на каналы арендатора.
    """
    if not oauth.supports(provider):
        raise Http404
    schema = oauth.read_state(request.GET.get("state", ""), provider)
    code = request.GET.get("code", "")
    if not schema or not code:
        return HttpResponse(_("Authorization failed. Please try again."), status=400)
    try:
        oauth.complete(provider, schema, code)
    except Exception:  # noqa: BLE001 — показать аккуратную ошибку, не 500
        return HttpResponse(_("Could not complete the connection."), status=502)
    back = oauth.tenant_channels_url(schema)
    return redirect(back) if back else HttpResponse(_("Connected. You can close this tab."))


@login_required
def posts(request):
    """CM-2: контент-календарь — собственные посты (текст/фото/ссылка) с
    отправкой в включённые каналы: «Planen» (к дате, beat send_due_content),
    «Jetzt senden», «Entwurf». Доставка per-канал — Publications (Channels).
    """
    from django.contrib import messages
    from django.core.exceptions import ValidationError
    from django.shortcuts import get_object_or_404, redirect
    from django.utils import timezone
    from django.utils.dateparse import parse_datetime

    from apps.catalog.images import save_product_image

    from .models import Channel, SocialPost
    from .services import publish_post
    from .state_machine import POST_SCHEDULED, POST_SENT, SocialPostSM

    sm = SocialPostSM()

    def _send_now(post):
        post.scheduled_at = timezone.now()
        post.save(update_fields=["scheduled_at", "updated_at"])
        if post.status == SocialPost.DRAFT:
            sm.apply(post, POST_SCHEDULED)
        publish_post(post)
        sm.apply(post, POST_SENT)

    if request.method == "POST":
        action = request.POST.get("action", "")
        pk = request.POST.get("pk", "")
        if action in ("delete", "send_now") and pk:
            post = get_object_or_404(SocialPost, pk=pk)
            if action == "delete":
                post.delete()
                messages.success(request, _("Post deleted."))
            elif post.status != SocialPost.SENT:
                _send_now(post)
                messages.success(request, _("Post sent to channels."))
            return redirect("publishing-posts")
        text = (request.POST.get("text") or "").strip()
        if not text:
            messages.error(request, _("Text is required."))
            return redirect("publishing-posts")
        image = {}
        uploaded = request.FILES.get("image")
        if uploaded is not None:
            try:
                image = save_product_image(uploaded, folder="posts")
            except ValidationError as exc:
                messages.error(request, "; ".join(exc.messages))
                return redirect("publishing-posts")
        when = parse_datetime((request.POST.get("scheduled_at") or "").strip())
        if when is not None and timezone.is_naive(when):
            when = timezone.make_aware(when)
        post = SocialPost.objects.create(
            text=text,
            link_url=(request.POST.get("link_url") or "").strip(),
            image=image,
        )
        if action == "now":
            _send_now(post)
            messages.success(request, _("Post sent to channels."))
        elif action == "schedule" and when is not None:
            post.scheduled_at = when
            post.save(update_fields=["scheduled_at", "updated_at"])
            sm.apply(post, POST_SCHEDULED)
            messages.success(request, _("Post scheduled."))
        else:
            messages.success(request, _("Draft saved."))  # без даты — черновик
        return redirect("publishing-posts")

    return render(
        request,
        "publishing/posts.html",
        {
            "nav": "posts",
            # CM-3: префилл из кнопок «Teilen» (блог/событие/товар) — GET-параметры.
            "prefill_text": (request.GET.get("text") or "")[:2000],
            "prefill_link": (request.GET.get("link") or "")[:500],
            "scheduled": SocialPost.objects.filter(status=SocialPost.SCHEDULED).order_by(
                "scheduled_at"
            ),
            "drafts": SocialPost.objects.filter(status=SocialPost.DRAFT),
            "sent": SocialPost.objects.filter(status=SocialPost.SENT).order_by("-scheduled_at")[
                :20
            ],
            "has_channels": Channel.objects.filter(is_enabled=True).exists(),
        },
    )


# --- Д3 «GBP-Sync»: экран «Google-Profil» (docs/d3-gbp-sync-plan-2026-10-18.md) --------

GBP_LOAD_LIMIT = 1  # запросов к Google в минуту на бизнес с кнопки
GBP_LOAD_WINDOW = 60

GBP_ERROR_MESSAGES = {
    "not_configured": gettext_lazy("Bitte zuerst mit Google verbinden."),
    "not_approved": gettext_lazy("Google-API noch nicht freigeschaltet"),
    "auth": gettext_lazy("Google-Verbindung abgelaufen – bitte neu verbinden"),
    "quota": gettext_lazy("Google-Kontingent erreicht – später erneut versuchen"),
    "not_found": gettext_lazy("Standort bei Google nicht gefunden"),
    "network": gettext_lazy("Google ist gerade nicht erreichbar – später erneut versuchen"),
    "bad_response": gettext_lazy("Unerwartete Antwort von Google – später erneut versuchen"),
}


def _owner(request) -> bool:
    """Вторая линия к owner-only префиксу middleware: экран пишет во внешний профиль."""
    from apps.core.roles import is_owner

    return is_owner(request.user)


def _gbp_channel():
    channel, _created = Channel.objects.get_or_create(type=Channel.GOOGLE_BUSINESS)
    return channel


def _gbp_sync_update(channel_pk, **fields) -> None:
    """Точечная запись `config["gbp_sync"]` под блокировкой строки — чужие ключи целы."""
    from django.utils import timezone

    def mutate(config):
        state = dict(config.get("gbp_sync") or {})
        state.update(fields)
        state["checked_at"] = timezone.now().isoformat()
        config["gbp_sync"] = state

    Channel.update_config(channel_pk, mutate)


@login_required
def gbp_sync(request):
    """Экран «Google-Profil»: подключение, выбор локации (Д3-1); часы и офферы — Д3-2/3."""
    from apps.core import ratelimit

    from . import gbp
    from .secrets import decrypted_config

    if not _owner(request):
        return HttpResponseForbidden(_("Nur für Inhaber."))
    channel = _gbp_channel()
    config = decrypted_config(channel)
    locations = None
    error_code = ""
    rate_limited = False
    if request.method == "POST" and request.POST.get("action") == "load":
        schema = getattr(connection, "schema_name", "") or ""
        if ratelimit.hit("gbp-sync", schema, limit=GBP_LOAD_LIMIT, window=GBP_LOAD_WINDOW):
            rate_limited = True
            messages.error(request, _("Bitte einen Moment warten und erneut versuchen."))
        else:
            try:
                locations = gbp.all_locations(config)
                _gbp_sync_update(channel.pk, last_error_code="", last_status=0)
            except gbp.GbpError as exc:
                error_code = exc.code
                _gbp_sync_update(channel.pk, last_error_code=exc.code, last_status=exc.status)
            channel.refresh_from_db()
    return _gbp_render(
        request, channel, config, locations=locations, error_code=error_code, quiet=rate_limited
    )


def _gbp_render(request, channel, config, *, error_code="", quiet=False, **extra):
    """Экран «Google-Profil». `quiet` — не показывать сохранённую ошибку (лимит частоты)."""
    state = (channel.config or {}).get("gbp_sync") or {}
    if not quiet:  # иначе рядом с «подождите» висел бы старый баннер
        error_code = error_code or state.get("last_error_code") or ""
    context = {
        "nav": "channels",
        "channel": channel,
        "connected": bool(config.get("refresh_token")),
        "location": config.get("location") or "",
        "locations": None,
        "hours_diff": None,
        "hours_confirm": "",
        "gbp_state": state,
        "hours_synced_at": _latest(state.get("hours_pushed_at"), state.get("hours_pulled_at")),
        "error_code": error_code,
        "error_message": GBP_ERROR_MESSAGES.get(error_code, ""),
    }
    context.update(extra)
    return render(request, "publishing/gbp_sync.html", context)


GBP_HOURS_MESSAGES = {
    "empty": gettext_lazy("Bitte zuerst Öffnungszeiten eintragen – leere Zeiten senden wir nicht."),
    "google_empty": gettext_lazy(
        "Bei Google sind keine Öffnungszeiten hinterlegt – es gibt nichts zu übernehmen."
    ),
    "lossy": gettext_lazy(
        "Bei Google sind geteilte Öffnungszeiten hinterlegt. Trotzdem überschreiben?"
    ),
    "closes_at_google": gettext_lazy(
        "Bei Google geöffnete Tage würden geschlossen. Bitte prüfen und bestätigen."
    ),
    "confirm_pull": gettext_lazy("Bitte die Änderungen prüfen und die Übernahme bestätigen."),
}


@login_required
@require_POST
def gbp_hours(request):
    """Часы ↔ Google (Д3-2): action=preview | push | pull_apply. Каждое действие сначала
    читает Google заново — решение не опирается на устаревший предпросмотр в браузере."""
    from apps.core import ratelimit

    from . import gbp
    from . import gbp_hours as hours
    from .secrets import decrypted_config

    if not _owner(request):
        return HttpResponseForbidden(_("Nur für Inhaber."))
    action = request.POST.get("action", "")
    if action not in ("preview", "push", "pull_apply"):
        return redirect("gbp-sync")
    channel = _gbp_channel()
    config = decrypted_config(channel)
    schema = getattr(connection, "schema_name", "") or ""
    if ratelimit.hit("gbp-hours", schema, limit=hours.ACTION_LIMIT, window=hours.ACTION_WINDOW):
        messages.error(request, _("Bitte einen Moment warten und erneut versuchen."))
        return _gbp_render(request, channel, config, quiet=True)
    tenant = request.tenant
    diff, confirm_needed, error_code = None, "", ""
    try:
        if action == "preview":
            diff = hours.fetch(tenant, config)
        elif action == "push":
            hours.push(tenant, config, confirm=request.POST.get("confirm") == "overwrite")
            _gbp_sync_update(channel.pk, last_error_code="", last_status=0, hours_pushed_at=_now())
            messages.success(request, _("Öffnungszeiten an Google gesendet."))
        else:
            hours.pull_apply(tenant, config, confirm=request.POST.get("confirm") == "pull")
            _gbp_sync_update(channel.pk, last_error_code="", last_status=0, hours_pulled_at=_now())
            messages.success(request, _("Öffnungszeiten von Google übernommen."))
    except hours.HoursError as exc:
        diff = exc.diff
        confirm_needed = (
            "pull"
            if exc.code == "confirm_pull"
            else ("push" if exc.code in ("lossy", "closes_at_google") else "")
        )
        messages.error(request, GBP_HOURS_MESSAGES[exc.code])
    except gbp.GbpError as exc:
        error_code = exc.code
        _gbp_sync_update(channel.pk, last_error_code=exc.code, last_status=exc.status)
    channel.refresh_from_db()
    return _gbp_render(
        request,
        channel,
        config,
        error_code=error_code,
        quiet=not error_code,
        hours_diff=diff,
        hours_confirm=confirm_needed,
    )


def _latest(*stamps):
    """Самая поздняя из ISO-отметок как datetime (для «Zuletzt abgeglichen») или None."""
    from django.utils.dateparse import parse_datetime

    parsed = [parse_datetime(x) for x in stamps if isinstance(x, str)]
    parsed = [x for x in parsed if x is not None]
    return max(parsed) if parsed else None


def _now() -> str:
    from django.utils import timezone

    return timezone.now().isoformat()


@login_required
@require_POST
def gbp_location(request):
    """Сохранить выбранную локацию (v4-имя). Чужие ключи конфига (токен) не трогаются."""
    from . import gbp

    if not _owner(request):
        return HttpResponseForbidden(_("Nur für Inhaber."))
    location = (request.POST.get("location") or "").strip()
    if not gbp.LOCATION_RE.fullmatch(location):
        messages.error(request, _("Bitte zuerst einen Standort wählen"))
        return redirect("gbp-sync")
    channel = _gbp_channel()
    Channel.update_config(channel.pk, lambda config: config.__setitem__("location", location))
    messages.success(request, _("Standort gespeichert."))
    return redirect("gbp-sync")


MERCHANT_ADMIN_LIMIT = 10  # действий с фидом в минуту на бизнес
MERCHANT_ADMIN_WINDOW = 60


def _merchant_store_code(request, channel, raw) -> None:
    from . import merchant

    value = merchant.clean_store_code(raw)
    if value is None:
        messages.error(
            request,
            _("Ungültiger Shopcode: höchstens 64 Zeichen, ohne Leerzeichen und Umlaute."),
        )
    elif not value:
        merchant.set_store_code(channel.pk, "")
        messages.success(request, _("Shopcode entfernt. Der lokale Feed ist jetzt leer."))
    else:
        merchant.set_store_code(channel.pk, value)
        messages.success(request, _("Shopcode gespeichert."))


def _merchant_store_from_google(request, channel) -> None:
    """Код магазина из профиля Google. Токен и ответ Google в сообщения не попадают."""
    from . import gbp, merchant
    from .secrets import decrypted_config

    config = decrypted_config(channel)
    try:
        _v4, v1 = gbp.location_ids(config)
        raw = gbp.get_store_code(gbp.access_token(config), v1)
    except gbp.GbpError as exc:
        if exc.code == "not_configured":
            messages.error(
                request,
                _("Bitte zuerst das Google-Profil verbinden und einen Standort wählen."),
            )
        else:
            messages.error(
                request, GBP_ERROR_MESSAGES.get(exc.code) or GBP_ERROR_MESSAGES["bad_response"]
            )
        return
    value = merchant.clean_store_code(raw)
    if value is None:
        messages.error(
            request,
            _(
                "Der Shopcode im Google-Profil enthält unzulässige Zeichen "
                "(nur ASCII, keine Leerzeichen, höchstens 64 Zeichen)."
            ),
        )
        return
    if not value:
        messages.error(request, _("Im Google-Profil ist kein Shopcode hinterlegt."))
        return
    merchant.set_store_code(channel.pk, value)
    messages.success(request, _("Shopcode aus dem Google-Profil übernommen."))


def _merchant_feed_url(request, token: str, name: str = "storefront-merchant-feed") -> str:
    """Адрес фида на ОСНОВНОМ домене бизнеса — он не меняется от того, через какой
    домен владелец открыл кабинет (у своего домена поддомен отвечает 301)."""
    from django.urls import reverse

    path = reverse(name, args=[token])
    tenant = getattr(request, "tenant", None)
    try:
        primary = tenant.domains.filter(is_primary=True).order_by("pk").first() if tenant else None
    except (DatabaseError, ValueError):  # ValueError — тенант без pk (тест/сборка)
        primary = None
    if primary:
        return f"{request.scheme}://{primary.domain}{path}"
    return request.build_absolute_uri(path)


@never_cache  # страница несёт секретный адрес фида — не держать в кэше браузера
@login_required
def merchant_feed(request):
    """Экран «Google Merchant Center» (M23b.2): включить фид, адрес, новый адрес, что в фиде.

    Не зависит от подключения Google и от переключателя канала — владелец вносит адрес
    в Merchant Center сам. Конфиг канала в шаблон не передаём целиком."""
    from apps.catalog import google
    from apps.core import ratelimit

    from . import merchant

    if not _owner(request):
        return HttpResponseForbidden(_("Nur für Inhaber."))
    channel = merchant.channel()
    if request.method == "POST":
        action = request.POST.get("action", "")
        schema = getattr(connection, "schema_name", "") or ""
        if action not in ("enable", "disable", "rotate", "store_code", "store_from_google"):
            return redirect("gbp-merchant")
        if ratelimit.hit(
            "merchant-feed-admin", schema, limit=MERCHANT_ADMIN_LIMIT, window=MERCHANT_ADMIN_WINDOW
        ):
            messages.error(request, _("Bitte einen Moment warten und erneut versuchen."))
            return redirect("gbp-merchant")
        if action == "store_code":
            _merchant_store_code(request, channel, request.POST.get("store_code", ""))
        elif action == "store_from_google":
            _merchant_store_from_google(request, channel)
        elif action == "enable":
            merchant.enable(channel.pk)
            messages.success(request, _("Der Produktfeed ist eingeschaltet."))
        elif action == "disable":
            merchant.disable(channel.pk)
            messages.success(
                request, _("Der Produktfeed ist ausgeschaltet. Google erhält einen leeren Feed.")
            )
        elif (
            request.POST.get("confirm") == "rotate" or merchant.feed_state(channel)["token"] is None
        ):  # нечитаемый адрес уже не работает — подтверждать нечего
            merchant.rotate(channel.pk)
            messages.success(
                request,
                _("Neue Adressen erzeugt. Bitte beide in Merchant Center ersetzen."),
            )
        else:
            messages.error(request, _("Bitte bestätigen, dass die alte Adresse ungültig wird."))
        return redirect("gbp-merchant")

    state = merchant.feed_state(channel)
    data = google.overview()
    excluded = [
        {
            "code": code,
            "label": google.REASON_LABELS.get(code, code),
            "count": group["count"],
            "items": [
                {"product": p, "labels": [google.REASON_LABELS.get(r, r) for r in reasons]}
                for p, reasons in group["items"]
            ],
        }
        for code, group in data["excluded"].items()
    ]
    warnings = [
        {
            "code": code,
            "label": google.WARNING_LABELS.get(code, code),
            "count": group["count"],
            "items": group["items"],
        }
        for code, group in data["warnings"].items()
    ]
    context = {
        "nav": "channels",
        "enabled": state["enabled"],
        "issued_at": state["issued_at"],
        "feed_url": _merchant_feed_url(request, state["token"]) if state["token"] else "",
        "local_feed_url": (
            _merchant_feed_url(request, state["token"], "storefront-merchant-local-feed")
            if state["token"]
            else ""
        ),
        "store_code": state["store_code"],
        "gbp_location_set": bool((channel.config or {}).get("location")),
        "local": data["local"],
        "token_unreadable": bool(state["enabled"] and not state["token"]),
        "included": data["included"],
        "excluded": excluded,
        "warnings": warnings,
    }
    return render(request, "publishing/merchant_feed.html", context)
