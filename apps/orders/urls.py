from django.urls import path

from . import views

app_name = "orders"

urlpatterns = [
    path("", views.order_list, name="order-list"),
    # R7-3: доставка — своя рабочая страница (накладные/трек-номера)
    path("lieferungen/", views.deliveries, name="deliveries"),
    path("kitchen/", views.kitchen, name="kitchen"),
    path("tisch-qr/", views.table_qr, name="table-qr"),
    path("kitchen/board/", views.kitchen_board, name="kitchen-board"),
    path("kitchen/<uuid:pk>/action/", views.kitchen_action, name="kitchen-action"),
    path("<uuid:pk>/", views.order_detail, name="order-detail"),
    path("<uuid:pk>/action/", views.order_action, name="order-action"),
    # SH группа B: правка состава/скидки/доставки/клиента с карточки заказа.
    path("<uuid:pk>/bearbeiten/", views.order_edit, name="order-edit"),
    path("<uuid:pk>/lieferschein.pdf", views.delivery_note_pdf, name="order-delivery-note"),
]
