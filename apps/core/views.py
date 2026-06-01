"""Общие tenant-facing вьюхи (живут в схеме арендатора)."""

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render

from apps.tenants.forms import BusinessSettingsForm


@login_required
def dashboard(request):
    """Главная кабинета владельца."""
    return render(request, "tenant/dashboard.html", {"nav": "dashboard"})


@login_required
def settings_view(request):
    """Настройки бизнеса: контакты и правовые тексты для витрины."""
    form = BusinessSettingsForm(request.POST or None, instance=request.tenant)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Gespeichert.")
        return redirect("settings")
    return render(request, "tenant/settings.html", {"form": form, "nav": "settings"})
