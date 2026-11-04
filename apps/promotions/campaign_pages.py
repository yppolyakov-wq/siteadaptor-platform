"""UX-D D8.2: Kampagnen — «＋ Neue Kampagne» шторкой, авто-рассылки в Einstellungen.

Раньше на экране кампаний одновременно были раскрыты форма новой кампании (11 полей)
и две формы автоматики (Win-back, Geburtstagsgruß) — рабочий список уезжал вниз.
Теперь: список — рабочий экран; создание — шторка (страница без JS); настройки
автоматики — экран «Automatische Mailings» в Einstellungen. Сервисы и поля прежние
(W0): старые POST экрана кампаний продолжают работать."""

from __future__ import annotations

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils.translation import gettext as _

from apps.core import drawer as drawer_mod
from apps.core.owner_login import local_next

from .forms import CouponCampaignForm
from .models import CouponCampaign

WINBACK_SUBJECT = "Wir vermissen Sie – Ihr persönlicher Gutschein"
BIRTHDAY_SUBJECT = "Alles Gute zum Geburtstag – Ihr Geschenk wartet"


def create_campaign(form) -> CouponCampaign:
    """Черновик кампании из валидной CouponCampaignForm (одна точка для шторки и
    старой формы экрана кампаний)."""
    d = form.cleaned_data
    return CouponCampaign.objects.create(
        name=d["name"],
        tag=(d.get("tag") or "").strip().lower(),
        inactive_days=d.get("inactive_days"),
        top_ltv=d.get("top_ltv"),
        discount_percent=d.get("discount_percent"),
        discount_cents=int(d["discount_eur"] * 100) if d.get("discount_eur") else None,
        min_order_cents=int(d["min_order_eur"] * 100) if d.get("min_order_eur") else 0,
        valid_days=d["valid_days"],
        subject=d["subject"],
        body=(d.get("body") or "").strip(),
    )


def _int_in(raw, default, lo, hi):
    """Целое в [lo, hi]; пусто → default; мусор → ValueError (форма покажет ошибку)."""
    value = int(raw) if str(raw or "").strip() else default
    return max(lo, min(hi, value))


def _singleton(kind, name, subject):
    obj = CouponCampaign.objects.filter(kind=kind).first()
    if obj is None:
        obj = CouponCampaign.objects.create(
            kind=kind, name=name, subject=subject, status=CouponCampaign.STATUS_PAUSED
        )
    return obj


def save_winback(request) -> bool:
    """B4.4: настройки авто-win-back на кампании-синглтоне kind=auto_winback."""
    obj = _singleton(CouponCampaign.KIND_AUTO_WINBACK, "Auto Win-back", WINBACK_SUBJECT)
    try:
        obj.inactive_days = _int_in(request.POST.get("inactive_days"), 60, 1, 3650)
        obj.discount_percent = _int_in(request.POST.get("discount_percent"), 10, 1, 100)
        obj.valid_days = _int_in(request.POST.get("valid_days"), 30, 1, 365)
    except (TypeError, ValueError):
        messages.error(request, _("Bitte gültige Zahlen eingeben."))
        return False
    obj.subject = (request.POST.get("subject") or "").strip()[:200] or obj.subject
    obj.status = (
        CouponCampaign.STATUS_ACTIVE
        if request.POST.get("enabled")
        else CouponCampaign.STATUS_PAUSED
    )
    obj.save(
        update_fields=[
            "inactive_days",
            "discount_percent",
            "valid_days",
            "subject",
            "status",
            "updated_at",
        ]
    )
    messages.success(request, _("Auto Win-back gespeichert."))
    return True


def save_birthday(request) -> bool:
    """PMS-B2: настройки «Geburtstagsgruß» на кампании-синглтоне kind=birthday."""
    obj = _singleton(CouponCampaign.KIND_BIRTHDAY, "Geburtstagsgruß", BIRTHDAY_SUBJECT)
    try:
        obj.discount_percent = _int_in(request.POST.get("discount_percent"), 10, 1, 100)
        obj.valid_days = _int_in(request.POST.get("valid_days"), 30, 1, 365)
    except (TypeError, ValueError):
        messages.error(request, _("Bitte gültige Zahlen eingeben."))
        return False
    obj.subject = (request.POST.get("subject") or "").strip()[:200] or obj.subject
    obj.status = (
        CouponCampaign.STATUS_ACTIVE
        if request.POST.get("enabled")
        else CouponCampaign.STATUS_PAUSED
    )
    obj.save(update_fields=["discount_percent", "valid_days", "subject", "status", "updated_at"])
    messages.success(request, _("Geburtstagsgruß gespeichert."))
    return True


@login_required
@drawer_mod.drawer_aware
def campaign_new(request):
    """«＋ Neue Kampagne» шторкой (B4.3: ?tag= из CRM предзаполняет сегмент)."""
    form = CouponCampaignForm(
        request.POST or None, initial={"tag": (request.GET.get("tag") or "").strip()[:50]}
    )
    if request.method == "POST":
        if form.is_valid():
            create_campaign(form)
            messages.success(request, _("Kampagne gespeichert."))
            # Черновик ждёт отправки в списке кампаний: открыли шторку с другой страницы
            # (CRM) — шторка ведёт туда (`navigate`), из списка — закрывается с тостом.
            return redirect("promotions:coupon-campaigns")
        if drawer_mod.is_drawer(request):
            messages.error(request, _("Bitte prüfen Sie Ihre Angaben und senden Sie erneut."))
    ctx = {
        "form": form,
        "nav": "campaigns",
        "next_url": drawer_mod.drawer_next(request, reverse("promotions:coupon-campaigns")),
    }
    if request.method == "POST":
        ctx["next_url"] = local_next(request) or ctx["next_url"]
    if drawer_mod.is_drawer(request) or request.GET.get("box") == "1":
        return drawer_mod.fragment(render(request, "promotions/_campaign_new_drawer.html", ctx))
    return render(request, "promotions/campaign_new.html", ctx)


@login_required
def campaign_automation(request):
    """Einstellungen › «Automatische Mailings»: Win-back и Geburtstagsgruß."""
    from .newsletter import consented_customers

    if request.method == "POST":
        action = request.POST.get("action")
        if action == "winback":
            save_winback(request)
        elif action == "birthday":
            save_birthday(request)
        return redirect("promotions:campaign-automation")
    return render(
        request,
        "promotions/campaign_automation.html",
        {
            "nav": "campaign-automation",
            "winback": CouponCampaign.objects.filter(kind=CouponCampaign.KIND_AUTO_WINBACK).first(),
            "birthday": CouponCampaign.objects.filter(kind=CouponCampaign.KIND_BIRTHDAY).first(),
            "birthday_known": consented_customers().exclude(birthday=None).count(),
            "winback_subject": WINBACK_SUBJECT,
            "birthday_subject": BIRTHDAY_SUBJECT,
        },
    )
