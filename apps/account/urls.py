from django.urls import path

from apps.documents import views as document_views

from . import views

urlpatterns = [
    path("", views.account_home, name="account-home"),
    path("login/", views.login_view, name="account-login"),
    path("verify/", views.login_verify, name="account-verify"),
    path("logout/", views.logout_view, name="account-logout"),
    path("profil/", views.profile_view, name="account-profile"),
    path("export/", views.export_data, name="account-export"),
    path("loeschen/", views.delete_account, name="account-delete"),
    path("termin/<str:code>/stornieren/", views.cancel_booking, name="account-cancel-booking"),
    # MT-2: досье участника — список/загрузка и ПРИВАТНАЯ выдача файла.
    path("dokumente/", document_views.documents_home, name="account-documents"),
    path(
        "dokumente/<uuid:pk>/",
        document_views.document_download,
        name="account-document-download",
    ),
    path(
        "dokumente/<uuid:pk>/loeschen/",
        document_views.document_delete,
        name="account-document-delete",
    ),
]
