"""P0-3 (аудит 2026-09-03 §9.3): перешифровать секреты явным ключом.

MultiFernet (apps.secrets.crypto) читает и старые шифротексты (производный от
SECRET_KEY ключ), и новые — поэтому задать SECRETS_ENCRYPTION_KEY безопасно. Но
пока старое не перешифровано, утечка SECRET_KEY по-прежнему раскрывает его.
Команда проходит public (PlatformSecret) и КАЖДУЮ схему тенанта: все
EncryptedTextField, секретные подключи Channel.config (publishing.SECRET_KEYS)
и файлы SecureDocument (*.enc).

По умолчанию dry-run — только считает. `--apply` пишет. Идемпотентна: уже
перешифрованное не трогает (crypto.needs_rotation). Ошибка в одной схеме не
валит обход — печатается, идём дальше.
"""

from django.apps import apps
from django.conf import settings
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.core.management.base import BaseCommand, CommandError
from django.db.models import TextField
from django.db.models.functions import Cast
from django_tenants.utils import get_public_schema_name, get_tenant_model, schema_context

from apps.secrets import crypto
from apps.secrets.fields import EncryptedTextField
from apps.secrets.models import PlatformSecret


class Command(BaseCommand):
    help = "Перешифровать секреты явным ключом (dry-run по умолчанию; --apply пишет)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--apply", action="store_true", help="Записать изменения (иначе только отчёт)."
        )

    def handle(self, *args, apply=False, **options):
        if not (getattr(settings, "SECRETS_ENCRYPTION_KEY", "") or ""):
            raise CommandError("SECRETS_ENCRYPTION_KEY не задан — ротировать не во что.")
        mode = "apply" if apply else "dry-run"
        total = self._platform_secrets(apply)
        self.stdout.write(f"public: PlatformSecret — {total}")

        tenant_model = get_tenant_model()
        schemas = tenant_model.objects.exclude(schema_name=get_public_schema_name()).values_list(
            "schema_name", flat=True
        )
        for schema in schemas:
            try:
                with schema_context(schema):
                    n = self._tenant_schema(apply)
            except Exception as exc:  # noqa: BLE001 — одна схема не валит обход
                self.stderr.write(f"{schema}: ОШИБКА {exc!r}")
                continue
            if n:
                self.stdout.write(f"{schema}: {n}")
            total += n
        self.stdout.write(f"[{mode}] секретов к перешифровке: {total}")

    # --- public ---

    def _platform_secrets(self, apply: bool) -> int:
        n = 0
        for pk, token in PlatformSecret.objects.values_list("pk", "value_encrypted"):
            if not crypto.needs_rotation(token):
                continue
            n += 1
            if apply:
                plain = crypto.decrypt(token)
                PlatformSecret.objects.filter(pk=pk).update(value_encrypted=crypto.encrypt(plain))
        return n

    # --- схема тенанта ---

    def _tenant_schema(self, apply: bool) -> int:
        return self._encrypted_fields(apply) + self._channel_configs(apply) + self._documents(apply)

    def _encrypted_fields(self, apply: bool) -> int:
        n = 0
        for model in apps.get_models():
            fields = [f for f in model._meta.get_fields() if isinstance(f, EncryptedTextField)]
            for field in fields:
                # Cast → TextField без конвертеров поля: видим ШИФРОТЕКСТ, а не
                # расшифровку, иначе needs_rotation не отличит старое от нового.
                rows = model._default_manager.annotate(
                    _raw=Cast(field.name, output_field=TextField())
                ).values_list("pk", "_raw")
                for pk, raw in rows:
                    if not crypto.needs_rotation(raw):
                        continue
                    n += 1
                    if apply:
                        # update() → get_prep_value поля → шифруется явным ключом.
                        plain = crypto.decrypt(raw)
                        model._default_manager.filter(pk=pk).update(**{field.name: plain})
        return n

    def _channel_configs(self, apply: bool) -> int:
        from apps.publishing.models import Channel
        from apps.publishing.secrets import SECRET_KEYS

        n = 0
        for channel in Channel.objects.all().iterator():
            cfg = dict(channel.config or {})
            changed = False
            for key in SECRET_KEYS:
                value = cfg.get(key)
                if isinstance(value, str) and crypto.needs_rotation(value):
                    n += 1
                    changed = True
                    if apply:
                        cfg[key] = crypto.encrypt(crypto.decrypt(value))
            if apply and changed:
                Channel.objects.filter(pk=channel.pk).update(config=cfg)
        return n

    def _documents(self, apply: bool) -> int:
        from apps.documents.models import SecureDocument

        n = 0
        for pk, path in SecureDocument.objects.exclude(path="").values_list("pk", "path"):
            if not default_storage.exists(path):
                continue
            with default_storage.open(path, "rb") as fh:
                blob = fh.read()
            if not crypto.needs_rotation(blob):
                continue
            n += 1
            if apply:
                rotated = crypto.rotate_bytes(blob)
                default_storage.delete(path)
                saved = default_storage.save(path, ContentFile(rotated))
                if saved != path:  # хранилище переименовало — путь в БД должен совпасть
                    SecureDocument.objects.filter(pk=pk).update(path=saved)
        return n
