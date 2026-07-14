"""Публичные вьюхи онбординга (живут в public-схеме, см. urls_public)."""

from django.conf import settings
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.http import url_has_allowed_host_and_scheme
from django.views import View

from . import archetype_pages, onboarding
from .forms import BusinessSignupForm
from .models import Tenant
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
        form = BusinessSignupForm(request.POST)
        if not form.is_valid():
            return render(request, self.template_name, self._context(form, request))

        cd = form.cleaned_data
        # Мгновенный ответ: схема строится в фоне (~1 мин), пользователь ждёт
        # на странице с автообновлением — UX-решение владельца 2026-06-12.
        tenant = start_business_provisioning(
            business_name=cd["business_name"],
            slug=cd["slug"],
            business_type=cd["business_type"],
            city=cd["city"],
            email=cd["email"],
            password=cd["password1"],
            # pop: код одноразовый на браузер-сессию — вторая регистрация из
            # того же браузера уже НЕ атрибуцируется автоматически (ревью D3).
            partner_code=request.session.pop("partner_ref", ""),
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
