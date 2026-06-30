from django.urls import path

from . import views

app_name = "stays"

urlpatterns = [
    path("", views.calendar, name="calendar"),
    # H1.2: инлайн-правка названия/описания номера на детальной витрине (?preview=1).
    path("inline-edit/", views.stay_inline_edit, name="stay-inline-edit"),
    path("photo-edit/", views.stay_photo_edit, name="stay-photo-edit"),
    path("new/", views.stay_create, name="stay-create"),
    path("<uuid:pk>/action/", views.stay_action, name="stay-action"),
    path("units/", views.units, name="units"),
    path("channels/", views.channels, name="channels"),
    path("checkins/", views.checkins, name="checkins"),
    path("reports/", views.reports, name="reports"),
]
