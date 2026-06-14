"""Кабинет событий (A6) — минимальный список (полный CRUD/ростер — A6b)."""

from django.contrib.auth.decorators import login_required
from django.shortcuts import render

from .models import Event


@login_required
def event_list(request):
    events = Event.objects.all().order_by("-starts_at")
    return render(request, "events/event_list.html", {"events": events, "nav": "events"})
