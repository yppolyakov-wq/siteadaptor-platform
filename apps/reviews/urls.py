"""CM-6: кабинет «Bewertungen» (/dashboard/reviews/)."""

from django.urls import path

from . import views

app_name = "reviews"

urlpatterns = [
    path("", views.review_list, name="list"),
    path("<uuid:pk>/toggle/", views.review_toggle, name="toggle"),
]
