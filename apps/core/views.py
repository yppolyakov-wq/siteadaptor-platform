"""Общие tenant-facing вьюхи (живут в схеме арендатора)."""

from django.contrib.auth.decorators import login_required
from django.shortcuts import render


@login_required
def dashboard(request):
    """Плейсхолдер кабинета владельца. Каталог/акции — следующие спринты."""
    return render(request, "tenant/dashboard.html")
