"""P0-2: `cleanup_import_files` — легаси-загрузки импорта уходят из общего /media/.

Гейт раздачи их больше не отдаёт, новые импорты удаляют файл сами, но в проде
лежат файлы завершённых импортов и брошенных загрузок с исходными именами.
"""

from datetime import timedelta

import pytest
from django.core.files.storage import default_storage
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.utils import timezone

from apps.imports.models import ImportJob
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db


def _job(status, *, days_old=0):
    job = ImportJob.objects.create(
        resource_type="product",
        status=status,
        source_file=SimpleUploadedFile("Kundenpreise.csv", b"sku;price\n"),
    )
    if days_old:
        ImportJob.objects.filter(pk=job.pk).update(
            updated_at=timezone.now() - timedelta(days=days_old)
        )
    return job


def _refreshed(job):
    return ImportJob.objects.get(pk=job.pk)


def test_dry_run_counts_apply_deletes_and_is_idempotent(capsys):
    TenantFactory(schema_name="impclean_t1", slug="impclean-t1")  # команда входит в схему
    completed = _job("completed")
    stale_failed = _job("failed", days_old=40)
    stale_uploaded = _job("uploaded", days_old=31)
    fresh_uploaded = _job("uploaded")
    fresh_failed = _job("failed", days_old=3)
    paths = {
        j.pk: j.source_file.name
        for j in (completed, stale_failed, stale_uploaded, fresh_uploaded, fresh_failed)
    }

    call_command("cleanup_import_files")
    out = capsys.readouterr().out
    assert "dry-run" in out and "3" in out
    assert all(default_storage.exists(p) for p in paths.values())  # dry-run не трогает

    call_command("cleanup_import_files", "--apply")
    assert "dry-run" not in capsys.readouterr().out
    for job in (completed, stale_failed, stale_uploaded):
        assert not _refreshed(job).source_file
        assert not default_storage.exists(paths[job.pk])
    for job in (fresh_uploaded, fresh_failed):  # свежие — владелец ещё может продолжить
        assert _refreshed(job).source_file.name == paths[job.pk]
        assert default_storage.exists(paths[job.pk])

    call_command("cleanup_import_files", "--apply")
    assert "к удалению: 0" in capsys.readouterr().out


def test_missing_file_in_storage_is_detached_not_an_error(capsys):
    TenantFactory(schema_name="impclean_t2", slug="impclean-t2")
    job = _job("completed")
    default_storage.delete(job.source_file.name)  # файл пропал раньше команды
    call_command("cleanup_import_files", "--apply")
    assert "ОШИБКА" not in capsys.readouterr().err
    assert not _refreshed(job).source_file


def test_older_than_days_is_configurable():
    TenantFactory(schema_name="impclean_t3", slug="impclean-t3")
    job = _job("failed", days_old=5)
    call_command("cleanup_import_files", "--apply", "--older-than-days", "3")
    assert not _refreshed(job).source_file
