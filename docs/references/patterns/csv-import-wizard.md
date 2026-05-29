# Pattern: 4-Step CSV Import Wizard

Статус: Phase 1, Sprint 2 (вместо one-shot django-import-export).
Ссылается из: `phase1-plan-additions.md` §2.1.

## Зачем state machine, а не one-shot

`django-import-export` делает импорт за один синхронный проход — на больших
файлах таймаутит, не даёт владельцу сопоставить колонки и увидеть превью до
записи, плохо переживает частичные сбои. 4-шаговый wizard:

```
uploaded → mapped → previewed → running → completed | failed
```

даёт: маппинг колонок руками, dry-run валидацию с превью, фоновую запись с
прогрессом, частичный результат (N ок / M ошибок) и переиспользование в
Phase 2 для Shopify/WooCommerce (тот же конвейер, другой парсер источника).

## Модели (tenant-схема)

```python
# apps/imports/models.py
from django.db import models
from apps.core.models import TimestampedModel


class ImportJob(TimestampedModel):
    STATUS = ["uploaded", "mapped", "previewed", "running", "completed", "failed"]

    resource_type = models.CharField(max_length=50)  # 'product', 'customer'
    status = models.CharField(max_length=20, default="uploaded", db_index=True)
    source_file = models.FileField(upload_to="imports/")
    # сопоставление колонок файла → поля модели: {"Name": "name.de", "Preis": "price"}
    column_mapping = models.JSONField(default=dict, blank=True)
    options = models.JSONField(default=dict, blank=True)  # delimiter, update_existing...

    total_rows = models.IntegerField(default=0)
    processed_rows = models.IntegerField(default=0)
    ok_rows = models.IntegerField(default=0)
    error_rows = models.IntegerField(default=0)
    error_summary = models.TextField(blank=True)


class ImportRow(TimestampedModel):
    job = models.ForeignKey(ImportJob, on_delete=models.CASCADE, related_name="rows")
    line_no = models.IntegerField()
    raw = models.JSONField(default=dict)             # исходная строка
    status = models.CharField(max_length=20, default="pending")  # ok|error|skipped
    errors = models.JSONField(default=list, blank=True)
    created_object_id = models.CharField(max_length=100, blank=True)

    class Meta:
        indexes = [models.Index(fields=["job", "status"])]
```

Переходы статуса `ImportJob` — через общий FSM (см. `state-machine.md`).

## Шаги

**1. uploaded** — загрузка файла, определение разделителя/кодировки, чтение
заголовков. Парсим только header + первые ~20 строк для предпросмотра колонок.

**2. mapped** — владелец сопоставляет колонки файла полям ресурса (UI на HTMX:
селекты «колонка → поле»). Сохраняем `column_mapping`. Валидируем, что
обязательные поля ресурса покрыты.

**3. previewed (dry-run)** — фоновая задача прогоняет ВСЕ строки через
валидацию **без записи**, наполняет `ImportRow` со `status` и `errors`,
считает `total/ok/error`. Владелец видит «480 ок, 20 с ошибками» и таблицу
проблемных строк до коммита.

```python
@idempotent_task()
def preview_import(job_id):
    job = ImportJob.objects.get(id=job_id)
    processor = get_processor(job.resource_type)   # реестр по resource_type
    for line_no, raw in enumerate(read_rows(job), start=1):
        data = apply_mapping(raw, job.column_mapping)
        errors = processor.validate(data)           # НЕ пишет в БД
        ImportRow.objects.create(
            job=job, line_no=line_no, raw=raw,
            status="error" if errors else "ok", errors=errors,
        )
    _recount(job)
    sm.apply(job, "previewed")
```

**4. running → completed/failed** — после подтверждения владельцем фоновая
задача пишет валидные строки **батчами в транзакции на батч** (не одна
транзакция на весь файл — иначе сбой на 9999-й строке откатит всё). Ошибки
строк не валят job; job → `failed` только при инфраструктурном сбое.

```python
@idempotent_task()
def run_import(job_id):
    job = ImportJob.objects.get(id=job_id)
    sm.apply(job, "running")
    processor = get_processor(job.resource_type)
    for batch in chunked(job.rows.filter(status="ok"), 500):
        with transaction.atomic():
            for row in batch:
                obj = processor.create_or_update(
                    apply_mapping(row.raw, job.column_mapping),
                    update_existing=job.options.get("update_existing", False),
                )
                row.created_object_id = str(obj.pk)
            ImportRow.objects.bulk_update(batch, ["created_object_id"])
        job.processed_rows = F("processed_rows") + len(batch)
        job.save(update_fields=["processed_rows"])
    _recount(job)
    sm.apply(job, "completed")
```

## Процессоры (расширяемость)

Реестр обработчиков по `resource_type` — в `apps/imports/processors/`. Каждый
реализует `validate(data) -> list[errors]` и `create_or_update(data, *,
update_existing)`. В Phase 2 добавляются процессоры-парсеры источников
(Shopify/WooCommerce) поверх тех же шагов 3–4.

## Тонкости

- **Идемпотентность**: задачи через `idempotent_task`; повторный запуск
  `run_import` не должен задваивать объекты — используем natural key/`sku` в
  `create_or_update(update_existing=...)`.
- **Транзакция на батч**, не на файл — частичный успех + рестарт с места.
- **i18n-поля**: маппинг умеет `name.de` / `name.en` → собирает JSONField.
- **Лимиты**: max размер файла и max строк (напр. 50k) — защита от OOM;
  читать потоково (csv.reader по строкам), не грузить файл в память целиком.
- **Файл**: после `completed` исходник можно удалить/архивировать по политике.

## Чек-лист

- [ ] FSM `uploaded→mapped→previewed→running→completed|failed`.
- [ ] dry-run (previewed) наполняет `ImportRow` без записи в БД.
- [ ] Запись батчами по 500 в транзакции на батч.
- [ ] Ошибки строк не валят весь job; считается ok/error.
- [ ] Задачи идемпотентны; повтор не задваивает объекты.
- [ ] Потоковое чтение + лимиты размера/строк.
