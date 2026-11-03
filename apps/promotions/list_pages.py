"""UX-D D6.4: Gutscheine & Treue — создание шторкой, страница программы лояльности.

Раньше над списками ваучеров и программ всегда висели раскрытые формы создания, суммы
ваучеров показывались в центах («−500 ct»), а программу лояльности после создания нельзя
было поправить (только перевести название). Контракт шторки — `docs/references/patterns/
drawer.md`; старые POST на страницах списков продолжают работать (старые вкладки)."""

from __future__ import annotations

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.translation import gettext as _

from apps.core import drawer as drawer_mod
from apps.core.owner_login import local_next
from apps.loyalty.models import LoyaltyProgram

from . import services
from .forms import LoyaltyProgramForm, VoucherCreateForm


def _render(request, form, *, drawer_tpl, page_tpl, nav, back):
    ctx = {
        "form": form,
        "nav": nav,
        "next_url": drawer_mod.drawer_next(request, reverse(back)),
    }
    if request.method == "POST":
        ctx["next_url"] = local_next(request) or ctx["next_url"]
    if drawer_mod.is_drawer(request) or request.GET.get("box") == "1":
        return drawer_mod.fragment(render(request, drawer_tpl, ctx))
    return render(request, page_tpl, ctx)


def create_vouchers(form):
    """Пачка кодов из валидной VoucherCreateForm (одна точка для шторки и старой формы)."""
    d_eur = form.cleaned_data.get("discount_eur")
    min_eur = form.cleaned_data.get("min_order_eur")
    return services.generate_vouchers(
        label=form.cleaned_data["label"],
        count=form.cleaned_data["count"],
        max_uses=form.cleaned_data["max_uses"],
        expires_at=form.cleaned_data.get("expires_at"),
        discount_percent=form.cleaned_data.get("discount_percent"),
        discount_cents=int(d_eur * 100) if d_eur else None,
        min_order_cents=int(min_eur * 100) if min_eur else 0,
        combinable=form.cleaned_data.get("combinable", False),
    )


@login_required
@drawer_mod.drawer_aware
def voucher_new(request):
    """«＋ Gutscheine erzeugen» — пачка кодов шторкой (та же форма и тот же сервис)."""
    form = VoucherCreateForm(request.POST or None)
    if request.method == "POST":
        if form.is_valid():
            created = create_vouchers(form)
            messages.success(request, _("%(count)d Voucher erstellt.") % {"count": len(created)})
            return redirect(local_next(request) or reverse("promotions:voucher-list"))
        if drawer_mod.is_drawer(request):
            messages.error(request, _("Bitte prüfen Sie Ihre Angaben und senden Sie erneut."))
    return _render(
        request,
        form,
        drawer_tpl="promotions/_voucher_new_drawer.html",
        page_tpl="promotions/voucher_new.html",
        nav="vouchers",
        back="promotions:voucher-list",
    )


@login_required
@drawer_mod.drawer_aware
def loyalty_new(request):
    """«＋ Neues Programm» шторкой; после создания — страница программы."""
    form = LoyaltyProgramForm(request.POST or None)
    if request.method == "POST":
        form.init_overlay_i18n(getattr(request, "tenant", None))
        if form.is_valid():
            program = form.save()
            messages.success(request, _("Programm erstellt."))
            return redirect("promotions:loyalty-edit", pk=program.pk)
        if drawer_mod.is_drawer(request):
            messages.error(request, _("Bitte prüfen Sie Ihre Angaben und senden Sie erneut."))
    else:
        form.init_overlay_i18n(getattr(request, "tenant", None))
    return _render(
        request,
        form,
        drawer_tpl="promotions/_loyalty_new_drawer.html",
        page_tpl="promotions/loyalty_new.html",
        nav="loyalty",
        back="promotions:loyalty-list",
    )


@login_required
def loyalty_edit(request, pk):
    """Страница программы: правка названия/штампов/награды/активности + переводы.

    Новый порог штампов действует со следующего штампа: накопленное у клиентов не
    сгорает и награда задним числом не выдаётся (`services.add_stamp`)."""
    program = get_object_or_404(LoyaltyProgram, pk=pk)
    if request.method == "POST" and request.POST.get("program") != str(program.pk):
        raise Http404  # страница правит только СВОЮ программу
    form = LoyaltyProgramForm(request.POST or None, instance=program)
    form.init_overlay_i18n(getattr(request, "tenant", None))
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, _("Saved."))
        return redirect("promotions:loyalty-edit", pk=program.pk)
    return render(
        request,
        "promotions/loyalty_page.html",
        {
            "nav": "loyalty",
            "program": program,
            "form": form,
            "cards": program.cards.count(),
        },
    )
