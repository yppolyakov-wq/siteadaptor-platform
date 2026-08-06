"""CM-6: кабинет «Bewertungen» (/dashboard/reviews/)."""

from django.urls import path

from . import views

app_name = "reviews"

urlpatterns = [
    path("", views.review_list, name="list"),
    path("<uuid:pk>/toggle/", views.review_toggle, name="toggle"),
    path("<uuid:pk>/reply/", views.review_reply, name="reply"),
    # 1а: ответ на портальный отзыв о бизнесе (BusinessReview — int pk, SHARED)
    path("betrieb/<int:pk>/antwort/", views.business_review_reply, name="business-reply"),
]
