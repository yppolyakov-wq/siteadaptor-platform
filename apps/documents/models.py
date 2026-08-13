"""Досье участника: документы, зашифрованные в хранилище (MT-2, TENANT).

Зачем отдельная сущность, а не FileRef как у фото: паспорт/права/страховка — это
чувствительные персональные данные. Отсюда три отличия от галерей платформы:

1. **Содержимое файла шифруется** (Fernet) ПЕРЕД записью в storage — в бакете
   лежит шифротекст, а не документ.
2. **Прямого URL не существует.** Отдаёт только proxy-вьюха с проверкой доступа;
   `default_storage.url()` для документов не зовём нигде.
3. **Срок хранения конечен** — `expires_at` проставляется при загрузке (конец
   поездки + `DOCUMENT_RETENTION_DAYS`), beat удаляет и запись, и blob.

Привязка к сделке — мягкая (`ref_kind`/`ref_id`, паттерн inbox): тред документов
переживает удаление события, а FK на билет заставил бы каскадно решать судьбу
файла при каждой отмене.
"""

from django.db import models
from django.utils.translation import gettext_lazy as _

from apps.core.models import TimestampedModel
from apps.promotions.models import Customer
from apps.secrets.fields import EncryptedTextField


class SecureDocument(TimestampedModel):
    KIND_PASSPORT = "passport"
    KIND_LICENSE = "license"
    KIND_INSURANCE = "insurance"
    KIND_VISA = "visa"
    KIND_OTHER = "other"
    KINDS = [
        (KIND_PASSPORT, _("Reisepass")),
        (KIND_LICENSE, _("Führerschein")),
        (KIND_INSURANCE, _("Versicherung")),
        (KIND_VISA, _("Visum")),
        (KIND_OTHER, _("Sonstiges")),
    ]

    BY_CUSTOMER = "customer"
    BY_STAFF = "staff"
    UPLOADERS = [(BY_CUSTOMER, _("Teilnehmer")), (BY_STAFF, _("Team"))]

    owner = models.ForeignKey(Customer, on_delete=models.CASCADE, related_name="documents")
    kind = models.CharField(max_length=20, choices=KINDS, default=KIND_OTHER)
    # Мягкая привязка к сделке: ("ticket", <uuid>) — билет на заезд.
    ref_kind = models.CharField(max_length=20, blank=True)
    ref_id = models.CharField(max_length=64, blank=True)
    # Ключ шифротекста в storage. Имя файла НЕ несёт исходного имени/типа.
    path = models.CharField(max_length=255)
    original_name = models.CharField(max_length=255, blank=True)
    mime = models.CharField(max_length=100, blank=True)
    size = models.PositiveIntegerField(default=0)  # размер ИСХОДНОГО файла, байт
    # Номер документа и прочие подписи — шифруются в БД (Fernet).
    note = EncryptedTextField(blank=True)
    uploaded_by = models.CharField(max_length=20, choices=UPLOADERS, default=BY_CUSTOMER)
    # Согласие на хранение (доказательство, как marketing_opt_in_at).
    consent_at = models.DateTimeField(null=True, blank=True)
    # Дата, после которой документ удаляется вместе с blob (retention).
    expires_at = models.DateField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["owner", "kind"], name="doc_owner_kind_idx"),
            models.Index(fields=["expires_at"], name="doc_expires_idx"),
        ]

    def __str__(self):
        return f"{self.get_kind_display()} · {self.owner_id}"

    @property
    def size_kb(self) -> int:
        return max(1, round(self.size / 1024))

    @property
    def is_image(self) -> bool:
        return self.mime.startswith("image/")
