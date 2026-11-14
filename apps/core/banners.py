"""FB-29.2: библиотека баннеров — единственный писатель и читатель модели `Banner`.

Баннер несёт те же поля, что слайд прежнего `site_config["heroes"]`, и чистится тем же
нормализатором (`siteconfig.normalize_heroes`): безопасные схемы ссылок, цели из списка
целей меню, оформление из реестра. Место показа хранит выбор — список UUID; `resolve`
превращает его в слайды той же формы, что уже рисует витрина.
"""

from __future__ import annotations

import datetime
import re
import uuid

from django.utils import timezone

#: Поля слайда, которые баннер хранит строками как есть.
_TEXT_FIELDS = ("title", "text", "button_label", "button_url", "link")
_STYLE_FIELDS = ("align", "overlay", "tone")
_I18N_FIELDS = (
    ("title", "title_i18n"),
    ("text", "text_i18n"),
    ("button_label", "button_label_i18n"),
)


#: Сколько баннеров показывает одно место (слайдер); лишнее в выборе отбрасывается.
MAX_SLIDES = 10


def _day(value):
    """Дата срока. Пусто — None; мусор — ValueError (молча превратить битую дату в
    «показывать всегда» нельзя: баннер вне срока вышел бы на сайт)."""
    if value in (None, ""):
        return None
    if isinstance(value, datetime.date):
        return value
    try:
        return datetime.date.fromisoformat(str(value))
    except ValueError as exc:
        raise ValueError("date") from exc


#: Адрес фото баннера: свой путь или http(s), без пробелов, кавычек, скобок и «\\».
_SAFE_IMAGE_URL = re.compile(r"^(?:https?://|/(?!/))[^\s'\"()\\<>]*$")


def clean_fields(raw: dict) -> dict:
    """Сырые поля формы/переноса → значения модели. Та же санитизация, что у слайда
    баннера главной; пустой баннер (ни фото, ни заголовка, ни текста) — ValueError."""
    from apps.tenants import siteconfig

    raw = raw if isinstance(raw, dict) else {}
    image = raw.get("image") if isinstance(raw.get("image"), dict) else {}
    url = str(image.get("url") or "") if image else str(raw.get("image") or "")
    if not _SAFE_IMAGE_URL.match(url):
        url = ""  # адрес попадает в `style="background-image:url('…')"` — без кавычек и скобок
    starts, ends = _day(raw.get("starts")), _day(raw.get("ends"))
    slide = {
        **{k: raw.get(k) for k in (*_TEXT_FIELDS, *_STYLE_FIELDS)},
        "image": url,
        "click_all": bool(raw.get("click_all")),
    }
    cleaned = siteconfig.normalize_heroes([slide])
    if not cleaned:
        raise ValueError("empty banner")
    slide = cleaned[0]
    ref = {"url": slide["image"]} if slide["image"] else {}
    if ref and image.get("path"):
        ref["path"] = str(image["path"])
    if ref and image.get("alt"):
        alt = image["alt"]  # FileRef хранит alt словарём по языкам; у ручного ввода — строка
        ref["alt"] = alt if isinstance(alt, dict) else str(alt)[:300]
    out = {k: slide.get(k, "") for k in (*_TEXT_FIELDS, *_STYLE_FIELDS)}
    out.update(image=ref, click_all=bool(slide.get("click_all")), starts=starts, ends=ends)
    # «включён» меняется, только когда поле прислано: частичная правка не включает
    # выключенный баннер обратно
    if "is_active" in raw:
        out["is_active"] = bool(raw["is_active"])
    return out


def create(raw: dict, *, sort_order: int | None = None, legacy_key: str = ""):
    """Новый баннер. Порядок и ключ переноса задаёт только код (не форма владельца)."""
    from apps.core.models import Banner

    fields = clean_fields(raw)
    if sort_order is not None:
        fields["sort_order"] = max(0, int(sort_order))
    if legacy_key:
        if len(legacy_key) > 80:
            raise ValueError("legacy_key")  # обрезка склеила бы два разных слайда
        fields["legacy_key"] = legacy_key
    return Banner.objects.create(**fields)


def update(banner, raw: dict):
    """Правка баннера. Сменился текст основного языка — его переводы снимаются: иначе
    сайт на других языках показывал бы прежний текст."""
    fields = clean_fields(raw)
    for base, overlay in _I18N_FIELDS:
        if fields.get(base, "") != getattr(banner, base):
            setattr(banner, overlay, {})
    for field, value in fields.items():
        setattr(banner, field, value)
    banner.save()
    return banner


def to_slide(banner, locale: str | None = None) -> dict:
    """Запись → слайд той формы, что рисует витрина (`normalize_heroes`), с переводом."""
    slide = {
        "image": (banner.image or {}).get("url", ""),
        "button_url": banner.button_url,
    }
    for base, overlay in _I18N_FIELDS:
        slide[base] = banner.get_overlay(base, overlay, locale)
    if banner.link:
        slide["link"] = banner.link
    for key in _STYLE_FIELDS:
        if getattr(banner, key):
            slide[key] = getattr(banner, key)
    if banner.starts:
        slide["starts"] = banner.starts.isoformat()
    if banner.ends:
        slide["ends"] = banner.ends.isoformat()
    if banner.click_all:
        slide["click_all"] = True
    if (banner.image or {}).get("alt"):
        slide["alt"] = banner.image["alt"]
    slide["id"] = str(banner.pk)
    return slide


def clean_pick(pick) -> list[str]:
    """Выбор места показа → UUID-строки без мусора и повторов, в порядке владельца."""
    out: list[str] = []
    for value in pick if isinstance(pick, (list, tuple)) else []:
        try:
            key = str(uuid.UUID(str(value)))
        except (ValueError, AttributeError, TypeError):
            continue
        if key not in out:
            out.append(key)
        if len(out) >= MAX_SLIDES:
            break
    return out


def resolve(pick, legacy=None, locale: str | None = None) -> list[dict]:
    """Слайды места показа. Есть выбор — записи, активные СЕГОДНЯ, в порядке выбора
    (удалённая или выключенная запись просто выпадает). Выбора нет — прежние слайды
    `legacy` как есть (их фильтрует и дополняет ссылкой тег витрины)."""
    from apps.core.models import Banner

    keys = clean_pick(pick)
    if not keys:
        return list(legacy or [])
    today = timezone.localdate()
    found = {str(b.pk): b for b in Banner.objects.filter(pk__in=keys, is_active=True)}
    out = []
    for key in keys:
        banner = found.get(key)
        if banner is None:
            continue
        if banner.starts and banner.starts > today:
            continue
        if banner.ends and banner.ends < today:
            continue
        out.append(to_slide(banner, locale))
    return out


def _picks(config: dict):
    """Все места, где хранится выбор баннеров: (подпись места, словарь с ключом `pick`)."""
    hero = config.get("hero_banners")
    if isinstance(hero, dict):
        yield "home", hero
    for item in config.get("sections") or []:
        if isinstance(item, dict) and isinstance(item.get("data"), dict) and item.get("id"):
            yield "home", item["data"]
    blocks = config.get("page_blocks") if isinstance(config.get("page_blocks"), dict) else {}
    for host, items in blocks.items():
        for item in items or []:
            if isinstance(item, dict) and isinstance(item.get("data"), dict):
                yield host, item["data"]


def places(tenant, banner) -> list[str]:
    """Где баннер выбран: коды мест («home», хост страницы) без повторов."""
    key = str(banner.pk)
    out: list[str] = []
    for place, holder in _picks(tenant.site_config or {}):
        if key in (holder.get("pick") or []) and place not in out:
            out.append(place)
    return out


def delete(tenant, banner) -> None:
    """Удалить баннер и убрать его из выбора всех мест показа — иначе в настройках сайта
    копились бы ссылки на несуществующую запись. Точечная запись под блокировкой строки."""
    import copy

    from django.db import transaction

    from apps.tenants.models import Tenant

    key = str(banner.pk)
    with transaction.atomic():
        fresh = Tenant.objects.select_for_update().filter(pk=tenant.pk).first()
        if fresh is not None:
            config = copy.deepcopy(fresh.site_config or {})
            changed = False
            for _place, holder in _picks(config):
                pick = holder.get("pick")
                if isinstance(pick, list) and key in pick:
                    holder["pick"] = [p for p in pick if p != key]
                    changed = True
            if changed:
                fresh.site_config = config
                fresh.save(update_fields=["site_config", "updated_at"])
                tenant.site_config = config
        banner.delete()


def first_image(config: dict) -> str:
    """Фото первого баннера главной — запасное фото шапок страниц и композиций. Выбраны
    баннеры из библиотеки — первый показываемый сегодня; иначе первый прежний слайд.
    Ошибка базы не роняет страницу: фото просто нет."""
    import logging

    from django.db import DatabaseError, transaction

    config = config or {}
    pick = (config.get("hero_banners") or {}).get("pick")
    if pick:
        try:
            with transaction.atomic():
                slides = resolve(pick)
        except DatabaseError:
            logging.getLogger(__name__).exception("banners: first image lookup failed")
            slides = []
        return slides[0]["image"] if slides else ""
    heroes = config.get("heroes") or []
    first = heroes[0] if heroes and isinstance(heroes[0], dict) else {}
    return first.get("image", "") or ""


# ───────── перенос прежних слайдов (`site_config["heroes"]`) в библиотеку ─────────

_LEGACY_PREFIX = "heroes:"


def _hero_translations(config: dict, index: int) -> dict:
    """Переводы слайда №index из позиционного оверлея `i18n[<язык>]["heroes"]`."""
    out: dict = {overlay: {} for _base, overlay in _I18N_FIELDS}
    for locale, layer in (config.get("i18n") or {}).items():
        slides = layer.get("heroes") if isinstance(layer, dict) else None
        slide = slides[index] if isinstance(slides, list) and index < len(slides) else None
        if not isinstance(slide, dict):
            continue
        for base, overlay in _I18N_FIELDS:
            if isinstance(slide.get(base), str) and slide[base].strip():
                out[overlay][locale] = slide[base].strip()
    return out


def import_legacy(tenant) -> dict:
    """Слайды баннера главной → записи библиотеки; главная начинает показывать их по
    выбору. Повторяемо (ключ `heroes:<i>`), прежние слайды в настройках остаются — для
    отката. Выбор, который владелец уже сделал сам, не трогается. Слайд, который не
    проходит чистку, пропускается и считается. Блоки «Banner» не переносятся: у блока
    остаётся свой слайд, пока владелец не выберет баннер из библиотеки."""
    import copy
    import logging

    from django.db import IntegrityError, transaction

    from apps.core.models import Banner
    from apps.tenants import siteconfig
    from apps.tenants.models import Tenant

    report = {"created": 0, "skipped": 0}
    with transaction.atomic():
        fresh = Tenant.objects.select_for_update().filter(pk=tenant.pk).first()
        if fresh is None:
            return report
        raw = copy.deepcopy(fresh.site_config or {})
        current = raw.get("hero_banners") if isinstance(raw.get("hero_banners"), dict) else {}
        # Перенос — один раз: выбор уже есть (владельца или прошлого переноса) либо записи
        # переноса уже лежат в библиотеке — ничего не создаём. Иначе повтор вернул бы
        # баннеры, которые владелец удалил, и подменил бы правленые записи прежними.
        if current.get("pick") or Banner.objects.filter(legacy_key__startswith=_LEGACY_PREFIX):
            return report
        items = raw.get("heroes") if isinstance(raw.get("heroes"), list) else []
        pick = []
        # индекс — по СЫРОМУ списку: по нему же лежат переводы (`i18n[...]["heroes"][i]`);
        # слайд, который чистка отбрасывает, переносу не мешает
        for index, item in enumerate(items):
            cleaned = siteconfig.normalize_heroes([item])
            if not cleaned or len(pick) >= siteconfig._MAX_HEROES:
                continue
            try:
                with transaction.atomic():
                    banner = create(
                        cleaned[0], sort_order=index, legacy_key=f"{_LEGACY_PREFIX}{index}"
                    )
            except (ValueError, IntegrityError):
                logging.getLogger(__name__).warning(
                    "banner import: slide %s of %s skipped (does not pass cleaning)",
                    index,
                    fresh.schema_name,
                )
                report["skipped"] += 1
                continue
            for overlay, value in _hero_translations(raw, index).items():
                setattr(banner, overlay, value)
            banner.save()
            report["created"] += 1
            pick.append(str(banner.pk))
        if pick:
            raw["hero_banners"] = {**current, "pick": pick}
            fresh.site_config = raw
            fresh.save(update_fields=["site_config", "updated_at"])
            tenant.site_config = raw
    return report


def undo_legacy(tenant) -> int:
    """Обратный ход переноса: перенесённые записи удаляются и уходят из выбора главной;
    баннеры, созданные владельцем, и его собственный выбор остаются. Возвращает число
    удалённых записей."""
    import copy

    from django.db import transaction

    from apps.core.models import Banner
    from apps.tenants.models import Tenant

    with transaction.atomic():
        imported = list(Banner.objects.filter(legacy_key__startswith=_LEGACY_PREFIX))
        keys = {str(b.pk) for b in imported}
        fresh = Tenant.objects.select_for_update().filter(pk=tenant.pk).first()
        if fresh is not None and keys:
            raw = copy.deepcopy(fresh.site_config or {})
            changed = False
            for _place, holder in _picks(raw):
                pick = holder.get("pick")
                if isinstance(pick, list) and keys & set(pick):
                    holder["pick"] = [p for p in pick if p not in keys]
                    changed = True
            if isinstance(raw.get("hero_banners"), dict) and not raw["hero_banners"].get("pick"):
                raw["hero_banners"].pop("pick", None)
                if not raw["hero_banners"]:
                    raw.pop("hero_banners")
                changed = True
            if changed:
                fresh.site_config = raw
                fresh.save(update_fields=["site_config", "updated_at"])
                tenant.site_config = raw
        for banner in imported:
            banner.delete()
    return len(imported)


def pick_state(request, choice: dict) -> dict:
    """Панель «Seitenaufbau»: выбранные баннеры (в порядке владельца), предложения из
    библиотеки (с поиском), настройки слайдера. Удалённая запись в выборе не показывается;
    выключенная или вне срока — помечается: на сайте её сейчас нет."""
    from django.db.models import Q
    from django.utils import timezone

    from apps.core.models import Banner
    from apps.tenants import siteconfig

    choice = choice if isinstance(choice, dict) else {}
    pick = clean_pick(choice.get("pick"))
    lookup = (request.GET.get("lookup") or "").strip()[:80]
    today = timezone.localdate()
    found = {str(b.pk): b for b in Banner.objects.filter(pk__in=pick)}

    def row(banner):
        live = banner.is_active and not (
            (banner.starts and banner.starts > today) or (banner.ends and banner.ends < today)
        )
        return {
            "pk": str(banner.pk),
            "label": banner.title or banner.text[:60],
            "image": (banner.image or {}).get("url", ""),
            "live": live,
        }

    entries = [row(found[key]) for key in pick if key in found]
    full = len(entries) >= siteconfig.BANNER_PICK_MAX
    offers = []
    if not full:
        rows = Banner.objects.exclude(pk__in=pick)
        if lookup:
            rows = rows.filter(Q(title__icontains=lookup) | Q(text__icontains=lookup))
        offers = [row(b) for b in rows[:24]]
    return {
        "entries": entries,
        "offers": offers,
        "lookup": lookup,
        "full": full,
        "total": Banner.objects.count(),
        "auto": choice.get("auto") is not False,
        "interval": str(choice.get("interval") or 6),
        "intervals": [str(n) for n in range(4, 13)],
        "arrows": bool(choice.get("arrows")),
    }
