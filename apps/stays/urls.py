from django.urls import path

from . import views

app_name = "stays"

urlpatterns = [
    path("", views.calendar, name="calendar"),
    # H1.2: инлайн-правка названия/описания номера на детальной витрине (?preview=1).
    path("inline-edit/", views.stay_inline_edit, name="stay-inline-edit"),
    path("photo-edit/", views.stay_photo_edit, name="stay-photo-edit"),
    path("new/", views.stay_create, name="stay-create"),
    # PMS-A2: стойка «Heute» — заезды/выезды/в доме.
    path("heute/", views.today_view, name="today"),
    # PMS-C: CSV броней месяца (те же выборки, что отчёт).
    path("berichte/export.csv", views.reports_export_csv, name="reports-export"),
    path("<uuid:pk>/action/", views.stay_action, name="stay-action"),
    # FB-11: карточка брони (кто/когда/сумма/оплата/Meldeschein + действия)
    path("buchung/<uuid:pk>/", views.booking_detail, name="booking-detail"),
    # Батч C: hard-delete ручной брони без денег (гейт во вьюхе; GoBD-safe).
    path("buchung/<uuid:pk>/loeschen/", views.booking_delete, name="booking-delete"),
    path("zimmer/<uuid:pk>/sauber/", views.room_clean, name="room-clean"),
    path("units/", views.units, name="units"),
    # Фидбэк 2026-07-28: каждый номер редактируется на СВОЕЙ странице.
    path("units/<uuid:pk>/", views.units, name="unit-edit"),
    # D2.4: self-serve продвижение юнита в агрегаторе.
    path("units/<uuid:pk>/feature/", views.unit_feature, name="unit-feature"),
    path(
        "units/<uuid:pk>/feature/checkout/",
        views.unit_feature_checkout,
        name="unit-feature-checkout",
    ),
    path("channels/", views.channels, name="channels"),
    path("checkins/", views.checkins, name="checkins"),
    path("reports/", views.reports, name="reports"),
]
