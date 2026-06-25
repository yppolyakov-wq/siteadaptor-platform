from django.urls import path

from . import views

app_name = "inbox"

urlpatterns = [
    path("", views.inbox_list, name="list"),
    path("unread-count/", views.unread_count, name="unread-count"),
    path("<uuid:pk>/", views.thread, name="thread"),
    path("<uuid:pk>/poll/", views.thread_poll, name="thread-poll"),
    path("<uuid:pk>/typing/", views.thread_typing, name="thread-typing"),
]
