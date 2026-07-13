"""Публичные вьюхи онбординга (живут в public-схеме, см. urls_public)."""

from django.conf import settings
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.http import url_has_allowed_host_and_scheme
from django.views import View

from . import onboarding
from .forms import BusinessSignupForm
from .models import Tenant
from .services import login_url_for, start_business_provisioning


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

    # Языки хрома публичной страницы (нативные подписи) — переключатель 5 языков.
    _LANG_LABELS = {"de": "DE", "en": "EN", "ru": "RU", "tr": "TR", "uk": "UK"}

    def _context(self, form, request=None):
        # AB3/AB5: тип бизнеса — визуальные карточки (иконка + язык задач), как в
        # мастере онбординга (шаг 1), а не сухой dropdown. #3/#5: + demo_url (кнопка
        # «Demo ansehen» на карточке → живая демо-витрина архетипа).
        langs = [
            {"code": c, "label": self._LANG_LABELS.get(c, c.upper())}
            for c in getattr(settings, "CABINET_LANGUAGES", [settings.LANGUAGE_CODE])
        ]
        return {
            "form": form,
            "business_types": onboarding.business_type_cards(request),
            "ui_languages": langs,
        }

    def get(self, request):
        # D3: реф-код партнёра переживает GET→POST через сессию (?ref=<code>).
        ref = (request.GET.get("ref") or "").strip()[:40]
        if ref:
            request.session["partner_ref"] = ref
        return render(request, self.template_name, self._context(BusinessSignupForm(), request))

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
