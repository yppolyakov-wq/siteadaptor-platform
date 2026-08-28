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
    site_plz="",
    source_channel="",
    vehicle="",
    vehicle_plate="",
    vehicle_hsn="",
    vehicle_tsn="",
    event_date=None,
    guest_count=None,
    event_type="",
) -> Job:
    """Создать заявку (Anfrage). Customer переиспускается по email."""
    customer = _get_or_create_customer(name=name, email=email, phone=phone)
    job = Job.objects.create(
        customer=customer,
        reference_code=_unique_job_code(),
        title=(title or "").strip()[:200] or "Anfrage",
        description=(description or "").strip()[:5000],
        site_address=(site_address or "").strip()[:2000],
        site_plz=(site_plz or "").strip()[:10],  # A7: PLZ объекта (Einzugsgebiet)
        source_channel=(source_channel or "")[:50],
        vehicle=(vehicle or "").strip()[:120],
        # A9: структурные данные авто (Kennzeichen/HSN/TSN) — верхний регистр, обрезка.
        vehicle_plate=(vehicle_plate or "").strip().upper()[:15],
        vehicle_hsn=(vehicle_hsn or "").strip().upper()[:4],
        vehicle_tsn=(vehicle_tsn or "").strip().upper()[:3],
        # AF-1: событийные поля — валидация (fail-soft дата/гости, whitelist типа)
        # на вызывающей стороне (public_views.anfrage); сервис хранит как есть.
        event_date=event_date,
        guest_count=guest_count,
        event_type=(event_type or "").strip()[:100],
    )
    # C2: «спросил с сайта → оставил заявку» — одна беседа (fail-soft, однозначность).
    from apps.inbox.deal_threads import adopt_open_thread, deal_ref_label

    adopt_open_thread(
        customer,
        ref_kind="job",
        ref_id=job.reference_code,
        ref_label=deal_ref_label("job", job.reference_code),
    )
    return job


def _line_vat_rate(line):
    """Ставка позиции сметы: явная из формы, иначе из карточки товара, иначе None.

    None означает «как весь документ» — существующие сметы так и продолжают
    считаться. Ставка товара берётся СНИМКОМ на момент сохранения: правка
    каталога не переписывает смету, которую клиент уже видел.
    """
    raw = line.get("vat_rate")
    if raw not in (None, ""):
        return Decimal(str(raw))
    variant = line.get("variant")
    product = line.get("product")
    if variant is not None and getattr(variant, "product_id", None) and product is None:
        product = variant.product
    if product is not None:
        rate = getattr(product, "vat_rate", None)
        if rate is not None:
            return Decimal(str(rate))
    return None


def set_lines(job, lines, *, vat_rate=None, small_business=False) -> Job:
    """Заменить позиции сметы и пересчитать суммы (снимок).

    ``lines`` — список dict ``{"text", "qty", "unit_price"}``. Пустые строки
    (без текста) пропускаются. Суммы считаются через finance.compute_totals.
    """
    from apps.jobs.totals import quote_totals

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
                    cost_rate=line.get("cost_rate"),  # ERP-6: плановый EK/ставка
                    # VAT-1: своя ставка позиции. None = ставка документа.
                    vat_rate=_line_vat_rate(line),
                    # G11: привязка строки к расходнику каталога (опц.).
                    product=line.get("product"),
                    variant=line.get("variant"),
                )
            )
        JobLine.objects.bulk_create(objs)

        if vat_rate is not None:
            job.vat_rate = Decimal(str(vat_rate))
        # VAT-1: итог считается по ставкам ПОЗИЦИЙ (строка без своей ставки идёт по
        # ставке документа — поэтому смета без смешанных ставок считается как раньше).
        totals = quote_totals(objs, job.vat_rate, small_business=small_business)
        job.net, job.vat_amount, job.gross = totals["net"], totals["vat"], totals["gross"]
        job.save(update_fields=["vat_rate", "net", "vat_amount", "gross", "updated_at"])
        # VF-13: если резерв уже держится (Beauftragt) — привести его к новому составу.
        _resync_reserved_stock(job)
    return job


def commit_stock(job) -> None:
    """G11/VF-13: списать остаток за расходники сметы (Teile) — один раз.

    С VF-13 вызывается уже при ПРИНЯТИИ сметы (Beauftragt) — резерв, чтобы
    витрина не продала заложенные под заявку детали; при erledigt повтор —
    идемпотентный no-op. Списываем только строки с привязкой к каталогу
    (product/variant) и учётом остатка (stock_quantity не null). Принятие
    клиентом/вебхуком не блокируем при нехватке, а клампим в 0 (паттерн R3 по
    атомарности, но без OutOfStock — детали докупаются). Идемпотентно: гард
    ``job.stock_committed`` под select_for_update. Возврат при отмене —
    ``release_stock``.
    """
    from math import ceil

    from apps.catalog.models import Product, ProductVariant
    from apps.inventory.services import record_movement

    with transaction.atomic():
        locked = Job.objects.select_for_update().get(pk=job.pk)
        if locked.stock_committed:
            return
        for line in locked.lines.all():
            if line.variant_id:
                row = ProductVariant.objects.select_for_update().get(pk=line.variant_id)
                prod, var = row.product, row
            elif line.product_id:
                # all_objects: списываем и со снятого с витрины (soft-deleted) товара.
                row = Product.all_objects.select_for_update().get(pk=line.product_id)
                prod, var = row, None
            else:
                continue  # свободная строка (Arbeit) — склад не трогаем
            if row.stock_quantity is None:
                continue  # без учёта остатка
            # Склад целочисленный: дробное кол-во расходника округляем вверх, при
            # нехватке клампим в 0 (работа выполнена). В леджер — ФАКТИЧЕСКИЙ расход.
            before = row.stock_quantity
            row.stock_quantity = max(0, before - ceil(line.qty))
            row.save(update_fields=["stock_quantity", "updated_at"])
            if row.stock_quantity != before:  # U-D3: залогировать фактический расход
                record_movement(
                    product=prod,
                    variant=var,
                    kind="commit",
                    delta=row.stock_quantity - before,
                    source="job",
                    source_ref=str(line.pk),
                    note=locked.reference_code,
                )
                # Склад-2 E1.5: расход материалов гасит партии FEFO (no-op без партий).
                from apps.inventory.services import consume_fefo, has_lots

                if has_lots(prod, var):
                    consume_fefo(prod, var, qty=before - row.stock_quantity)
        locked.stock_committed = True
        locked.save(update_fields=["stock_committed", "updated_at"])
    job.stock_committed = True


def release_stock(job) -> None:
    """VF-13: вернуть зарезервированное по смете при отмене (Storno/Abgelehnt).

    Возврат идёт по ЛЕДЖЕРУ (source="job", kind="commit", note=reference_code),
    а не по строкам — строки пересоздаются при каждом Save сметы и могли
    отвязаться/исчезнуть. Return-движение пишется ПЕРВЫМ (дедуп конституционный
    по (source, ref, kind), ref="ret:<pk движения>"), счётчик двигается
    conditional UPDATE только при созданном движении — повторный вызов и
    двухшаговые обходы безопасны. Возвращается ровно фактически списанное
    (вкл. клампы). Гард stock_committed снимается; повторный резерв после
    отмены невозможен (рёбер ИЗ cancelled-роли не бывает).
    """
    from django.db.models import F

    from apps.catalog.models import Product, ProductVariant
    from apps.inventory.models import StockMovement
    from apps.inventory.services import record_movement, restore_fefo

    with transaction.atomic():
        locked = Job.objects.select_for_update().get(pk=job.pk)
        if not locked.stock_committed:
            return
        movements = StockMovement.objects.filter(
            source="job", kind="commit", note=locked.reference_code
        )
        for mv in movements:
            qty = -mv.delta
            if qty <= 0:
                continue
            created = record_movement(
                product=mv.product,
                variant=mv.variant,
                kind="return",
                delta=qty,
                source="job",
                source_ref=f"ret:{mv.pk}",
                note=locked.reference_code,
            )
            if created is None:
                continue  # это движение уже возвращали (дедуп)
            if mv.variant_id:
                ProductVariant.objects.filter(
                    pk=mv.variant_id, stock_quantity__isnull=False
                ).update(stock_quantity=F("stock_quantity") + qty)
            else:
                Product.all_objects.filter(pk=mv.product_id, stock_quantity__isnull=False).update(
                    stock_quantity=F("stock_quantity") + qty
                )
            restore_fefo(mv.product, mv.variant, qty=qty)
        locked.stock_committed = False
        locked.save(update_fields=["stock_committed", "updated_at"])
    job.stock_committed = False


def _resync_reserved_stock(job) -> None:
    """VF-13: смета с активным резервом правится → резерв следует новым строкам.

    Release + повторный commit в одной atomic (net-эффект = дельта состава).
    Только пока статус в роли active — после done/invoiced правка сметы склад
    не трогает (история; прежнее поведение), у отменённой резерва нет.
    """
    from apps.core import status_registry

    desc = status_registry.resolve("job", job.status)
    if desc is None or desc.role != "active" or not job.stock_committed:
        return
    with transaction.atomic():
        release_stock(job)
        commit_stock(job)


MAX_PHOTOS = 5
MAX_PHOTO_BYTES = 8 * 1024 * 1024  # 8 МБ на файл


_PHOTO_EXT = {"JPEG": "jpg", "PNG": "png", "WEBP": "webp"}


def add_job_photos(job, files, *, max_count=MAX_PHOTOS) -> int:
    """A7b: сохранить загруженные фото к заявке. Форма ПУБЛИЧНАЯ (без логина),
    поэтому реальный формат проверяем Pillow'ом (не доверяем клиентскому
    content_type/расширению), а имя перезаписываем на uuid.ext — иначе аноним мог
    залить .html/.svg и получить stored-XSS на домене бизнеса. Возвращает число
    сохранённых."""
    import uuid

    from django.core.exceptions import ValidationError

    from apps.catalog.images import validate_image

    from .models import JobPhoto

    saved = 0
    for f in (files or [])[:max_count]:
        if f.size and f.size > MAX_PHOTO_BYTES:
            continue
        try:
            fmt = validate_image(f)  # Pillow: реальный формат ∈ JPEG/PNG/WEBP + ≤5 МБ
        except ValidationError:
            continue
        f.name = f"{uuid.uuid4().hex}.{_PHOTO_EXT.get(fmt, 'jpg')}"
        JobPhoto.objects.create(job=job, image=f)
        saved += 1
    return saved


def lines_snapshot(job) -> list[dict]:
    """Позиции сметы в формате finance (для Rechnung-снимка / PDF)."""
    return [
        {
            "text": ln.text,
            "qty": str(ln.qty),
            "unit_price": str(ln.unit_price),
            # VAT-4: ставка позиции едет в счёт — иначе смешанная смета дала бы
            # Rechnung, брутто которой не совпадает с принятой клиентом сметой.
            "vat_rate": str(ln.effective_vat_rate(job.vat_rate)),
        }
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
