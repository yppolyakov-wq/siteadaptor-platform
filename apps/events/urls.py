from django.urls import path

from . import views

app_name = "events"

urlpatterns = [
    path("", views.event_list, name="list"),
    path("teachers/", views.teacher_list, name="teacher-list"),
    path("teachers/new/", views.teacher_create, name="teacher-create"),
    path("teachers/<uuid:pk>/edit/", views.teacher_edit, name="teacher-edit"),
    path("teachers/<uuid:pk>/delete/", views.teacher_delete, name="teacher-delete"),
    path("new/", views.event_create, name="create"),
    path("<uuid:pk>/", views.event_detail, name="detail"),
    path("<uuid:pk>/edit/", views.event_edit, name="edit"),
    path("<uuid:pk>/action/", views.event_action, name="action"),
    path("<uuid:pk>/tickets/add/", views.ticket_add, name="ticket-add"),
    path("<uuid:pk>/tickets/<uuid:tid>/action/", views.ticket_action, name="ticket-action"),
    path("<uuid:pk>/roster.csv", views.roster_csv, name="roster-csv"),
    path("<uuid:pk>/waitlist/notify/", views.waitlist_notify, name="waitlist-notify"),
]
