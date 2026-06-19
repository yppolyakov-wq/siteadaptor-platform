from django.urls import path

from . import views

urlpatterns = [
    path("", views.account_home, name="account-home"),
    path("login/", views.login_view, name="account-login"),
    path("verify/", views.login_verify, name="account-verify"),
    path("logout/", views.logout_view, name="account-logout"),
]
