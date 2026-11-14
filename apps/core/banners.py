"""FB-29.2: библиотека баннеров — единственный писатель и читатель модели `Banner`.

Баннер несёт те же поля, что слайд прежнего `site_config["heroes"]`, и чистится тем же
нормализатором (`siteconfig.normalize_heroes`): безопасные схемы ссылок, цели из списка
целей меню, оформление из реестра. Место показа хранит выбор — список UUID; `resolve`
превращает его в слайды той же формы, что уже рисует витрина.
"""

from __future__ import annotations

import datetime
import logging
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
    проходит чистку, пропускается и считается. S7: собственные слайды блоков «Banner»
    переносятся тоже (`_import_blocks`) — все баннеры живут в библиотеке."""
    import copy
    import logging

    from django.db import IntegrityError, transaction

    from apps.core.models import Banner
    from apps.tenants import siteconfig
    from apps.tenants.models import Tenant

    report = {"created": 0, "skipped": 0}
    log = logging.getLogger(__name__)
    with transaction.atomic():
        fresh = Tenant.objects.select_for_update().filter(pk=tenant.pk).first()
        if fresh is None:
            return report
        raw = copy.deepcopy(fresh.site_config or {})
        changed = False
        current = raw.get("hero_banners") if isinstance(raw.get("hero_banners"), dict) else {}
        # Перенос слайдов главной — один раз: выбор уже есть (владельца или прошлого
        # переноса) либо записи переноса уже лежат в библиотеке — ничего не создаём. Иначе
        # повтор вернул бы баннеры, которые владелец удалил, и подменил бы правленые.
        heroes_done = bool(current.get("pick")) or bool(
            Banner.objects.filter(legacy_key__startswith=_LEGACY_PREFIX)
        )
        items = raw.get("heroes") if isinstance(raw.get("heroes"), list) else []
        pick = []
        # индекс — по СЫРОМУ списку: по нему же лежат переводы (`i18n[...]["heroes"][i]`);
        # слайд, который чистка отбрасывает, переносу не мешает
        for index, item in enumerate([] if heroes_done else items):
            cleaned = siteconfig.normalize_heroes([item])
            if not cleaned or len(pick) >= siteconfig._MAX_HEROES:
                continue
            try:
                with transaction.atomic():
                    banner = create(
                        cleaned[0], sort_order=index, legacy_key=f"{_LEGACY_PREFIX}{index}"
                    )
            except (ValueError, IntegrityError):
                log.warning(
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
            changed = True
        # S7: собственные слайды блоков «Banner» (главная и все страницы) — тоже записи
        # библиотеки; блок выбирает свою запись. Свои поля слайда в блоке остаются (откат).
        if _import_blocks(raw, fresh.schema_name, report):
            changed = True
        if changed:
            fresh.site_config = raw
            fresh.save(update_fields=["site_config", "updated_at"])
            tenant.site_config = raw
    return report


_BLOCK_PREFIX = "block:"
_OWN_SLIDE = ("url", "title", "text")


def _banner_blocks(config: dict):
    """Блоки «Banner» главной и всех страниц: (хост | "" у главной, блок)."""
    for item in config.get("sections") or []:
        if isinstance(item, dict) and item.get("id") and item.get("key") == "banner":
            yield "", item
    blocks = config.get("page_blocks") if isinstance(config.get("page_blocks"), dict) else {}
    for host, items in blocks.items():
        for item in items or []:
            if isinstance(item, dict) and item.get("id") and item.get("key") == "banner":
                yield host, item


def _localized_configs(raw: dict) -> dict:
    """Локализованный конфиг на каждую локаль с переводами — один раз на перенос."""
    import logging

    from apps.tenants import siteconfig

    out = {}
    for locale in [loc for loc in (raw.get("i18n") or {}) if isinstance(loc, str)]:
        try:
            out[locale] = siteconfig.localize(siteconfig.normalize(raw), locale)
        except Exception:  # noqa: BLE001 — перенос важнее перевода одной локали
            logging.getLogger(__name__).exception("banner import: locale %s unreadable", locale)
    return out


def _block_translations(shown_by_locale: dict, host: str, block_id: str, base: dict) -> dict:
    """Переводы своего слайда блока — из того же локализованного конфига, что рисует сайт."""
    out: dict = {overlay: {} for _base, overlay in _I18N_FIELDS}
    for locale, shown in shown_by_locale.items():
        items = (
            shown.get("sections") or []
            if not host
            else (shown.get("page_blocks") or {}).get(host) or []
        )
        data = next(
            (b.get("data") or {} for b in items if isinstance(b, dict) and b.get("id") == block_id),
            {},
        )
        for field, overlay in _I18N_FIELDS:
            value = data.get(field)
            if isinstance(value, str) and value.strip() and value.strip() != base.get(field, ""):
                out[overlay][locale] = value.strip()
    return out


def _import_blocks(raw: dict, schema_name: str, report: dict) -> bool:
    """Свой слайд блока «Banner» → запись библиотеки с ключом `block:<id>`; блок получает
    выбор. Один раз на блок (ключ уникален); блок с выбором владельца, блок-место и
    пустой блок не трогаются. Возвращает, менялся ли конфиг."""
    import logging

    from django.db import IntegrityError, transaction

    from apps.core.models import Banner

    done = set(
        Banner.objects.filter(legacy_key__startswith=_BLOCK_PREFIX).values_list(
            "legacy_key", flat=True
        )
    )
    changed = False
    shown_by_locale = _localized_configs(raw)  # до правок: переводы своих слайдов
    made: dict = {}  # ключ → запись этого прогона: один id блока на двух страницах
    for host, block in _banner_blocks(raw):
        data = block.get("data") if isinstance(block.get("data"), dict) else {}
        key = f"{_BLOCK_PREFIX}{block['id']}"
        if data.get("pick") or data.get("from_page") or len(key) > 80:
            continue
        if key in made and any(str(data.get(f) or "").strip() for f in _OWN_SLIDE):
            block["data"] = {**data, "pick": [made[key]]}  # тот же блок-копия — та же запись
            changed = True
            continue
        if key in done:
            continue
        if not any(str(data.get(f) or "").strip() for f in _OWN_SLIDE):
            continue
        slide = {**data, "image": data.get("url") or ""}
        try:
            with transaction.atomic():
                banner = create(slide, legacy_key=key)
        except (ValueError, IntegrityError):
            logging.getLogger(__name__).warning(
                "banner import: block %s of %s skipped (does not pass cleaning)",
                block["id"],
                schema_name,
            )
            report["skipped"] += 1
            continue
        base = {field: getattr(banner, field) for field, _overlay in _I18N_FIELDS}
        translations = _block_translations(shown_by_locale, host, block["id"], base)
        for overlay, value in translations.items():
            setattr(banner, overlay, value)
        banner.save()
        block["data"] = {**data, "pick": [str(banner.pk)]}
        made[key] = str(banner.pk)
        report["created"] += 1
        changed = True
    return changed


def undo_legacy(tenant) -> int:
    """Обратный ход переноса: перенесённые записи удаляются и уходят из выбора главной;
    баннеры, созданные владельцем, и его собственный выбор остаются. Возвращает число
    удалённых записей."""
    import copy

    from django.db import transaction
    from django.db.models import Q

    from apps.core.models import Banner
    from apps.tenants.models import Tenant

    with transaction.atomic():
        imported = list(
            Banner.objects.filter(
                Q(legacy_key__startswith=_LEGACY_PREFIX) | Q(legacy_key__startswith=_BLOCK_PREFIX)
            )
        )
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
                    if not holder["pick"] and holder is not raw.get("hero_banners"):
                        holder.pop("pick")  # блок снова показывает свой слайд
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


def pick_state(request, choice: dict, place_capable: bool = False) -> dict:
    """Панель «Seitenaufbau»: выбранные баннеры (в порядке владельца), предложения из
    библиотеки (с поиском), настройки слайдера. Удалённая запись в выборе не показывается;
    выключенная или вне срока — помечается: на сайте её сейчас нет."""
    import logging

    from django.db import DatabaseError

    choice = choice if isinstance(choice, dict) else {}
    try:
        return _pick_state(request, choice, place_capable)
    except DatabaseError:
        # S8: схема без таблицы баннеров (миграция ещё не дошла) — панель без выбора,
        # а не ошибка 500 на всём экране «Seitenaufbau».
        logging.getLogger(__name__).exception("banner picker: library unavailable")
        return {
            "entries": [], "offers": [], "lookup": "", "full": False, "total": 0,
            "auto": True, "interval": "6", "intervals": [str(n) for n in range(4, 13)],
            "arrows": False, "place_capable": False, "from_page": False, "unavailable": True,
        }  # fmt: skip


def _pick_state(request, choice: dict, place_capable: bool) -> dict:
    from django.db.models import Q
    from django.utils import timezone

    from apps.core.models import Banner
    from apps.tenants import siteconfig

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
        # S6: блок-место — «баннеры этой страницы» (только там, где у страницы есть объект)
        "place_capable": place_capable,
        "from_page": place_capable and bool(choice.get("from_page")),
    }


# ───────── FB-29.2c: «Wo zeigen» — баннер сам показывается на выбранных страницах ─────────

SHOW_ON_TYPES = ("category", "product", "service", "promotion", "stay", "event")
SHOW_ON_MAX = 50


def place_key(kind: str, obj) -> str:
    """Ключ места показа страницы объекта — то же значение, что у цели ссылки меню."""
    if kind not in SHOW_ON_TYPES or obj is None:
        return ""
    target = getattr(obj, "slug", "") if kind == "category" else getattr(obj, "pk", "")
    return f"{kind}:{target}" if target else ""


def _place_ok(value) -> bool:
    if not isinstance(value, str) or len(value) > 120 or ":" not in value:
        return False
    kind, target = value.split(":", 1)
    return kind in SHOW_ON_TYPES and bool(target.strip())


def set_show_on(banner, *, keep, add, allowed=None) -> list[str]:
    """Записать места показа баннера. `keep` — отмеченные в форме из уже сохранённых
    (оставить можно только то, что было); `add` — новые, только из `allowed` (цели,
    которые сайт сейчас открывает). Порядок — как добавляли, без повторов, с потолком."""
    current = [v for v in (banner.show_on or []) if _place_ok(v)]
    kept = set(keep or [])
    out = [v for v in current if v in kept]
    wanted = [v for v in (add or []) if _place_ok(v) and v not in out]
    wanted = wanted[: max(0, SHOW_ON_MAX - len(out))]  # ревью R1: предел — до запроса
    if allowed is None:
        allowed = set(place_labels(wanted))  # R1: допустимо то, что есть на сайте
    for value in wanted:
        if value in allowed and value not in out:
            out.append(value)
    out = out[:SHOW_ON_MAX]
    if out != (banner.show_on or []):
        banner.show_on = out
        banner.save(update_fields=["show_on", "updated_at"])
    return out


#: FB-29 R1: сколько страниц одного вида предлагает поиск «Wo zeigen».
PLACE_SEARCH_LIMIT = 30


def _place_sources() -> dict:
    """Вид места → (записи, которые сайт показывает, поле цели, подпись группы)."""
    from django.utils.translation import gettext_lazy as _

    from apps.booking.models import Service
    from apps.catalog.models import Category, Product
    from apps.events.models import Event
    from apps.promotions.models import Promotion
    from apps.stays.models import StayUnit

    return {
        "category": (Category.objects.filter(is_active=True), "slug", _("Kategorien")),
        "product": (Product.objects.filter(is_active=True), "pk", _("Produkte")),
        "service": (Service.objects.filter(is_active=True), "pk", _("Leistungen")),
        # ревью R1: черновики и завершённые акции не предлагаются
        "promotion": (Promotion.objects.filter(status="active"), "pk", _("Aktionen")),
        "stay": (StayUnit.objects.filter(is_active=True), "pk", _("Zimmer")),
        "event": (
            Event.objects.filter(status=Event.STATUS_PUBLISHED),
            "pk",
            _("Veranstaltungen"),
        ),
    }


def _place_label(obj) -> str:
    for attr in ("name_localized", "title_text", "title_localized", "name", "title"):
        value = getattr(obj, attr, None)
        if callable(value):
            try:
                value = value()
            except TypeError:  # метод с обязательным аргументом — берём следующее поле
                continue
        if isinstance(value, dict):
            value = value.get("de") or next(iter(value.values()), "")
        if value:
            return str(value)
    return str(obj)


def _targets(kind: str, values) -> list:
    """Цели вида в форме, пригодной для запроса (UUID либо слаг); мусор отбрасывается."""
    if kind == "category":
        return [v for v in values if v]
    out = []
    for value in values:
        try:
            out.append(uuid.UUID(str(value)))
        except (ValueError, TypeError):
            continue
    return out


def place_labels(values) -> dict:
    """Ключ места → «Группа: название» для существующих страниц (по запросу на вид)."""
    from django.db import DatabaseError

    by_kind: dict = {}
    for value in values or []:
        if _place_ok(value):
            kind, target = value.split(":", 1)
            by_kind.setdefault(kind, []).append(target)
    out: dict = {}
    sources = _place_sources()
    for kind, targets in by_kind.items():
        base, field, group = sources[kind]
        try:
            rows = base.filter(**{f"{field}__in": _targets(kind, targets)})
            for obj in rows:
                out[f"{kind}:{getattr(obj, field)}"] = f"{group}: {_place_label(obj)}"
        except DatabaseError:
            logging.getLogger(__name__).exception("banner places: labels failed for %s", kind)
    return out


def place_exists(value) -> bool:
    """Есть ли такая страница на сайте — проверка нового места по базе (а не по списку
    целей меню с его потолком)."""
    return _place_ok(value) and value in place_labels([value])


def place_search(query: str = "", exclude=()) -> list[dict]:
    """Страницы для «Seite hinzufügen»: [{label, items: [{value, label}]}]. С запросом —
    поиск по названию во всех записях вида; без запроса — начало списка."""
    from django.db import DatabaseError

    query = (query or "").strip()[:80].lower()
    skip = set(exclude or ())
    groups = []
    for kind, (base, field, group) in _place_sources().items():
        items = []
        try:
            rows = base.order_by("pk")
            # Названия — JSON по языкам (или обычная строка): ищем по подписи в Python,
            # ограничив выборку, — у малого бизнеса записей сотни, не миллионы.
            for obj in rows[:2000] if query else rows[: PLACE_SEARCH_LIMIT * 2]:
                value = f"{kind}:{getattr(obj, field)}"
                label = _place_label(obj)
                if value in skip or (query and query not in label.lower()):
                    continue
                items.append({"value": value, "label": label})
                if len(items) >= PLACE_SEARCH_LIMIT:
                    break
        except DatabaseError:
            logging.getLogger(__name__).exception("banner places: search failed for %s", kind)
        if items:
            groups.append({"label": str(group), "items": items})
    return groups


def show_on_rows(tenant, banner) -> list[dict]:
    """Сохранённые места с названиями (место, которого сайт сейчас не открывает, —
    с пометкой: запись выключена или удалена)."""
    values = [v for v in (banner.show_on or []) if _place_ok(v)]
    labels = place_labels(values)
    return [{"value": v, "label": labels.get(v, ""), "missing": v not in labels} for v in values]


def rename_place(old: str, new: str) -> int:
    """Адрес страницы сменился (категория) — место переезжает; пустой `new` — убрать."""
    from apps.core.models import Banner

    changed = 0
    for banner in Banner.objects.filter(show_on__contains=[old]):
        places = [new if v == old else v for v in banner.show_on]
        banner.show_on = [v for i, v in enumerate(places) if v and v not in places[:i]]
        banner.save(update_fields=["show_on", "updated_at"])
        changed += 1
    return changed


def picks_for_place(key: str) -> list[str]:
    """Баннеры места показа по порядку библиотеки (отбор по сроку и «включён» делает
    `resolve`). Ошибка базы (нет таблицы до миграции) — пусто: страница важнее баннера."""
    import logging

    from django.db import DatabaseError

    from apps.core.models import Banner

    if not key:
        return []
    try:
        rows = Banner.objects.filter(show_on__contains=[key], is_active=True)
        return [
            str(pk)
            for pk in rows.order_by("sort_order", "created_at").values_list("pk", flat=True)[
                :MAX_SLIDES
            ]
        ]
    except DatabaseError:
        logging.getLogger(__name__).exception("banner places: lookup failed for %s", key)
        return []


def page_place_key(context) -> str:
    """Ключ места показа текущей страницы витрины — по объекту в контексте шаблона."""
    for kind, name in (
        ("product", "product"),
        ("service", "service"),
        ("promotion", "promotion"),
        ("stay", "unit"),
        ("event", "event"),
        ("category", "current_category"),
    ):
        obj = context.get(name)
        if obj is not None and getattr(obj, "pk", None):
            return place_key(kind, obj)
    return ""


def place_block_present(config, hosts) -> bool:
    """Стоит ли в структуре этих хостов включённый блок «Banner» с источником «баннеры
    этой страницы» — тогда место баннеров задаёт он, а место по умолчанию молчит."""
    blocks = (config or {}).get("page_blocks") or {}
    for host in hosts:
        for block in blocks.get(host) or []:
            if (
                isinstance(block, dict)
                and block.get("key") == "banner"
                and block.get("enabled", True)
                and isinstance(block.get("data"), dict)
                and block["data"].get("from_page")
            ):
                return True
    return False
