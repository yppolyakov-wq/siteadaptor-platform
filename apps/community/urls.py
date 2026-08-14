from django.urls import path

from . import views

app_name = "community"

urlpatterns = [
    # MT-3: пространство заезда в кабинете (настройки + код привязки Telegram).
    path("<uuid:pk>/gruppe/", views.event_space, name="event-space"),
]
