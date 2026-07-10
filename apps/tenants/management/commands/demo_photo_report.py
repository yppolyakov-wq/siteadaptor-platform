"""Инвентарь демо-фото: какие ключевые слова используют киты и какие уже закрыты
реальными файлами в static/demo/photos/ (решение владельца 2026-07-10 — CC0/AI-набор).

    python manage.py demo_photo_report            # всё
    python manage.py demo_photo_report --kit bakery
    python manage.py demo_photo_report --missing  # только незакрытые
"""

from django.core.management.base import BaseCommand

from apps.tenants import demo_kits
from apps.tenants.demo_images import _kw_slug, photo_static_name


def kit_keywords(kit) -> list[tuple[str, str]]:
    """[(keyword, где-используется)] по всем фото-полям кита (порядок стабильный)."""
    out: list[tuple[str, str]] = []

    def add(kw, where):
        if isinstance(kw, str) and kw.strip():
            out.append((kw, where))

    add(kit.hero_image_kw, "hero (1600×900)")
    for h in kit.heroes:
        add(h.get("image_kw"), "hero-слайд (1600×900)")
    for kw in kit.gallery_kw:
        add(kw, "галерея (800×600)")
    for pair in kit.before_after:
        add(pair[0], "до/после (800×600)")
        add(pair[1], "до/после (800×600)")
    for t in kit.team:
        add(t[2] if len(t) > 2 else "", "команда (400×400)")
    for t in kit.teachers:
        add(t[2] if len(t) > 2 else "", "преподаватель (400×400)")

    def add_category(entry):
        # (name, slug, items) ИЛИ (name, slug, items, children) — как _make_category
        for p in entry[2]:
            add(p.get("img"), "товар (800×600)")
        for child in entry[3] if len(entry) > 3 else []:
            add_category(child)

    for entry in kit.categories:
        add_category(entry)
    for s in kit.services:
        if isinstance(s, dict):
            add(s.get("img") or s.get("image_kw"), "услуга (800×600)")
    for u in kit.stay_units:
        if isinstance(u, dict):
            for kw in u.get("photos", []):
                add(kw, "номер (800×600)")
    for e in kit.events:
        if isinstance(e, dict):
            for kw in e.get("photos", []):
                add(kw, "событие (800×600)")
    for b in kit.blog_posts:
        add(b[3] if len(b) > 3 else "", "блог-обложка (800×450)")
    for cover in kit.archetype_covers.values():
        add(cover.get("hero_kw"), "обложка раздела (1600×900)")
        for kw in cover.get("gallery_kw", []):
            add(kw, "галерея раздела (800×600)")
    return out


class Command(BaseCommand):
    help = "Список ключевых слов демо-фото по китам + покрытие файлами static/demo/photos/."

    def add_arguments(self, parser):
        parser.add_argument("--kit", help="только один кит")
        parser.add_argument("--missing", action="store_true", help="только незакрытые ключи")

    def handle(self, *args, **options):
        keys = [options["kit"]] if options.get("kit") else list(demo_kits.KITS)
        total, covered = 0, 0
        seen: set[str] = set()
        for key in keys:
            kit = demo_kits.KITS.get(key)
            if kit is None:
                self.stderr.write(self.style.ERROR(f"Unbekannter Kit: {key}"))
                continue
            rows = []
            for kw, where in kit_keywords(kit):
                slug = _kw_slug(kw)
                if (key, slug) in seen:
                    continue
                seen.add((key, slug))
                total += 1
                photo = photo_static_name(kw)
                if photo:
                    covered += 1
                    if options["missing"]:
                        continue
                mark = f"✅ {photo}" if photo else f"⬜ {slug}.webp"
                rows.append(f"  {mark:44s} ← {kw}  ({where})")
            if rows:
                self.stdout.write(self.style.MIGRATE_HEADING(f"[{key}] {kit.label}"))
                self.stdout.write("\n".join(rows))
        pct = round(covered * 100 / total) if total else 0
        self.stdout.write(
            self.style.SUCCESS(
                f"\nПокрытие: {covered}/{total} ({pct} %). Файлы — в static/demo/photos/ "
                f"(правила — README.md там)."
            )
        )
