from django.urls import path

from . import views

app_name = "stays"

urlpatterns = [
    path("", views.calendar, name="calendar"),
    path("new/", views.stay_create, name="stay-create"),
    path("<uuid:pk>/action/", views.stay_action, name="stay-action"),
    path("units/", views.units, name="units"),
    path("checkins/", views.checkins, name="checkins"),
    path("reports/", views.reports, name="reports"),
]
