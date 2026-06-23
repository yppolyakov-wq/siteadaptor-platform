from django.urls import path

from . import views

app_name = "promotions"

urlpatterns = [
    path("", views.promotion_list, name="promotion-list"),
    path("new/", views.promotion_create, name="promotion-create"),
    path("<uuid:pk>/edit/", views.promotion_edit, name="promotion-edit"),
    path("<uuid:pk>/transition/", views.promotion_transition, name="promotion-transition"),
    # Платное продвижение акции в агрегаторе (P2.4b): страница + Stripe-Checkout.
    path("<uuid:pk>/feature/", views.promotion_feature, name="promotion-feature"),
    path(
        "<uuid:pk>/feature/checkout/",
        views.promotion_feature_checkout,
        name="promotion-feature-checkout",
    ),
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
    path("redeem/", views.redeem_home, name="redeem"),
    path("redeem/<str:code>/", views.redeem_detail, name="redeem-detail"),
    path("redeem/<str:code>/action/", views.redeem_action, name="redeem-action"),
    path("vouchers/", views.voucher_list, name="voucher-list"),
    path("vouchers/redeem/", views.voucher_redeem, name="voucher-redeem"),
    path("loyalty/", views.loyalty_list, name="loyalty-list"),
    path("loyalty/<uuid:program_id>/stamp/", views.loyalty_stamp, name="loyalty-stamp"),
    path("newsletter/", views.newsletter_campaigns, name="newsletter"),
    path("analytics/", views.analytics_overview, name="analytics"),
    path("poster/", views.shop_poster_pdf, name="shop-poster"),
]
