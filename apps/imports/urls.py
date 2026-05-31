from django.urls import path

from . import views

app_name = "imports"

urlpatterns = [
    path("start/", views.import_start, name="start"),
    path("<uuid:pk>/map/", views.import_map, name="map"),
    path("<uuid:pk>/preview/", views.import_preview, name="preview"),
    path("<uuid:pk>/status/", views.import_status, name="status"),
]
