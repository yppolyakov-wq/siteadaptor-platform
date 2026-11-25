from django.contrib.auth.decorators import login_required
from django.urls import path
from django.views.generic import RedirectView

from . import views

app_name = "imports"

urlpatterns = [
    # FB-33 стопка 15 K0: корень префикса → «Import starten» (решение владельца §14.3).
    path(
        "",
        login_required(RedirectView.as_view(pattern_name="imports:start")),
        name="index",
    ),
    path("start/", views.import_start, name="start"),
    path("<uuid:pk>/map/", views.import_map, name="map"),
    path("<uuid:pk>/preview/", views.import_preview, name="preview"),
    path("<uuid:pk>/status/", views.import_status, name="status"),
    # T-8.27: импорт с сайта клиента (owner-only — CabinetOwnerAccessMiddleware).
    path("website/", views.website_start, name="website"),
    path("website/<uuid:pk>/", views.website_run, name="website-run"),
]
