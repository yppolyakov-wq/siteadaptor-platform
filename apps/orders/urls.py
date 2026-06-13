from django.urls import path

from . import views

app_name = "orders"

urlpatterns = [
    path("", views.order_list, name="order-list"),
    path("settings/", views.order_settings, name="order-settings"),
    path("<uuid:pk>/", views.order_detail, name="order-detail"),
    path("<uuid:pk>/action/", views.order_action, name="order-action"),
]
