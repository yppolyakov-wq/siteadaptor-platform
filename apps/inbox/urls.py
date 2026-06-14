from django.urls import path

from . import views

app_name = "inbox"

urlpatterns = [
    path("", views.inbox_list, name="list"),
    path("<uuid:pk>/", views.thread, name="thread"),
]
