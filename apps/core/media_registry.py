"""CM-4: карта мест хранения FileRef-медиа + операции реестра.

Единственный источник знания «где лежат FileRef-копии» — используется
backfill-командой, write-back'ом alt и проверкой занятости перед удалением.
При добавлении НОВОГО места хранения медиа — дописать сюда (рассинхрон
всплывёт тестом test_media_registry_map_covers_known_fields).

Demo-FileRef (SVG-вьюха /medien/demo.svg, без "path") реестром игнорируются.
jobs.JobPhoto (ImageField) — отдельная система, вне CM-4.
"""

from django.core.files.storage import default_storage


def _iter_gallery_fields():
    """(queryset, поле-СПИСОК FileRef) — галереи сущностей."""
    from apps.catalog.models import Product
    from apps.events.models import Event
    from apps.promotions.models import Promotion
    from apps.stays.models import StayUnit

    yield Product.objects.all(), "images"
    yield Promotion.objects.all(), "images"
    yield Event.objects.all(), "images"
    yield StayUnit.objects.all(), "images"


def _iter_single_fields():
    """(queryset, поле-ОДИНОЧНЫЙ FileRef-dict)."""
    from apps.booking.models import Resource
    from apps.core.models import Extra
    from apps.events.models import BlogPost
    from apps.publishing.models import SocialPost

    yield BlogPost.objects.all(), "cover"
    yield SocialPost.objects.all(), "image"
    yield Extra.objects.all(), "image"
    yield Resource.objects.all(), "photo"


def _service_images():
    """Service.image — шим dict|list (UC4-3): нормализуем к списку."""
    from apps.booking.models import Service

    for svc in Service.objects.all():
        yield svc, "image", list(svc.images)


def _site_config_refs(tenant):
    """FileRef-списки внутри site_config (галерея главной + галереи архетипов)."""
    cfg = tenant.site_config or {}
    refs = list(cfg.get("gallery") or [])
    for arch in (cfg.get("archetypes") or {}).values():
        if isinstance(arch, dict):
            refs.extend(arch.get("gallery") or [])
    return [r for r in refs if isinstance(r, dict)]


def iter_all_refs(tenant=None):
    """Все FileRef-dict'ы тенанта (включая копии) — генератор.

    tenant нужен только для site_config-галерей (None → пропустить их)."""
    for qs, field in _iter_gallery_fields():
        for obj in qs:
            for ref in getattr(obj, field) or []:
                if isinstance(ref, dict):
                    yield ref
    for qs, field in _iter_single_fields():
        for obj in qs:
            ref = getattr(obj, field)
            if isinstance(ref, dict) and ref:
                yield ref
    for _svc, _field, refs in _service_images():
        yield from refs
    if tenant is not None:
        yield from _site_config_refs(tenant)


def used_paths(tenant=None) -> set:
    """Множество storage-путей, на которые ссылается хоть одна сущность."""
    return {ref.get("path") for ref in iter_all_refs(tenant) if ref.get("path")}


def backfill(tenant=None) -> int:
    """Идемпотентный засев реестра из существующих FileRef-копий (unique path).

    Возвращает число созданных записей. Вызывать в схеме тенанта."""
    from apps.core.models import MediaAsset

    created = 0
    seen = set()
    for ref in iter_all_refs(tenant):
        path = ref.get("path")
        if not path or path in seen:
            continue
        seen.add(path)
        _, was_created = MediaAsset.objects.get_or_create(
            path=path,
            defaults={
                "url": ref.get("url", ""),
                "folder": path.split("/", 1)[0] if "/" in path else "",
                "mime_type": ref.get("mime_type", ""),
                "size": int(ref.get("size") or 0),
                "alt": ref.get("alt") or {},
            },
        )
        created += int(was_created)
    return created


def write_back_alt(path: str, alt: dict, tenant=None) -> int:
    """Обновить alt во ВСЕХ FileRef-копиях с данным path (+ site_config тенанта).

    Возвращает число обновлённых объектов. Источник рендера — FileRef, поэтому
    редактор alt на «Medien» обязан прописать его в копии."""
    updated = 0
    for qs, field in _iter_gallery_fields():
        for obj in qs:
            refs = getattr(obj, field) or []
            if _apply_alt(refs, path, alt):
                obj.save(update_fields=[field, "updated_at"])
                updated += 1
    for qs, field in _iter_single_fields():
        for obj in qs:
            ref = getattr(obj, field)
            if isinstance(ref, dict) and ref.get("path") == path:
                ref["alt"] = dict(alt)
                setattr(obj, field, ref)
                obj.save(update_fields=[field, "updated_at"])
                updated += 1
    for svc, field, refs in _service_images():
        if _apply_alt(refs, path, alt):
            svc.image = refs  # шим: запись всегда списком
            svc.save(update_fields=[field, "updated_at"])
            updated += 1
    if tenant is not None:
        cfg = tenant.site_config or {}
        changed = _apply_alt(cfg.get("gallery") or [], path, alt)
        for arch in (cfg.get("archetypes") or {}).values():
            if isinstance(arch, dict) and _apply_alt(arch.get("gallery") or [], path, alt):
                changed = True
        if changed:
            tenant.site_config = cfg
            tenant.save(update_fields=["site_config"])
            updated += 1
    return updated


def _apply_alt(refs: list, path: str, alt: dict) -> bool:
    changed = False
    for ref in refs:
        if isinstance(ref, dict) and ref.get("path") == path:
            ref["alt"] = dict(alt)
            changed = True
    return changed


def delete_unused(asset, tenant=None) -> bool:
    """Удалить файл+запись, ТОЛЬКО если path нигде не используется (защита от
    битых ссылок). True — удалено."""
    if asset.path in used_paths(tenant):
        return False
    if asset.path and default_storage.exists(asset.path):
        default_storage.delete(asset.path)
    asset.delete()
    return True
