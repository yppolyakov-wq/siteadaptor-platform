"""Применение черновика импорта (T-8.27c): выбранные позиции → каталог, профиль → Tenant.

Цена — как на сайте: `list_price`, бейдж и акции не создаются (PAngV). Позиция без
цены становится «Nur auf Anfrage» (иначе витрина показала бы «0,00 €»). Лимит
бесплатной ступени (Р-B, `IMPORT_FREE_ITEMS`) проверяется здесь, на сервере, под
advisory-lock схемы — две вкладки не обойдут его гонкой. Фото скачиваются после
коммита фоновой задачей (`fetch_images`) через `core.ssrf.safe_fetch`."""

from __future__ import annotations

import io
import logging
import zlib
from dataclasses import dataclass, field
from decimal import Decimal

from django.conf import settings
from django.db import connection, transaction
from django.utils import timezone

from . import structured

logger = logging.getLogger(__name__)
IMAGE_TYPES = ("image/jpeg", "image/png", "image/webp")
MAX_PIXELS = 40_000_000
PROFILE_FIELDS = ("phone", "address", "opening_hours_structured", "description")


@dataclass
class ApplyResult:
    created: int = 0
    updated: int = 0
    over_limit: int = 0
    errors: list = field(default_factory=list)


def free_limit(tenant) -> int | None:
    """Сколько импортированных позиций бесплатно; None — без ограничения."""
    if tenant is None or getattr(tenant, "is_demo", False):
        return None
    if getattr(tenant, "subscription_status", "") == "active":
        return None
    limit = getattr(settings, "IMPORT_FREE_ITEMS", 50)
    return limit if limit and limit > 0 else None


def used_count() -> int:
    """Импортированные позиции, которые сейчас живут в каталоге: последнее применённое
    состояние без отключённых как пропавшие (T-8.27f)."""
    from .service import applied_state

    return len({(v["target_kind"], v["target_id"]) for v in applied_state().values()})


def usage(tenant) -> dict | None:
    limit = free_limit(tenant)
    if limit is None:
        return None
    used = used_count()
    return {"used": used, "limit": limit, "left": max(0, limit - used)}


def _lock_schema():
    key = zlib.crc32(f"site-import:{connection.schema_name}".encode())
    with connection.cursor() as cursor:
        cursor.execute("SELECT pg_advisory_xact_lock(%s)", [key])


def _previous_target(item):
    """Цель той же позиции из прошлых применённых прогонов (повторный импорт → update)."""
    from ..models import SiteImportItem

    prev = (
        SiteImportItem.objects.filter(identity_key=item.identity_key, applied_at__isnull=False)
        .exclude(pk=item.pk)
        .exclude(target_id="")
        .order_by("-applied_at")
        .first()
    )
    return (prev.target_kind, prev.target_id) if prev else ("", "")


def _category(choice: str):
    from apps.catalog.models import Category
    from apps.catalog.slugs import unique_slug

    choice = (choice or "").strip()
    if not choice:
        return None
    if choice.startswith("new:"):
        name = structured.plain(choice[4:], structured.CATEGORY_MAX)
        if not name:
            return None
        existing = Category.objects.filter(name__de=name).first()
        if existing:
            return existing
        return Category.objects.create(name={"de": name}, slug=unique_slug(Category, name))
    return Category.objects.filter(pk=choice).first() if choice.isdigit() else None


def _meta(item):
    return {"import": {"run": str(item.run_id), "method": item.data.get("method", ""),
                       "ai_generated": item.ai_generated}}  # fmt: skip


def _save_product(item, data, category, target_id):
    from apps.catalog.models import Product

    price = data.get("price")
    product = Product.objects.filter(pk=target_id).first() if target_id else None
    created = product is None
    if created:
        product = Product(currency="EUR")
    product.name = {**(product.name or {}), settings.LANGUAGE_CODE: data["name"]}
    if data.get("description"):
        product.description = {
            **(product.description or {}),
            settings.LANGUAGE_CODE: data["description"],
        }
    product.base_price = Decimal(price) if price else Decimal("0")
    product.primary_action = "" if price else "request"
    product.list_price = None  # PAngV: импорт никогда не создаёт «statt»
    product.badge = ""
    if category is not None:
        product.category = category
    if created:
        product.sku = (data.get("sku") or "")[:100]
        product.gtin = (data.get("gtin") or "")[:14]
    product.external_url = (data.get("page_url") or "")[:500]
    product.metadata = {**(product.metadata or {}), **_meta(item)}
    product.is_active = True
    product.save()
    return product, created


def _save_service(item, data, target_id):
    from apps.booking.models import Service

    service = Service.objects.filter(pk=target_id).first() if target_id else None
    created = service is None
    if created:
        service = Service()
    service.name = data["name"][:120]
    if data.get("description"):
        service.description = data["description"]
    price = data.get("price")
    service.price_cents = int(Decimal(price) * 100) if price else 0
    if data.get("duration_min"):
        service.duration_minutes = max(5, min(int(data["duration_min"]), 600))
    service.external_url = (data.get("page_url") or "")[:500]
    service.is_active = True
    service.save()
    return service, created


def _merge(item, edits: dict) -> dict:
    data = dict(item.data)
    name = structured.plain(edits.get("name", data.get("name")), structured.NAME_MAX)
    if name:
        data["name"] = name
    data["description"] = structured.plain(
        edits.get("description", data.get("description")), structured.DESC_MAX
    )
    if "price" in edits:
        data["price"] = structured.price_of(edits.get("price")) if edits.get("price") else None
    return data


def apply_items(run, tenant, decisions: dict) -> ApplyResult:
    """decisions: {item_pk(str): {"name", "price", "description", "category"}} — только
    выбранные владельцем позиции. Остальные помечаются skipped."""
    from apps.core.modules import is_module_active

    result = ApplyResult()
    services_on = is_module_active(tenant, "booking")
    limit = free_limit(tenant)
    with transaction.atomic():
        _lock_schema()
        used = used_count()
        # Сначала отключения/подтверждения: место, освобождённое пропавшей позицией,
        # доступно новой в том же «Veröffentlichen» (лимит считается по живым).
        order = {"removed": 0, "unchanged": 1, "changed": 2, "new": 3}
        items = sorted(
            run.items.select_for_update().order_by("created_at"),
            key=lambda i: order.get(i.diff, 9),
        )
        for item in items:
            edits = decisions.get(str(item.pk))
            if edits is None:
                if item.decision == "pending":
                    item.decision = "skipped"
                    item.save(update_fields=["decision", "updated_at"])
                continue
            if item.diff in (item.DIFF_REMOVED, item.DIFF_UNCHANGED):
                _confirm(item, deactivate=item.diff == item.DIFF_REMOVED)
                if item.diff == item.DIFF_REMOVED:
                    used = used_count()
                result.updated += 1
                continue
            target_kind, target_id = item.target_kind, item.target_id
            if not target_id:
                target_kind, target_id = _previous_target(item)
            is_new_target = not target_id
            if is_new_target and limit is not None and used >= limit:
                result.over_limit += 1
                continue
            data = _merge(item, edits)
            try:
                with transaction.atomic():
                    if item.kind == "service" and services_on:
                        obj, created = _save_service(
                            item, data, target_id if target_kind == "service" else ""
                        )
                        kind = "service"
                    else:
                        category = _category(edits.get("category", ""))
                        obj, created = _save_product(
                            item, data, category, target_id if target_kind == "product" else ""
                        )
                        kind = "product"
            except Exception as exc:  # noqa: BLE001 — одна позиция не роняет остальные
                logger.warning("site import apply %s: %s", item.pk, type(exc).__name__)
                result.errors.append(item.pk)
                continue
            item.data = data
            item.decision = "accepted"
            item.target_kind, item.target_id = kind, str(obj.pk)
            item.applied_at = item.confirmed_at = timezone.now()
            item.save()
            if created:
                result.created += 1
                used += 1
            else:
                result.updated += 1
        run.status = run.STATUS_APPLIED
        run.save(update_fields=["status", "updated_at"])
        schema = connection.schema_name
        transaction.on_commit(lambda: _enqueue_images(schema, run.pk))
    return result


def _confirm(item, *, deactivate: bool) -> None:
    """«Bestätigen» без перезаписи каталога: без изменений — только отметка (шов Г3);
    пропавшая с сайта — позиция отключается (не удаляется: история заказов цела)."""
    from apps.booking.models import Service
    from apps.catalog.models import Product

    if not item.target_id:
        kind, target_id = _previous_target(item)
        item.target_kind, item.target_id = kind, target_id
    if deactivate and item.target_id:
        model = Service if item.target_kind == "service" else Product
        obj = model.objects.filter(pk=item.target_id).first()
        if obj is not None and obj.is_active:
            obj.is_active = False
            obj.save()  # через save: хук post_save снимет листинг из каталога города
    item.decision = "accepted"
    item.applied_at = item.confirmed_at = timezone.now()
    item.save()


def apply_profile(run, tenant, fields) -> list:
    """Профиль бизнеса: только выбранные поля; пустые поля тенанта — по умолчанию."""
    profile = run.profile or {}
    changed = []
    mapping = {"phone": "contact_phone", "address": "address",
               "opening_hours_structured": "opening_hours_structured"}  # fmt: skip
    for key in fields:
        value = profile.get(key)
        if not value or key not in PROFILE_FIELDS:
            continue
        if key == "description":
            config = dict(tenant.site_config or {})
            config["about_text"] = structured.plain(value, structured.DESC_MAX)
            tenant.site_config = config
            changed.append("site_config")
            continue
        attr = mapping[key]
        if attr == "contact_phone":
            value = structured.plain(value, 30)
        setattr(tenant, attr, value)
        changed.append(attr)
    if changed:
        tenant.save(update_fields=sorted(set(changed)))
    return changed


def _enqueue_images(schema, run_id):
    from ..tasks import fetch_site_import_images

    fetch_site_import_images.delay(
        dedupe_key=f"site-import-img:{schema}:{run_id}", schema_name=schema, run_id=str(run_id)
    )


def fetch_images(run, *, fetch=None) -> int:
    """По одному фото на применённую позицию без фото: safe_fetch → проверка Pillow →
    перекодировка в WEBP (срезает EXIF/полиглоты) → штатное хранилище товаров."""
    from django.core.files.base import ContentFile
    from PIL import Image

    from apps.booking.models import Service
    from apps.catalog.images import save_product_image
    from apps.catalog.models import Product
    from apps.core.ssrf import safe_fetch

    fetch = fetch or safe_fetch
    saved = 0
    for item in run.items.filter(applied_at__isnull=False).exclude(target_id=""):
        url = item.data.get("image_url") or ""
        if not url.startswith(("http://", "https://")):
            continue
        model = Product if item.target_kind == "product" else Service
        obj = model.objects.filter(pk=item.target_id).first()
        if obj is None or (obj.images if item.target_kind == "product" else obj.image):
            continue
        try:
            got = fetch(url, accept=IMAGE_TYPES, max_bytes=settings.SITE_IMPORT_MAX_IMAGE_BYTES)
            if not got.ok:
                continue
            with Image.open(io.BytesIO(got.body)) as img:
                img.verify()
            with Image.open(io.BytesIO(got.body)) as img:
                if img.width * img.height > MAX_PIXELS:  # «бомба» ниже порога Pillow
                    continue
                img = img.convert("RGB")
                img.thumbnail((2000, 2000))
                buf = io.BytesIO()
                img.save(buf, "WEBP", quality=85)
            upload = ContentFile(buf.getvalue(), name="import.webp")
            ref = save_product_image(upload, is_primary=True, folder="products")
        except Exception as exc:  # noqa: BLE001 — SsrfError/сеть/битое фото: позиция без фото
            logger.info("site import image skipped: %s", type(exc).__name__)
            continue
        if item.target_kind == "product":
            obj.images = [ref]
            obj.save(update_fields=["images", "updated_at"])
        else:
            obj.image = ref
            obj.save(update_fields=["image", "updated_at"])
        saved += 1
    return saved
