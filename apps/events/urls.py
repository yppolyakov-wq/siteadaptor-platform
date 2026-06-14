from django.urls import path

from . import views

app_name = "events"

urlpatterns = [
    path("", views.event_list, name="list"),
    path("new/", views.event_create, name="create"),
    path("<uuid:pk>/", views.event_detail, name="detail"),
    path("<uuid:pk>/edit/", views.event_edit, name="edit"),
    path("<uuid:pk>/action/", views.event_action, name="action"),
    path("<uuid:pk>/tickets/add/", views.ticket_add, name="ticket-add"),
    path("<uuid:pk>/tickets/<uuid:tid>/action/", views.ticket_action, name="ticket-action"),
    path("<uuid:pk>/roster.csv", views.roster_csv, name="roster-csv"),
]
