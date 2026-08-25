from django.urls import path

from . import views

app_name = "inbox"

urlpatterns = [
    path("", views.inbox_list, name="list"),
    path("unread-count/", views.unread_count, name="unread-count"),
    path("<uuid:pk>/", views.thread, name="thread"),
    path("<uuid:pk>/poll/", views.thread_poll, name="thread-poll"),
    path("<uuid:pk>/typing/", views.thread_typing, name="thread-typing"),
    # LS-3: композер персонального предложения из треда.
    path("<uuid:pk>/angebot/", views.offer_compose, name="offer-compose"),
    # C1: написать клиенту с карточки сделки (owner-first тред). Живёт ПОД
    # /dashboard/inbox/ → гейт модуля даёт ModuleGatingMiddleware бесплатно.
    path("deal/<str:kind>/<uuid:pk>/", views.deal_thread, name="deal-thread"),
]
