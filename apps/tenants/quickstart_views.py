"""T-8.5 «Aktion in 3 Klicks»: страница ``/aktion-starten/`` и ожидание провижининга.

План — docs/t8-5-quick-start-plan-2026-10-10.md §1. Клик 1 «Weiter» (акция), клик 2
«Veröffentlichen» (бизнес + e-mail), клик 3 — «Teilen» на экране «Fertig» поддомена.
"""

from __future__ import annotations

import logging
from datetime import timedelta
from urllib.parse import urlencode

from django.conf import settings
from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.db import IntegrityError
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.translation import gettext as _
from django.views.decorators.http import require_POST

from apps.core import city_categories, ratelimit
from apps.core.archetypes import FOOD_BUSINESS_TYPES
from apps.promotions.quick import MAX_PHOTOS

from . import quickstart
from .models import Tenant
from .services import login_url_for, site_url_for, start_quick_provisioning

logger = logging.getLogger(__name__)

# Ожидание: схема готова, а ключ акции пропал — через READY_GRACE ведём в список
# акций; PENDING дольше STALE_AFTER — задача потеряна, круг не крутим вечно.
READY_GRACE = timedelta(minutes=3)
STALE_AFTER = timedelta(minutes=15)
SESSION_KEY = "quick_handoff"  # {slug: {"token": ..., "title": ..., "price": ...}}


KEPT_PHOTOS_SALT = "quick-start-kept-photos"
KEPT_PHOTOS_MAX_AGE = 3600


def _sign_photos(refs) -> str:
    from django.core import signing

    return signing.dumps(list(refs or []), salt=KEPT_PHOTOS_SALT, compress=True)


def _kept_photos(request) -> list:
    """Фото прошлой попытки (подписаны сервером — путь чужого файла не подставить)."""
    from django.core import signing

    raw = request.POST.get("photos_kept", "")
    if not raw:
        return []
    try:
        refs = signing.loads(raw, salt=KEPT_PHOTOS_SALT, max_age=KEPT_PHOTOS_MAX_AGE)
    except signing.BadSignature:
        return []
    if not isinstance(refs, list):
        return []
    ok = [
        r for r in refs if isinstance(r, dict) and str(r.get("path", "")).startswith("promotions/")
    ]
    return ok[:MAX_PHOTOS]


def _drop_photos(refs) -> None:
    from apps.catalog.images import delete_stored_image

    for ref in refs or []:
        delete_stored_image(ref)


def _context(request, form, kept_photos=None, kept_signed=""):
    from apps.platform_bot import web_signup

    from .views import ui_languages

    return {
        "form": form,
        # Фото прошлой попытки: показываем и отправляем снова (форма с файлами их теряет).
        "source_images": kept_photos or [],
        "photos_kept": kept_signed or (_sign_photos(kept_photos) if kept_photos else ""),
        # T-8.30i: пришли из Mini App — после почты «Mein Laden» откроет этот бизнес.
        "tg_linked": web_signup.from_session(request),
        "type_cards": quickstart.type_cards(request),
        "stamp": quickstart.form_stamp(),
        "domain_base": quickstart.domain_base(),
        "known_cities": quickstart.known_cities(),
        "district_options": _district_options(),
        "max_photos": MAX_PHOTOS,
        "category_suggestions": dict(city_categories.BY_BUSINESS_TYPE),
        "category_allowed": city_categories.allowed_by_type(),
        "ui_languages": ui_languages(),
        # ИИ — только после регистрации (расход считается на бизнес и его дневной
        # лимит; анонимная страница бюджет не тратит) — здесь лишь честная подсказка.
        "ai_after_signup": _ai_enabled(),
        # T-8.5e: проверка текста без входа (свой эндпоинт публичного хоста; ИИ-кнопки нет).
        "text_check_url": reverse("quick-start-text-check", urlconf="config.urls_public"),
        "food_types": sorted(FOOD_BUSINESS_TYPES),
    }


def _ai_enabled() -> bool:
    from apps.ai.api import is_enabled

    return is_enabled()


def _district_options() -> list[dict]:
    from apps.core import districts

    return districts.all_options()


def quick_start(request):
    if request.method == "GET":
        from .views import _capture_partner_ref

        _capture_partner_ref(request)
        form = quickstart.QuickStartForm(initial={"term": "week", "customer_response": "reserve"})
        return render(request, "tenants/quick_start.html", _context(request, form))

    form = quickstart.QuickStartForm(request.POST, request.FILES)
    # Бот: скрытое поле заполнено — форма возвращается как есть, ничего не создаём.
    if (request.POST.get("website") or "").strip():
        return render(request, "tenants/quick_start.html", _context(request, form))
    if not form.is_valid():
        return render(request, "tenants/quick_start.html", _context(request, form))
    stamp = request.POST.get("stamp", "")
    if quickstart.too_fast(stamp):
        form.add_error(None, _("Bitte prüfen Sie Ihre Angaben und senden Sie erneut."))
        return render(request, "tenants/quick_start.html", _context(request, form))

    # T-8.30k: повторная отправка той же формы (второй тап, пока грузятся фото) — не
    # вторая регистрация и не «Zu viele Versuche», а тот же результат, что у первой.
    key, done = _claim_submit(request, stamp)
    if done == "busy":
        form.add_error(None, _("Ihr Geschäft wird gerade angelegt — einen Moment bitte."))
        return render(request, "tenants/quick_start.html", _context(request, form))
    if done:
        if done["entry"].get("tg"):
            from apps.platform_bot import web_signup

            web_signup.forget(request)  # как у первой отправки: метка Telegram израсходована
        handoff = dict(request.session.get(SESSION_KEY) or {})
        handoff[done["slug"]] = done["entry"]
        request.session[SESSION_KEY] = handoff
        return redirect(f"/aktion-starten/{done['slug']}/")
    finished = False
    try:
        response, result = _publish(request, form)
        if result:
            cache.set(key, result, SUBMIT_TTL)
            finished = True
        return response
    finally:
        if not finished:
            cache.delete(key)  # не создано — следующая попытка с той же формой свободна


SUBMIT_TTL = 10 * 60  # результат опубликованной формы
BUSY_TTL = 90  # «идёт отправка»: убитый воркер не держит форму дольше
SUBMIT_WAIT = 5  # сек: второй запрос недолго ждёт первый (sync-воркер не держим)


def _claim_submit(request, stamp: str):
    """(ключ, None) — запрос первый, публикуем; (ключ, dict) — уже опубликовано;
    (ключ, "busy") — первая отправка всё ещё идёт дольше ``SUBMIT_WAIT``.

    Ключ — хэш подписанной метки формы (своя у каждой отрисовки) И CSRF-куки браузера
    (ревью: утёкшая метка из чужого браузера даёт другой ключ — результата, а с ним
    входа в кабинет, не получить). Ключ сессии не годится: при двойном тапе до первого
    ответа сессии ещё нет, а CSRF-кука есть с GET."""
    import hashlib
    import time

    bind = request.COOKIES.get(settings.CSRF_COOKIE_NAME, "")
    key = "qs-submit:" + hashlib.sha256(f"{stamp}|{bind}".encode()).hexdigest()
    deadline = time.monotonic() + SUBMIT_WAIT
    waited = False
    while True:
        try:
            if cache.add(key, "busy", BUSY_TTL):
                return key, None
            state = cache.get(key)
        except Exception:  # noqa: BLE001 — кэш недоступен: обычная отправка
            return key, None
        if isinstance(state, dict):
            return key, state
        if not waited:
            waited = True
            # Ожидание держит воркер — не больше нескольких раз в минуту с одного адреса.
            if ratelimit.hit("quick-start-wait", ratelimit.client_ip(request), limit=10, window=60):
                return key, "busy"
        if time.monotonic() > deadline:
            return key, "busy"
        # state is None — первая отправка не удалась и освободила ключ: пробуем сами.
        time.sleep(0.5)


def _publish(request, form):
    """Сама публикация: (ответ, результат). Результат {slug, entry} — бизнес создан."""

    def page(kept=None, signed=""):
        return render(request, "tenants/quick_start.html", _context(request, form, kept, signed))

    cd = form.cleaned_data
    promo = form.promo_payload()
    uploads = cd.get("photo") or []
    kept = _kept_photos(request)
    if uploads and kept:
        _drop_photos(kept)  # выбраны новые фото — прежние больше не нужны
        kept = []
    # Формат фото проверяем ДО лимита: исправимая ошибка не должна сжигать попытки.
    if uploads:
        from apps.catalog.images import validate_image

        try:
            for upload in uploads:
                validate_image(upload)
        except ValidationError as exc:
            form.add_error("photo", "; ".join(exc.messages))
            return page(), None
    ip = ratelimit.client_ip(request)
    if ratelimit.hit("quick-start", ip, limit=5, window=3600):
        logger.info("quick-start limited: ip")
        form.add_error(
            None, _("Zu viele Versuche aus diesem Netzwerk. Bitte in einer Stunde erneut.")
        )
        # Подпись не обновляем: срок жизни сохранённых фото считается от первой попытки.
        return page(kept, request.POST.get("photos_kept", "") if kept else ""), None
    # Дальше любой отказ без побочного эффекта возвращает засчитанные попытки.
    hits = [("quick-start", ip)]
    if uploads:
        from apps.promotions.quick import save_photos

        try:
            promo["images"] = save_photos(uploads)
        except ValidationError as exc:
            _refund(hits)
            form.add_error("photo", "; ".join(exc.messages))
            return page(), None
    elif kept:
        promo["images"] = kept

    # Лимиты Telegram-регистрации — после проверки фото: неудачная попытка квоту не жжёт.
    tg = _telegram_gate(request, form, cd["email"])
    if tg is False:
        _refund(hits)
        # Окончательный отказ (лимит/Art. 18) — повтор не поможет, файлы не держим.
        _drop_photos(promo.get("images"))
        return page(), None
    if tg:
        from apps.platform_bot import signup

        hits += tg["hits"]
        # Метка «создаётся» — до запуска (как в боте): Mini App сразу отвечает `pending`.
        signup.cache.set(signup._pending_key(tg["uid"]), 1, signup.PENDING_TTL)
    try:
        tenant = start_quick_provisioning(
            business_name=cd["business_name"].strip(),
            slug=cd.get("subdomain") or quickstart.suggest_slug(cd["business_name"]),
            business_type=cd["business_type"],
            city=cd["city"],
            district=cd.get("district") or "",
            email=cd["email"],
            address=form.address_line(),
            phone=cd["phone"],
            promo=promo,
            partner_code=request.session.get("partner_ref", ""),
            in_city_catalog=cd.get("in_city_catalog", False),
            telegram={"tg_user_id": tg["uid"], "lang": tg["lang"]} if tg else None,
        )
    except IntegrityError:
        # Гонка: адрес заняли между проверкой и сохранением — просим выбрать другой.
        # Транзакция откатилась, бизнеса нет — попытки возвращаем.
        _refund(hits)
        _clear_tg_pending(tg)
        form.add_error("subdomain", _("Diese Adresse ist schon vergeben."))
        # Исправимо (другой адрес) — фото уже сохранены, отдаём их обратно в форму.
        signed = request.POST.get("photos_kept", "") if (kept and not uploads) else ""
        return page(promo.get("images"), signed), None
    except Exception:
        _clear_tg_pending(tg)  # иначе Mini App полчаса показывал бы «wird angelegt»
        raise
    request.session.pop("partner_ref", None)
    from apps.core import owner_login

    handoff = dict(request.session.get(SESSION_KEY) or {})
    entry = {
        "title": cd["title"],
        "image": (promo.get("images") or [{}])[0].get("url", ""),
    }
    if tg:
        # T-8.30i (Р-1): из Telegram кабинет до почты не открываем — только «Fertig».
        from apps.platform_bot import web_signup

        web_signup.forget(request)
        entry.update(tg=True, mail=_mask(cd["email"]))
    else:
        entry["token"] = owner_login.issue_token(tenant.schema_name, cd["email"])
    handoff[tenant.slug] = entry
    request.session[SESSION_KEY] = handoff
    # Литеральный путь: страницы платформы рендерятся и под tenant-urlconf (тесты).
    return redirect(f"/aktion-starten/{tenant.slug}/"), {"slug": tenant.slug, "entry": entry}


def _refund(hits) -> None:
    for scope, ident in hits:
        ratelimit.refund(scope, ident)


def _clear_tg_pending(tg) -> None:
    if tg:
        from apps.platform_bot import signup

        signup.cache.delete(signup._pending_key(tg["uid"]))


def _mask(email: str) -> str:
    name, _sep, domain = (email or "").partition("@")
    return f"{name[:1]}***@{domain}" if domain else "***"


def _telegram_gate(request, form, email):
    """T-8.30i: регистрация из Mini App. None — обычная веб-регистрация; dict
    (uid, lang, hits) — передать Telegram в провижининг; False — отказ (ошибка уже в
    форме). Корзины — те же, что у регистрации в чате бота; ``hits`` — засчитанные в
    этом запросе (вернуть, если бизнес не создан)."""
    import hashlib

    from apps.platform_bot import links, signup, web_signup

    tg = web_signup.from_session(request)
    if tg is None:
        return None
    uid = int(tg["uid"])
    if not web_signup.allowed(uid):
        web_signup.forget(request)
        form.add_error(
            None,
            _("Ein weiteres Geschäft legen Sie auf der Website an: %(url)s")
            % {"url": f"https://{quickstart.domain_base()}/aktion-starten/"},
        )
        return False
    verified = links.active_links(uid).filter(via=links.OwnerTelegramLink.VIA_SIGNUP).exists()
    # T-8.30k: аккаунт Mini App подписан Telegram (HMAC), а веб-путь без Telegram лимита
    # на аккаунт не имеет вовсе — строгая «1 в сутки» тут ничего не защищала. Глобальная
    # корзина по-прежнему зависит от подтверждения.
    global_scope = "tgplat-signup-global" if verified else "tgplat-signup-global-unverified"
    global_limit = signup.LIMIT_GLOBAL if verified else signup.LIMIT_GLOBAL_UNVERIFIED
    mail_key = hashlib.sha256(email.encode()).hexdigest()
    buckets = (
        (
            "tgplat-signup",
            str(uid),
            signup.LIMIT_SIGNUP,
            86400,
            "account",
            _(
                "Mit diesem Telegram-Konto wurden heute schon mehrere Geschäfte angelegt. "
                "Bitte morgen erneut."
            ),
        ),
        (
            "tgplat-signup-mail",
            mail_key,
            signup.LIMIT_MAIL,
            86400,
            "mail",
            _(
                "Für diese E-Mail-Adresse wurden heute schon mehrere Geschäfte angelegt. "
                "Bitte morgen erneut oder eine andere Adresse verwenden."
            ),
        ),
        (
            global_scope,
            "all",
            global_limit,
            3600,
            "global",
            _("Zu viele Versuche. Bitte später erneut."),
        ),
    )
    hits = []
    for scope, ident, limit, window, label, message in buckets:
        if signup._rate(scope, ident, limit, window):
            logger.info("quick-start limited: %s", label)
            _refund(hits)
            form.add_error(None, message)
            return False
        hits.append((scope, ident))
    return {"uid": uid, "lang": tg.get("lang") or "", "hits": hits}


def slug_check(request):
    """Живая проверка адреса для формы: {slug, ok, message}.

    ``?slug=`` — что ввёл человек (нормализуется так же, как на сервере при отправке);
    пусто + ``?name=`` — предложить свободный адрес из названия.
    """
    if ratelimit.hit("quick-slug", ratelimit.client_ip(request), limit=120, window=3600):
        return JsonResponse({"slug": "", "ok": False, "message": ""}, status=429)
    raw = (request.GET.get("slug") or "").strip()
    if not raw:
        name = (request.GET.get("name") or "").strip()
        slug = quickstart.suggest_slug(name) if name else ""
        return JsonResponse({"slug": slug, "ok": bool(slug), "message": ""})
    slug = quickstart.normalize_slug(raw)
    problem = quickstart.slug_problem(slug) if slug else str(_("Bitte eine Adresse eingeben."))
    suggestion = ""
    if problem and slug:
        suggestion = quickstart.suggest_slug(slug)
    return JsonResponse(
        {"slug": slug, "ok": not problem, "message": problem, "suggestion": suggestion}
    )


def _target(request, tenant) -> str | None:
    """Куда перейти, когда всё готово; None — ещё ждём."""
    if tenant.provisioning_status != Tenant.PROVISIONING_READY:
        return None
    done = cache.get(f"quick_promo:{tenant.pk}")
    if done is None:
        # Схема есть, акция ещё создаётся. Ключ мог и потеряться (истёк, рестарт
        # Redis, задача зависла на письме) — тогда не ждать вечно: через несколько
        # минут ведём в список акций, там всё уже видно.
        if timezone.now() - tenant.created_at < READY_GRACE:
            return None
        done = "list"
    entry = (request.session.get(SESSION_KEY) or {}).get(tenant.slug)
    if not entry:
        return login_url_for(tenant)  # другой браузер — обычный вход
    if entry.get("tg"):
        return f"/aktion-starten/{tenant.slug}/?fertig=1"  # T-8.30i: без кабинета до почты
    if done == "list":
        next_url = "/promotions/"
    elif done == "none":
        next_url = "/promotions/schnell/"
    else:
        next_url = f"/promotions/{done}/fertig/"
    return f"{site_url_for(tenant)}/start/{entry['token']}/?{urlencode({'next': next_url})}"


def quick_waiting(request, slug):
    """Ожидание провижининга. Страница опрашивает статус fetch'ем (``?poll=1``) —
    без видимой перезагрузки; meta refresh только как запасной путь без JS.
    Висящее «PENDING» дольше STALE_AFTER — честное сообщение вместо вечного круга."""
    tenant = get_object_or_404(Tenant, slug=slug)
    failed = tenant.provisioning_status == Tenant.PROVISIONING_FAILED
    stale = (
        tenant.provisioning_status == Tenant.PROVISIONING_PENDING
        and timezone.now() - tenant.created_at > STALE_AFTER
    )
    target = None if failed or stale else _target(request, tenant)
    if request.GET.get("poll"):
        return JsonResponse({"redirect": target or "", "stop": failed or stale})
    entry = (request.session.get(SESSION_KEY) or {}).get(tenant.slug) or {}
    tg_done = bool(target and entry.get("tg"))
    if target and not tg_done:
        return redirect(target)
    return render(
        request,
        "tenants/quick_waiting.html",
        {
            "tenant": tenant,
            "failed": failed,
            "stale": stale,
            "preview": entry,
            "tg_done": tg_done,
            "site_url": site_url_for(tenant) if tg_done else "",
        },
    )


# T-8.5e E3: «Vor dem Veröffentlichen prüfen» без входа — только правила (без ИИ и без БД
# каталога). Поля — белым списком: товар не принимается (на публичной схеме каталога нет,
# а ответ стал бы оракулом существования товаров).
TEXT_CHECK_FIELDS = (
    "title",
    "description",
    "new_price",
    "old_price",
    "percent",
    "quantity",
    "term",
    "until",
    "perishable",
)
# Запросов с одного IP за окно; клиент перепроверяет после правок полей, поэтому с запасом.
TEXT_CHECK_LIMIT = 60
TEXT_CHECK_WINDOW = 600


@require_POST
def quick_text_check(request):
    from types import SimpleNamespace

    from django.http import HttpResponse
    from django.template.loader import render_to_string

    from apps.promotions import text_check as ptc

    if ratelimit.hit(
        "quick-text-check",
        ratelimit.client_ip(request),
        limit=TEXT_CHECK_LIMIT,
        window=TEXT_CHECK_WINDOW,
    ):
        return HttpResponse(status=429)
    data = {k: request.POST.get(k, "") for k in TEXT_CHECK_FIELDS}
    btype = request.POST.get("business_type", "")
    tenant = SimpleNamespace(
        business_type=btype if btype in quickstart.QUICK_TYPES else "",
        opening_hours_structured=None,
        opening_hours="",
    )
    try:
        promo = ptc.promotion_from_payload(data, tenant)
        findings = ptc.for_promotion(promo, tenant)
    except Exception:  # noqa: BLE001 — подсказки не стоят 500: клиент оставит прежние
        logger.exception("quick text check failed")
        return HttpResponse(status=503)
    html = render_to_string(
        "promotions/_text_check_results.html",
        {"text_findings": findings, "text_checked": True},
    )
    response = HttpResponse(html)
    response["Cache-Control"] = "no-store"
    return response
