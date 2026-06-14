from django.urls import path

from . import views

app_name = "support"

urlpatterns = [
    path("", views.help_list, name="help"),
    path("<int:pk>/", views.help_thread, name="thread"),
]
