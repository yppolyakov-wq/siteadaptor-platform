"""NT-A2: центр подписок «Benachrichtigungen auswählen» — выбор галочками.

План — docs/nt-notification-preferences-plan-2026-11-10.md §2 A2. Житель отмечает разделы,
категории, районы, признаки (vegan, halal…) и марки; сохранение — одна транзакция под
блокировкой строки жителя, diff только по видам центра (`follow.CENTER_KINDS`) этого канала
и города: подписки на компании и поиски центр не трогает. Правила (Р-NT2/Р-NT3):

* отмеченный раздел покрывает свои категории (категории под ним не храним);
* отмечены все категории раздела — сохраняется один раздел;
* лимит считается по ИТОГОВОМУ числу подписок жителя; сверх лимита не пишется ничего;
* `mode="add"` (подтверждение из письма) только добавляет — чужие подписки того же адреса
  (поставленные с другого устройства) подтверждение не стирает.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from django.db import transaction
from django.db.models import Count
from django.utils import timezone

from apps.core import city_categories as cc
from apps.core import districts

from . import follow
from .models import FollowSubscription, PortalUser

MAX_BRANDS = 30  # марок в блоке «Marken» (самые частые в каталоге области)

KIND_FIELD = {
    FollowSubscription.TARGET_SECTION: "sections",
    FollowSubscription.TARGET_CATEGORY: "categories",
    FollowSubscription.TARGET_DISTRICT: "districts",
    FollowSubscription.TARGET_TAG: "tags",
    FollowSubscription.TARGET_BRAND: "brands",
}
FIELD_KIND = {v: k for k, v in KIND_FIELD.items()}
#: короткие ключи DOI-токена v2 (сжатый токен в ссылке письма)
TOKEN_KEYS = {"sections": "s", "categories": "g", "districts": "d", "tags": "t", "brands": "b"}


@dataclass
class Selection:
    sections: set = field(default_factory=set)
    categories: set = field(default_factory=set)
    districts: set = field(default_factory=set)
    tags: set = field(default_factory=set)
    brands: set = field(default_factory=set)

    def targets(self, city: str) -> set[tuple[str, str]]:
        return {
            (FIELD_KIND[name], key) for name in KIND_FIELD.values() for key in getattr(self, name)
        }

    def __len__(self) -> int:
        return sum(len(getattr(self, name)) for name in KIND_FIELD.values())

    def as_token(self) -> dict:
        return {TOKEN_KEYS[name]: sorted(getattr(self, name)) for name in KIND_FIELD.values()}

    @classmethod
    def from_token(cls, data) -> Selection:
        data = data if isinstance(data, dict) else {}
        out = cls()
        for name, short in TOKEN_KEYS.items():
            values = data.get(short) or []
            if isinstance(values, list):
                getattr(out, name).update(str(v) for v in values if isinstance(v, str))
        return out


# --- что показать -------------------------------------------------------------------------


def city_of(portal) -> str:
    return districts.city_label(getattr(portal, "city", "") or "") if portal else ""


def _theme_categories(portal) -> set[str]:
    from . import portal_scope

    return set(portal_scope.theme_category_keys(portal)) if portal is not None else set()


def tree(portal) -> list[dict]:
    """Разделы → категории справочника. Тематический портал — только его разделы/категории.
    Пустые категории тоже показываем: подписка «сообщить, когда появится» — смысл центра."""
    allowed = _theme_categories(portal)
    out = []
    for section in cc.SECTIONS:
        cats = [c for c in cc.CATEGORIES if c.section == section.key]
        if allowed:
            cats = [c for c in cats if c.key in allowed]
            if not cats:
                continue
        out.append({"section": section, "categories": cats, "whole": not allowed})
    return out


def tags(portal) -> list[tuple[str, str]]:
    from . import portal_scope

    theme = set(portal_scope.theme_tags(portal)) if portal is not None else set()
    return [(key, str(label)) for key, label in cc.TAGS if not theme or key in theme]


def brands(portal) -> list[tuple[str, str]]:
    """Марки, которые реально есть в каталоге области (самые частые первыми), [(ключ, подпись)].
    Пока марок нет — пусто, блок не показывается."""
    from . import portal_scope

    rows = (
        portal_scope.pool(portal, include_demo=False)
        .exclude(brand="")
        .values("brand")
        .annotate(n=Count("pk"))
        .order_by("-n", "brand")[: MAX_BRANDS * 2]
    )
    out: dict[str, str] = {}
    for row in rows:
        key = follow.brand_key(row["brand"])
        if key and key not in out:
            out[key] = row["brand"]
        if len(out) >= MAX_BRANDS:
            break
    return sorted(out.items(), key=lambda kv: kv[1].casefold())


def district_choices(portal) -> list[tuple[str, str]]:
    city = city_of(portal)
    return districts.choices_for(city) if city else []


def state(user: PortalUser | None, city: str, channel: str) -> Selection:
    out = Selection()
    if user is None:
        return out
    for kind, key in FollowSubscription.objects.filter(
        user=user, channel=channel, city=city, target_kind__in=follow.CENTER_KINDS
    ).values_list("target_kind", "target_key"):
        getattr(out, KIND_FIELD[kind]).add(key)
    return out


# --- нормализация -------------------------------------------------------------------------


def normalize(raw: Selection, portal) -> Selection:
    """Только ключи реестров области; раздел покрывает свои категории; полный набор
    категорий раздела сворачивается в раздел; чужое теме портала отбрасывается."""
    city = city_of(portal)
    allowed = _theme_categories(portal)
    tag_keys = {k for k, _l in tags(portal)}
    sections = {k for k in raw.sections if cc.section(k)}
    if allowed:  # раздел тематического портала — только целиком внутри темы
        sections = {
            s for s in sections if all(c.key in allowed for c in cc.CATEGORIES if c.section == s)
        }
    categories = {
        k
        for k in raw.categories
        if cc.category(k) is not None and cc.section(k) is None and (not allowed or k in allowed)
    }
    for section in cc.SECTIONS:
        members = {c.key for c in cc.CATEGORIES if c.section == section.key}
        if members and members <= categories and (not allowed or members <= allowed):
            sections.add(section.key)
    categories = {k for k in categories if cc.category(k).section not in sections}
    district_keys = set()
    for value in raw.districts:
        slug = districts.normalize(city, value) if city else ""
        if slug:
            district_keys.add(slug)
    brand_keys = {follow.brand_key(b) for b in raw.brands} - {""}
    return Selection(
        sections=sections,
        categories=categories,
        districts=district_keys,
        tags={k for k in raw.tags if k in tag_keys},
        brands=brand_keys,
    )


def from_post(data, portal) -> Selection:
    def values(name):
        return [str(v)[:100] for v in data.getlist(name)][:200]

    raw = Selection(
        sections=set(values("bereich")),
        categories=set(values("kategorie")),
        districts=set(values("stadtteil")),
        tags=set(values("merkmal")),
        brands=set(values("marke")),
    )
    return normalize(raw, portal)


# --- запись -------------------------------------------------------------------------------


@dataclass
class Result:
    added: int = 0
    removed: int = 0


def apply(
    user: PortalUser,
    desired: Selection,
    *,
    frequency: str,
    portal,
    source_host: str = "",
    channel: str = FollowSubscription.CHANNEL_EMAIL,
    mode: str = "set",
    now=None,
) -> Result:
    """Применить выбор. `set` — привести виды центра к выбору; `add` — только добавить.
    Лимит по итоговому числу — `FollowLimitReached`, в базе ничего не меняется."""
    now = now or timezone.now()
    city = city_of(portal)
    want = desired.targets(city)
    result = Result()
    with transaction.atomic():
        PortalUser.objects.select_for_update().filter(pk=user.pk).first()
        mine = FollowSubscription.objects.filter(user=user, channel=channel)
        center = mine.filter(city=city, target_kind__in=follow.CENTER_KINDS)
        have = {
            (k, key): pk for pk, k, key in center.values_list("pk", "target_kind", "target_key")
        }
        to_add = want - set(have)
        to_remove = [] if mode == "add" else [pk for t, pk in have.items() if t not in want]
        total = mine.count() - len(to_remove) + len(to_add)
        if to_add and total > follow.max_follows():
            raise follow.FollowLimitReached
        if to_remove:
            result.removed = FollowSubscription.objects.filter(pk__in=to_remove).delete()[0]
        freq = follow.normalize_frequency(
            frequency, follow.Target(FollowSubscription.TARGET_SECTION, "", city)
        )
        for kind, key in sorted(to_add):
            FollowSubscription.objects.create(
                user=user,
                target_kind=kind,
                target_key=key,
                city=city,
                channel=channel,
                portal=portal,
                frequency=freq,
                token=follow._new_token(),
                confirmed_at=now,
                source_host=(source_host or "")[:253],
            )
            result.added += 1
        if mode == "set" and frequency:  # одна частота на весь центр
            center.filter(user=user).exclude(frequency=freq).update(frequency=freq, updated_at=now)
        if want or result.added:
            follow.ensure_follow_token(user)
    if result.removed and not want:
        follow.forget_if_empty(user)
    return result


# --- DOI v2 (аноним: один токен на весь выбор) --------------------------------------------


def make_token(*, email: str, selection: Selection, frequency: str, portal, locale: str) -> str:
    from django.core import signing

    payload = {
        "v": 2,
        "e": email.strip().lower(),
        "sel": selection.as_token(),
        "f": frequency if frequency in follow.FREQUENCIES else FollowSubscription.FREQ_DAILY,
        "p": portal.pk if portal is not None else None,
        "l": follow.normalize_locale(locale),
    }
    return signing.dumps(payload, salt=follow.DOI_SALT, compress=True)


def is_center_payload(payload) -> bool:
    return isinstance(payload, dict) and payload.get("v") == 2


def portal_of(payload):
    from .models import AggregatorPortal

    pk = payload.get("p")
    return AggregatorPortal.objects.filter(pk=pk, is_active=True).first() if pk else None


def selection_of(payload, portal) -> Selection:
    """Выбор из токена — ПЕРЕПРОВЕРЕН по реестрам и теме портала сейчас."""
    return normalize(Selection.from_token(payload.get("sel")), portal)


def confirm(payload: dict, *, source_host: str = "") -> tuple[PortalUser | None, Result]:
    """POST подтверждения v2: житель (создаётся при необходимости) + добавление выбора."""
    portal = portal_of(payload)
    if portal is None:
        return None, Result()
    selection = selection_of(payload, portal)
    if not len(selection):
        return None, Result()
    email = (payload.get("e") or "").strip().lower()
    with transaction.atomic():
        user, _created = PortalUser.objects.get_or_create(email=email)
        locale = follow.normalize_locale(payload.get("l", ""))
        if user.locale != locale:
            user.locale = locale
            user.save(update_fields=["locale", "updated_at"])
        if not user.is_active:
            return None, Result()
        result = apply(
            user,
            selection,
            frequency=payload.get("f", ""),
            portal=portal,
            source_host=source_host,
            mode="add",
        )
    return user, result


def labels(selection: Selection, portal) -> list[str]:
    """Подписи выбора для страницы подтверждения/письма."""
    city = city_of(portal)
    out = []
    for kind, key in sorted(selection.targets(city)):
        out.append(follow.Target(kind, key, city).label)
    return out
