"""Приём и выдача зашифрованных файлов (MT-2).

Единственная точка, где документ попадает в хранилище и покидает его. Валидация
идёт ПО СИГНАТУРЕ файла, а не по расширению: расширение пишет тот, кто загружает.
"""

import uuid

from django.core.exceptions import ValidationError
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.utils.translation import gettext_lazy as _

from apps.secrets import crypto

# Решение владельца (§0b.3): до 50 МБ — фото, PDF, GPX-треки, короткие видео.
MAX_BYTES = 50 * 1024 * 1024

MIME_PDF = "application/pdf"
MIME_GPX = "application/gpx+xml"

#: (сигнатура, смещение, mime). Порядок важен: сначала точные магии.
_SIGNATURES = (
    (b"\xff\xd8\xff", 0, "image/jpeg"),
    (b"\x89PNG\r\n\x1a\n", 0, "image/png"),
    (b"%PDF-", 0, MIME_PDF),
    (b"ftyp", 4, "video/mp4"),
)


def _sniff(head: bytes) -> str:
    for sig, offset, mime in _SIGNATURES:
        if head[offset : offset + len(sig)] == sig:
            return mime
    # WEBP: RIFF....WEBP — размер между сигнатурами, отдельной проверкой.
    if head[:4] == b"RIFF" and head[8:12] == b"WEBP":
        return "image/webp"
    # GPX — обычный XML с корнем <gpx …>; смотрим начало текста.
    text = head[:512].lstrip().lower()
    if text.startswith(b"<?xml") and b"<gpx" in head[:2048].lower():
        return MIME_GPX
    return ""


def validate(uploaded) -> str:
    """Проверить размер и реальный тип; вернуть mime. Иначе ValidationError."""
    if uploaded.size > MAX_BYTES:
        raise ValidationError(_("Die Datei ist zu groß (maximal 50 MB)."))
    head = uploaded.read(2048)
    uploaded.seek(0)
    mime = _sniff(head or b"")
    if not mime:
        raise ValidationError(_("Erlaubt sind Fotos, PDF, GPX und MP4."))
    return mime


def save_encrypted(uploaded, *, folder="documents") -> tuple[str, str, int]:
    """Зашифровать содержимое и положить в storage. → (path, mime, размер).

    Имя в бакете — случайное, без расширения: по ключу нельзя понять, что внутри.
    """
    mime = validate(uploaded)
    raw = uploaded.read()
    uploaded.seek(0)
    name = f"{folder}/{uuid.uuid4().hex}.enc"
    path = default_storage.save(name, ContentFile(crypto.encrypt_bytes(raw)))
    return path, mime, len(raw)


def read_decrypted(path: str) -> bytes:
    """Расшифрованное содержимое; пропавший файл/чужой ключ → b'' (не падаем)."""
    if not path or not default_storage.exists(path):
        return b""
    with default_storage.open(path, "rb") as fh:
        return crypto.decrypt_bytes(fh.read())


def delete_blob(path: str) -> None:
    if path and default_storage.exists(path):
        default_storage.delete(path)
