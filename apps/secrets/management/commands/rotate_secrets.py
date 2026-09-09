"""P0-3 (аудит 2026-09-03 §9.3): перешифровать секреты явным ключом.

MultiFernet (apps.secrets.crypto) читает и старые шифротексты (производный от
SECRET_KEY ключ), и новые — поэтому задать SECRETS_ENCRYPTION_KEY безопасно. Но
пока старое не перешифровано, утечка SECRET_KEY по-прежнему раскрывает его.
Команда проходит public (PlatformSecret) и КАЖДУЮ схему тенанта: все
EncryptedTextField, секретные подключи Channel.config (publishing.SECRET_KEYS)
и файлы SecureDocument (*.enc).

По умолчанию dry-run — только считает. `--apply` пишет. Идемпотентна: уже
перешифрованное не трогает (crypto.needs_rotation). Ошибка в одной схеме не
валит обход — печатается, идём дальше; но в конце команда падает с перечнем
сбойных схем: «прошло без ошибок» и «выход 0» обязаны значить одно и то же,
иначе владелец сочтёт ротацию выполненной и решит, что утечка SECRET_KEY уже
безопасна.

Прод во время ротации РАБОТАЕТ, поэтому пишем не по снимку: значение
перечитывается под блокировкой строки, и свежая запись приложения переживает
проход. Файлы документов пишутся в НОВОЕ имя (старое удаляется только после
переключения указателя) — сбой хранилища между delete и save уничтожал бы
единственный экземпляр шифротекста.
"""

import logging
import posixpath
import uuid

from django.apps import apps
from django.conf import settings
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.db.models import TextField
from django.db.models.functions import Cast
from django_tenants.utils import get_public_schema_name, get_tenant_model, schema_context

from apps.secrets import crypto
from apps.secrets.fields import EncryptedTextField
from apps.secrets.models import PlatformSecret

logger = logging.getLogger(__name__)


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
        failed = []
        total = 0
        try:
            total = self._platform_secrets(apply)
        except Exception as exc:  # noqa: BLE001 — public не валит обход схем
            self.stderr.write(f"public: ОШИБКА {exc!r}")
            failed.append(get_public_schema_name())
        self.stdout.write(f"public: PlatformSecret — {total}")

        tenant_model = get_tenant_model()
        schemas = tenant_model.objects.exclude(schema_name=get_public_schema_name()).values_list(
            "schema_name", flat=True
        )
        for schema in schemas:
            errors = []
            n = 0
            try:
                with schema_context(schema):
                    n = self._tenant_schema(apply, errors)
            except Exception as exc:  # noqa: BLE001 — одна схема не валит обход
                errors.append(repr(exc))
            for err in errors:
                self.stderr.write(f"{schema}: ОШИБКА {err}")
            if errors:
                failed.append(schema)
            if n:
                self.stdout.write(f"{schema}: {n}")
            total += n
        self.stdout.write(f"[{mode}] секретов к перешифровке: {total}")
        if failed:
            # Ненулевой код + перечень: «ротация выполнена» не должно быть ложью,
            # а повторить точечно можно по именам из сообщения.
            raise CommandError(
                "схемы с ошибками (секреты в них НЕ перешифрованы полностью): " + ", ".join(failed)
            )

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

    def _tenant_schema(self, apply: bool, errors: list) -> int:
        """Три прохода НЕЗАВИСИМЫ: падение документов не должно обнулять уже
        сделанную работу по полям и каналам (и их вклад в счётчик)."""
        n = 0
        for name, step in (
            ("поля", self._encrypted_fields),
            ("каналы", self._channel_configs),
            ("документы", self._documents),
        ):
            try:
                n += step(apply)
            except Exception as exc:  # noqa: BLE001
                errors.append(f"{name}: {exc!r}")
        return n

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
                        self._rotate_field(model, field, pk)
        return n

    def _rotate_field(self, model, field, pk) -> None:
        """Перечитать значение ПОД БЛОКИРОВКОЙ строки и только потом писать.

        Снимок `rows` снимается до начала записи, а обход всех моделей всех схем
        идёт минутами: за это время гость сохранит Meldeschein, владелец сменит
        токен бота. Запись по снимку молча вернула бы старое значение —
        расхождение необнаружимо (поле шифрованное, по нему не отфильтруешь).
        """
        with transaction.atomic():
            fresh = (
                model._default_manager.select_for_update()
                .annotate(_raw=Cast(field.name, output_field=TextField()))
                .filter(pk=pk)
                .values_list("_raw", flat=True)
                .first()
            )
            if fresh is None or not crypto.needs_rotation(fresh):
                return  # строку удалили или приложение уже переписало её явным ключом
            # update() → get_prep_value поля → шифруется явным ключом.
            model._default_manager.filter(pk=pk).update(**{field.name: crypto.decrypt(fresh)})

    def _channel_configs(self, apply: bool) -> int:
        from apps.publishing.models import Channel
        from apps.publishing.secrets import SECRET_KEYS

        n = 0
        for pk, config in Channel.objects.values_list("pk", "config").iterator():
            stale = [
                key
                for key in SECRET_KEYS
                if isinstance((config or {}).get(key), str) and crypto.needs_rotation(config[key])
            ]
            if not stale:
                continue
            n += len(stale)
            if not apply:
                continue
            # Весь JSON пишется целиком (так же его пишут oauth/views), поэтому
            # мутируем СВЕЖИЙ словарь под блокировкой строки: иначе параллельное
            # переподключение канала было бы молча откачено снимком.
            with transaction.atomic():
                channel = Channel.objects.select_for_update().filter(pk=pk).first()
                if channel is None:
                    continue
                cfg = dict(channel.config or {})
                changed = False
                for key in SECRET_KEYS:
                    value = cfg.get(key)
                    if isinstance(value, str) and crypto.needs_rotation(value):
                        cfg[key] = crypto.encrypt(crypto.decrypt(value))
                        changed = True
                if changed:
                    Channel.objects.filter(pk=pk).update(config=cfg)
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
                # Пишем в НОВОЕ имя и только потом переключаем указатель. Раньше
                # было delete(path) → save(path, …): сбой хранилища между ними
                # (5xx, обрыв, OOM) уничтожал единственный экземпляр шифротекста —
                # плейнтекст живёт только в памяти процесса. Осиротевший старый
                # файл безопаснее уничтоженного нового.
                rotated = crypto.rotate_bytes(blob)
                folder = posixpath.dirname(path) or "documents"
                saved = default_storage.save(
                    f"{folder}/{uuid.uuid4().hex}.enc", ContentFile(rotated)
                )
                SecureDocument.objects.filter(pk=pk).update(path=saved)
                try:
                    default_storage.delete(path)
                except Exception:  # noqa: BLE001 — указатель уже переключён
                    logger.warning("rotate_secrets: старый blob %s не удалён", path)
        return n
