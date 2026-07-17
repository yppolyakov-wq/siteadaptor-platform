"""Публичные вьюхи онбординга (живут в public-схеме, см. urls_public)."""

from django.conf import settings
from django.db import transaction
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone, translation
from django.utils.http import url_has_allowed_host_and_scheme
from django.utils.translation import gettext as _
from django.views import View

from apps.core import ratelimit

from . import archetype_pages, onboarding, signup
from .forms import BusinessSignupForm
from .models import SignupRequest, Tenant
from .services import login_url_for, start_business_provisioning

# Языки хрома публичных страниц (нативные подписи) — переключатель 5 языков.
_LANG_LABELS = {"de": "DE", "en": "EN", "ru": "RU", "tr": "TR", "uk": "UK"}


def ui_languages():
    return [
        {"code": c, "label": _LANG_LABELS.get(c, c.upper())}
        for c in getattr(settings, "CABINET_LANGUAGES", [settings.LANGUAGE_CODE])
    ]


def _capture_partner_ref(request):
    """D3: реф-код партнёра из ?ref= — в сессию (переживает переходы до POST
    регистрации). Исторические партнёрские ссылки ведут на КОРЕНЬ — поэтому
    захват и на лендинге, и на /registrieren/."""
    ref = (request.GET.get("ref") or "").strip()[:40]
    if ref:
        request.session["partner_ref"] = ref


def set_public_language(request):
    """Переключатель языка публичной страницы (регистрация бизнеса и пр.).

    Валидируем `?lang=` против CABINET_LANGUAGES (языки хрома платформы: de/en/tr/
    ru/uk); неизвестный → LANGUAGE_CODE. Кладём cookie, LocaleMiddleware подхватит
    на следующем запросе. `next` — только относительный (open-redirect guard)."""
    allowed = getattr(settings, "CABINET_LANGUAGES", [settings.LANGUAGE_CODE])
    lang = request.GET.get("lang", "")
    if lang not in allowed:
        lang = settings.LANGUAGE_CODE
    nxt = request.GET.get("next") or "/"
    if not url_has_allowed_host_and_scheme(nxt, allowed_hosts=None):
        nxt = "/"
    resp = redirect(nxt)
    resp.set_cookie(settings.LANGUAGE_COOKIE_NAME, lang, max_age=60 * 60 * 24 * 365)
    return resp


class BusinessSignupView(View):
    template_name = "tenants/onboarding.html"

    def _context(self, form, request=None, preselected_type=""):
        # AB3/AB5: тип бизнеса — визуальные карточки (иконка + язык задач), как в
        # мастере онбординга (шаг 1), а не сухой dropdown. #3/#5: + demo_url (кнопка
        # «Demo ansehen» на карточке → живая демо-витрина архетипа).
        # preselected_type: пришли с Branchen-страницы (?type=) с УЖЕ выбранной отраслью
        # → шаблон показывает компактный баннер выбранной отрасли + форму, а не весь
        # пикер (фидбэк владельца: «должна просто открываться форма регистрации»).
        return {
            "form": form,
            "business_types": onboarding.business_type_cards(request),
            "ui_languages": ui_languages(),
            "preselected_type": preselected_type,
            # AB5.1: заметка «сначала письмо-подтверждение» под кнопкой.
            "email_confirmation": signup.confirmation_enabled(),
        }

    def get(self, request):
        _capture_partner_ref(request)
        # Предвыбор типа бизнеса из ?type= (переход с Branchen-страницы «Jetzt starten»).
        pretype = (request.GET.get("type") or "").strip()
        preselected = pretype if pretype in dict(Tenant.BUSINESS_TYPES) else ""
        form = (
            BusinessSignupForm(initial={"business_type": preselected})
            if preselected
            else BusinessSignupForm()
        )
        return render(request, self.template_name, self._context(form, request, preselected))

    def post(self, request):
        # AB5.1: honeypot — людям поле не видно, бот его заполняет → фейковый
        # успех без записи и письма (паттерн newsletter_signup).
        if (request.POST.get("website") or "").strip():
            return render(
                request,
                "tenants/signup_confirm_sent.html",
                {
                    "email": (request.POST.get("email") or "").strip(),
                    "ui_languages": ui_languages(),
                },
            )
        form = BusinessSignupForm(request.POST)
        if not form.is_valid():
            return render(request, self.template_name, self._context(form, request))

        cd = form.cleaned_data
        # pop: код одноразовый на браузер-сессию — вторая регистрация из
        # того же браузера уже НЕ атрибуцируется автоматически (ревью D3).
        partner_code = request.session.pop("partner_ref", "")

        if signup.confirmation_enabled():
            # AB5.1: double-opt-in — тенант появится только после клика по ссылке
            # из письма (план signup-confirm-wizard-plan-2026-07-17 §1).
            if ratelimit.hit("signup", ratelimit.client_ip(request), limit=5, window=3600):
                form.add_error(None, _("Zu viele Versuche — bitte später erneut."))
                return render(request, self.template_name, self._context(form, request))
            req = signup.create_request(
                cleaned_data=cd,
                partner_code=partner_code,
                locale=translation.get_language() or "de",
            )
            signup.send_confirmation_email(request, req)
            return render(
                request,
                "tenants/signup_confirm_sent.html",
                {
                    "email": req.email,
                    "token": req.token,
                    "direct_url": signup.confirm_url(request, req)
                    if signup.show_direct_link()
                    else "",
                    "ui_languages": ui_languages(),
                },
            )

        # Флаг выключен (страховка, пока почта не настроена): прежний прямой флоу —
        # мгновенный ответ, схема строится в фоне (~1 мин), пользователь ждёт
        # на странице с автообновлением (UX-решение владельца 2026-06-12).
        tenant = start_business_provisioning(
            business_name=cd["business_name"],
            slug=cd["slug"],
            business_type=cd["business_type"],
            city=cd["city"],
            email=cd["email"],
            password=cd["password1"],
            partner_code=partner_code,
        )
        return redirect("signup-waiting", slug=tenant.slug)


def industries_index(request):
    """Главная платформы (/ и /branchen/): обзор Branchen-Landingpages.

    Корень исторически принимал партнёрский `?ref=` (ссылки в проде) — захват
    сохранён и здесь."""
    _capture_partner_ref(request)
    return render(
        request,
        "tenants/industries.html",
        {"cards": archetype_pages.index_cards(request), "ui_languages": ui_languages()},
    )


def industry_page(request, slug):
    """Branchen-Feature-Seite (/branchen/<slug>/): was die Plattform für DIESE
    Branche kann. Unbekannter/neutraler Typ → 404."""
    if not archetype_pages.is_valid(slug):
        raise Http404("Unbekannte Branche")
    return render(request, "tenants/industry.html", archetype_pages.page_context(request, slug))


def about_page(request):
    """«Über uns» — о платформе (/ueber-uns/)."""
    return render(request, "tenants/about.html", {"ui_languages": ui_languages()})


_LEGAL_TEMPLATES = {
    "impressum": "tenants/legal_impressum.html",
    "datenschutz": "tenants/legal_datenschutz.html",
    "agb": "tenants/legal_agb.html",
}


def platform_legal(request, kind):
    """Правовые страницы ПЛАТФОРМЫ (siteadaptor.de): Impressum/Datenschutz/AGB.

    Не путать с правовыми страницами тенантов (их витрины, tenant-urlconf).
    Тексты — немецкие заготовки; реквизиты заполняет владелец (плейсхолдеры
    помечены в шаблонах)."""
    tpl = _LEGAL_TEMPLATES.get(kind)
    if not tpl:
        raise Http404
    return render(request, tpl, {"ui_languages": ui_languages()})


def _signup_error(request, reason, status, signup_req=None):
    return render(
        request,
        "tenants/signup_confirm_error.html",
        {"reason": reason, "signup": signup_req, "ui_languages": ui_languages()},
        status=status,
    )


def signup_confirm(request, token):
    """AB5.1: клик по ссылке из письма — единственная точка, где создаётся бизнес.

    Идемпотентно (повторный клик → waiting-страница его тенанта); гонка
    двойного клика закрыта select_for_update на заявке."""
    with transaction.atomic():
        signup_req = SignupRequest.objects.select_for_update().filter(token=token).first()
        if signup_req is None:
            return _signup_error(request, "invalid", 404)
        if signup_req.is_confirmed:
            if signup_req.tenant_id:
                return redirect("signup-waiting", slug=signup_req.tenant.slug)
            return _signup_error(request, "invalid", 410)
        if signup_req.is_expired:
            return _signup_error(request, "expired", 410, signup_req)
        # Заявка slug не резервирует — между POST и кликом его могли занять.
        if signup.slug_taken(signup_req.slug):
            return _signup_error(request, "slug_taken", 409, signup_req)
        tenant = start_business_provisioning(
            business_name=signup_req.business_name,
            slug=signup_req.slug,
            business_type=signup_req.business_type,
            city=signup_req.city,
            email=signup_req.email,
            password_hash=signup_req.password_hash,
            partner_code=signup_req.partner_code,
        )
        signup_req.confirmed_at = timezone.now()
        signup_req.tenant = tenant
        signup_req.save(update_fields=["confirmed_at", "tenant"])
    return redirect("signup-waiting", slug=tenant.slug)


def signup_resend(request):
    """AB5.1: переотправка письма подтверждения (кнопка на «проверьте почту»)."""
    if request.method != "POST":
        return redirect("business-signup")
    token = (request.POST.get("token") or "")[:64]
    signup_req = SignupRequest.objects.filter(token=token, confirmed_at__isnull=True).first()
    if signup_req is None or signup_req.is_expired:
        return redirect("business-signup")
    ctx = {
        "email": signup_req.email,
        "token": signup_req.token,
        "direct_url": signup.confirm_url(request, signup_req) if signup.show_direct_link() else "",
        "ui_languages": ui_languages(),
    }
    if ratelimit.hit("signup-resend", token, limit=3, window=600):
        ctx["resend_error"] = _("Zu viele Versuche — bitte später erneut.")
    else:
        signup.send_confirmation_email(request, signup_req)
        ctx["resent"] = True
    return render(request, "tenants/signup_confirm_sent.html", ctx)


def signup_waiting(request, slug):
    """Страница «Ihre Website wird eingerichtet…»: meta-refresh каждые 4 сек,
    по готовности — редирект на логин субдомена; письмо со ссылкой уходит
    параллельно (tasks._send_ready_email)."""
    tenant = get_object_or_404(Tenant, slug=slug)
    if tenant.provisioning_status == Tenant.PROVISIONING_READY:
        return redirect(login_url_for(tenant))
    return render(
        request,
        "tenants/provisioning.html",
        {
            "tenant": tenant,
            "failed": tenant.provisioning_status == Tenant.PROVISIONING_FAILED,
        },
        status=200,
    )
