from django.urls import path

from . import views

app_name = "orders"

urlpatterns = [
    path("", views.order_list, name="order-list"),
    path("settings/", views.order_settings, name="order-settings"),
    path("kitchen/", views.kitchen, name="kitchen"),
    path("kitchen/board/", views.kitchen_board, name="kitchen-board"),
    path("kitchen/<uuid:pk>/action/", views.kitchen_action, name="kitchen-action"),
    path("<uuid:pk>/", views.order_detail, name="order-detail"),
    path("<uuid:pk>/action/", views.order_action, name="order-action"),
    path("<uuid:pk>/lieferschein.pdf", views.delivery_note_pdf, name="order-delivery-note"),
]
