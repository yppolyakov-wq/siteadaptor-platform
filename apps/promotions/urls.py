from django.urls import path

from . import views

app_name = "promotions"

urlpatterns = [
    path("", views.promotion_list, name="promotion-list"),
    path("new/", views.promotion_create, name="promotion-create"),
    path("<uuid:pk>/edit/", views.promotion_edit, name="promotion-edit"),
    path("<uuid:pk>/transition/", views.promotion_transition, name="promotion-transition"),
    path(
        "<uuid:pk>/images/<str:image_id>/delete/",
        views.promotion_image_delete,
        name="promotion-image-delete",
    ),
    path(
        "<uuid:pk>/images/<str:image_id>/primary/",
        views.promotion_image_primary,
        name="promotion-image-primary",
    ),
    path("reservations/", views.reservation_list, name="reservation-list"),
    path("reservations/<uuid:pk>/action/", views.reservation_action, name="reservation-action"),
]
