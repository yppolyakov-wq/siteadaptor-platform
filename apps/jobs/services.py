"""Сервисы заявок/смет Handwerker (G6 / F1).

create_job — заявка (Anfrage) с переиспользованием Customer по email; set_lines —
заменить позиции сметы и пересчитать суммы снимком (через finance.compute_totals,
§19 Kleinunternehmer → НДС 0). Письма/PDF/Rechnung — F2/F3.
"""

import secrets
import string
from decimal import Decimal

from django.db import transaction

from apps.promotions.models import Customer

from .models import Job, JobLine

_ALPHABET = string.ascii_uppercase + string.digits


def _unique_job_code() -> str:
    for _ in range(10):
        code = "A-" + "".join(secrets.choice(_ALPHABET) for _ in range(6))
        if not Job.objects.filter(reference_code=code).exists():
            return code
    raise RuntimeError("could not generate unique job reference code")


def _get_or_create_customer(*, name, email, phone) -> Customer:
    if email:
        customer = Customer.objects.filter(email__iexact=email).order_by("created_at").first()
        if customer is not None:
            if not customer.phone and phone:
                customer.phone = phone
                customer.save(update_fields=["phone", "updated_at"])
            return customer
    return Customer.objects.create(name=name, email=email, phone=phone)


def create_job(
    *,
    title,
    name,
    email="",
    phone="",
    description="",
    site_address="",
    source_channel="",
    vehicle="",
    vehicle_plate="",
    vehicle_hsn="",
    vehicle_tsn="",
) -> Job:
    """Создать заявку (Anfrage). Customer переиспускается по email."""
    customer = _get_or_create_customer(name=name, email=email, phone=phone)
    return Job.objects.create(
        customer=customer,
        reference_code=_unique_job_code(),
        title=(title or "").strip()[:200] or "Anfrage",
        description=(description or "").strip()[:5000],
        site_address=(site_address or "").strip()[:2000],
        source_channel=(source_channel or "")[:50],
        vehicle=(vehicle or "").strip()[:120],
        # A9: структурные данные авто (Kennzeichen/HSN/TSN) — верхний регистр, обрезка.
        vehicle_plate=(vehicle_plate or "").strip().upper()[:15],
        vehicle_hsn=(vehicle_hsn or "").strip().upper()[:4],
        vehicle_tsn=(vehicle_tsn or "").strip().upper()[:3],
    )


def set_lines(job, lines, *, vat_rate=None, small_business=False) -> Job:
    """Заменить позиции сметы и пересчитать суммы (снимок).

    ``lines`` — список dict ``{"text", "qty", "unit_price"}``. Пустые строки
    (без текста) пропускаются. Суммы считаются через finance.compute_totals.
    """
    from apps.finance.services import compute_totals

    with transaction.atomic():
        job.lines.all().delete()
        objs = []
        for i, line in enumerate(lines):
            text = (line.get("text") or "").strip()
            if not text:
                continue
            objs.append(
                JobLine(
                    job=job,
                    position=i,
                    text=text[:300],
                    qty=line.get("qty", 1),
                    unit_price=line.get("unit_price", 0),
                    # G11: привязка строки к расходнику каталога (опц.).
                    product=line.get("product"),
                    variant=line.get("variant"),
                )
            )
        JobLine.objects.bulk_create(objs)

        if vat_rate is not None:
            job.vat_rate = Decimal(str(vat_rate))
        dict_lines = [{"text": o.text, "qty": o.qty, "unit_price": str(o.unit_price)} for o in objs]
        net, vat, gross = compute_totals(dict_lines, job.vat_rate, small_business=small_business)
        job.net, job.vat_amount, job.gross = net, vat, gross
        job.save(update_fields=["vat_rate", "net", "vat_amount", "gross", "updated_at"])
    return job


def commit_stock(job) -> None:
    """G11: списать остаток за расходники сметы (Teile) — один раз, при erledigt.

    Списываем только строки с привязкой к каталогу (product/variant) и учётом
    остатка (stock_quantity не null). Работа уже выполнена → не блокируем при
    нехватке, а клампим в 0 (паттерн R3 по атомарности, но без OutOfStock).
    Идемпотентно: гард ``job.stock_committed`` под select_for_update. Возврата при
    отмене нет — cancelled достижим только до done (см. JobSM).
    """
    from apps.catalog.models import Product, ProductVariant

    with transaction.atomic():
        locked = Job.objects.select_for_update().get(pk=job.pk)
        if locked.stock_committed:
            return
        for line in locked.lines.all():
            if line.variant_id:
                row = ProductVariant.objects.select_for_update().get(pk=line.variant_id)
            elif line.product_id:
                # all_objects: списываем и со снятого с витрины (soft-deleted) товара.
                row = Product.all_objects.select_for_update().get(pk=line.product_id)
            else:
                continue  # свободная строка (Arbeit) — склад не трогаем
            if row.stock_quantity is None:
                continue  # без учёта остатка
            # Склад целочисленный: дробное кол-во расходника округляем вверх.
            from math import ceil

            row.stock_quantity = max(0, row.stock_quantity - ceil(line.qty))
            row.save(update_fields=["stock_quantity", "updated_at"])
        locked.stock_committed = True
        locked.save(update_fields=["stock_committed", "updated_at"])
    job.stock_committed = True


MAX_PHOTOS = 5
MAX_PHOTO_BYTES = 8 * 1024 * 1024  # 8 МБ на файл


def add_job_photos(job, files, *, max_count=MAX_PHOTOS) -> int:
    """A7b: сохранить загруженные фото к заявке. Берём только изображения до 8 МБ,
    не больше max_count. Возвращает число сохранённых."""
    from .models import JobPhoto

    saved = 0
    for f in (files or [])[:max_count]:
        if not getattr(f, "content_type", "").startswith("image/"):
            continue
        if f.size and f.size > MAX_PHOTO_BYTES:
            continue
        JobPhoto.objects.create(job=job, image=f)
        saved += 1
    return saved


def lines_snapshot(job) -> list[dict]:
    """Позиции сметы в формате finance (для Rechnung-снимка / PDF)."""
    return [
        {"text": ln.text, "qty": str(ln.qty), "unit_price": str(ln.unit_price)}
        for ln in job.lines.all()
    ]


def quote_to_invoice(job, *, small_business=False):
    """Создать черновик Rechnung (apps.finance.Invoice) из позиций сметы заявки.

    Снимок позиций + получатель (клиент + адрес работ); суммы пересчитываются
    через finance.compute_totals (§19 → НДС 0), чтобы Rechnung совпала со сметой.
    Возвращает Invoice; ставит job.invoice_id. Переход done→invoiced — на вызове.
    """
    from apps.finance.models import Invoice
    from apps.finance.services import compute_totals

    lines = lines_snapshot(job)
    recipient = str(job.customer)
    if job.site_address:
        recipient = f"{recipient}\n{job.site_address}"
    net, vat, gross = compute_totals(lines, job.vat_rate, small_business=small_business)
    invoice = Invoice.objects.create(
        customer=job.customer,
        recipient=recipient[:500],
        lines=lines,
        vat_rate=Decimal("0") if small_business else job.vat_rate,
        net=net,
        vat_amount=vat,
        gross=gross,
        note=f"Auftrag {job.reference_code}: {job.title}"[:200],
    )
    job.invoice_id = invoice.id
    job.save(update_fields=["invoice_id", "updated_at"])
    return invoice
