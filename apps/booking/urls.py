from django.urls import path

from . import views

app_name = "booking"

urlpatterns = [
    path("", views.calendar, name="calendar"),
    path("new/", views.booking_create, name="booking-create"),
    path("<uuid:pk>/action/", views.booking_action, name="booking-action"),
    path("ressourcen/", views.resources, name="resources"),
    path("leistungen/", views.services_view, name="services"),
]
