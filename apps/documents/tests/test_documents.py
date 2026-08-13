"""MT-2: досье участника — шифрование, приватная выдача, ретеншн.

Три инварианта, ради которых модуль и появился:
* в хранилище лежит НЕ исходный файл (иначе бакет = утечка паспортов);
* прямой ссылки не существует — отдаёт только вьюха с проверкой доступа;
* документ живёт конечное время и удаляется вместе с blob.
"""

import uuid

import pytest
from django.contrib.auth import get_user_model
from django.contrib.messages.middleware import MessageMiddleware
from django.contrib.sessions.middleware import SessionMiddleware
from django.core.exceptions import ValidationError
from django.core.files.storage import default_storage
from django.core.files.uploadedfile import SimpleUploadedFile
from django.http import Http404
from django.test import RequestFactory
from django.utils import timezone

from apps.account.auth import SESSION_KEY
from apps.documents import services, storage, views
from apps.documents.models import SecureDocument
from apps.promotions.models import Customer
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db

PNG = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06"
    b"\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\nIDATx\x9cc\x00\x01\x00\x00\x05\x00"
    b"\x01\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82"
)
PDF = b"%PDF-1.4\n1 0 obj\n<<>>\nendobj\ntrailer\n<<>>\n%%EOF\n"


def _tenant():
    return TenantFactory.build(name="Himalaya Riders", enabled_modules=["events"])


def _customer(email="rider@example.de"):
    return Customer.objects.create(name="Rider", email=email)


def _upload(data=PNG, name="pass.png"):
    return SimpleUploadedFile(name, data, content_type="application/octet-stream")


def _request(method="get", data=None, customer=None, user=None, path="/konto/dokumente/"):
    request = getattr(RequestFactory(), method)(path, data or {})
    SessionMiddleware(lambda r: None).process_request(request)
    MessageMiddleware(lambda r: None).process_request(request)
    request.tenant = TenantFactory.build(
        name="Himalaya Riders", enabled_modules=["events", "customer_account"]
    )
    if customer is not None:
        request.session[SESSION_KEY] = str(customer.pk)
    if user is not None:
        request.user = user
    return request


def _store(customer, **kwargs):
    return services.store(
        _upload(),
        owner=customer,
        kind=SecureDocument.KIND_PASSPORT,
        uploaded_by=SecureDocument.BY_CUSTOMER,
        **kwargs,
    )


class TestEncryptionAtRest:
    def test_storage_holds_ciphertext_not_the_file(self):
        """Главный замок: исходные байты не должны лежать в хранилище."""
        document = _store(_customer())
        with default_storage.open(document.path, "rb") as fh:
            stored = fh.read()
        assert stored != PNG
        assert not stored.startswith(b"\x89PNG")
        assert storage.read_decrypted(document.path) == PNG

    def test_note_is_encrypted_in_db(self):
        from django.db import connection

        document = _store(_customer(), note="Pass Nr. C01X00T47")
        with connection.cursor() as cur:
            cur.execute("SELECT note FROM documents_securedocument WHERE id = %s", [document.pk])
            raw = cur.fetchone()[0]
        assert "C01X00T47" not in raw
        assert SecureDocument.objects.get(pk=document.pk).note == "Pass Nr. C01X00T47"

    def test_stored_name_reveals_nothing(self):
        document = _store(_customer())
        assert "pass" not in document.path
        assert document.path.endswith(".enc")


class TestValidation:
    def test_rejects_unknown_type_even_with_valid_extension(self):
        """Тип определяется по сигнатуре, а не по расширению файла."""
        with pytest.raises(ValidationError):
            storage.validate(SimpleUploadedFile("scan.pdf", b"not a pdf at all"))

    def test_accepts_pdf_and_png(self):
        assert storage.validate(_upload(PDF, "a.pdf")) == "application/pdf"
        assert storage.validate(_upload(PNG, "a.png")) == "image/png"

    def test_rejects_too_large(self):
        big = SimpleUploadedFile("big.png", PNG)
        big.size = storage.MAX_BYTES + 1
        with pytest.raises(ValidationError):
            storage.validate(big)


class TestAccess:
    def test_owner_downloads_own_document(self):
        customer = _customer()
        document = _store(customer)
        response = views.document_download(_request(customer=customer), pk=document.pk)
        assert response.status_code == 200
        assert response.content == PNG
        assert response["Cache-Control"] == "private, no-store"

    def test_stranger_gets_404_not_403(self):
        """404, чтобы не подтверждать существование чужого документа."""
        document = _store(_customer())
        other = _customer("other@example.de")
        with pytest.raises(Http404):
            views.document_download(_request(customer=other), pk=document.pk)

    def test_anonymous_gets_404(self):
        document = _store(_customer())
        with pytest.raises(Http404):
            views.document_download(_request(), pk=document.pk)

    def test_staff_of_the_business_may_download(self):
        from apps.core.models import Membership

        document = _store(_customer())
        suffix = uuid.uuid4().hex[:8]
        user = get_user_model().objects.create_user(
            username=f"o-{suffix}", email=f"o-{suffix}@test.de", password="pw12345678"
        )
        Membership.objects.create(user=user, role=Membership.ROLE_OWNER)
        response = views.document_download(_request(user=user), pk=document.pk)
        assert response.status_code == 200

    def test_logged_in_user_without_membership_is_not_staff(self):
        """Fail-closed: логин сам по себе доступа к чужим документам не даёт."""
        document = _store(_customer())
        suffix = uuid.uuid4().hex[:8]
        user = get_user_model().objects.create_user(
            username=f"x-{suffix}", email=f"x-{suffix}@test.de", password="pw12345678"
        )
        with pytest.raises(Http404):
            views.document_download(_request(user=user), pk=document.pk)

    def test_stranger_cannot_delete(self):
        document = _store(_customer())
        other = _customer("other2@example.de")
        with pytest.raises(Http404):
            views.document_delete(_request("post", customer=other), pk=document.pk)
        assert SecureDocument.objects.filter(pk=document.pk).exists()


class TestRetention:
    def test_expiry_is_derived_from_the_departure(self):
        from apps.events.models import Event, Ticket

        customer = _customer()
        event = Event.objects.create(
            title="Manali – Leh",
            starts_at=timezone.now() + timezone.timedelta(days=30),
            ends_at=timezone.now() + timezone.timedelta(days=42),
        )
        ticket = Ticket.objects.create(event=event, customer=customer, quantity=1)
        document = _store(customer, ref_kind="ticket", ref_id=str(ticket.pk))
        expected = (event.ends_at + timezone.timedelta(days=services.retention_days())).date()
        assert document.expires_at == expected

    def test_purge_removes_record_and_blob(self):
        customer = _customer()
        document = _store(customer)
        document.expires_at = timezone.localdate() - timezone.timedelta(days=1)
        document.save(update_fields=["expires_at"])
        path = document.path
        assert services.purge_expired() == 1
        assert not SecureDocument.objects.filter(pk=document.pk).exists()
        assert not default_storage.exists(path)

    def test_documents_without_expiry_are_kept(self):
        document = _store(_customer())
        assert document.expires_at is None
        assert services.purge_expired() == 0
        assert SecureDocument.objects.filter(pk=document.pk).exists()


class TestUpload:
    def test_upload_requires_consent(self):
        customer = _customer()
        request = _request("post", data={"file": _upload(), "kind": "passport"}, customer=customer)
        views.documents_home(request)
        assert SecureDocument.objects.count() == 0

    def test_upload_stores_consent_moment(self):
        customer = _customer()
        request = _request(
            "post",
            data={"file": _upload(), "kind": "license", "consent": "1"},
            customer=customer,
        )
        views.documents_home(request)
        document = SecureDocument.objects.get()
        assert document.kind == "license"
        assert document.consent_at is not None
        assert document.uploaded_by == SecureDocument.BY_CUSTOMER
