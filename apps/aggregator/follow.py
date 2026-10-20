"""T-8.7 «Folgen»: подписка жителя на бизнес / раздел / район каталога города.

План — docs/t8-7-folgen-plan-2026-10-15.md. Домен без HTTP: цели, DOI-токен, подтверждение,
управление, выборка новинок для письма. Правила:

* До подтверждения в БД ничего нет — состояние живёт в подписанном токене (DSGVO-минимизация).
* Выборка письма идёт ТОЛЬКО через `views.listings_for` (одна точка видимости T-8.6: демо,
  приостановленные, скрытые, истёкшие — никогда).
* Ссылки строятся с явным urlconf (урок T-8.5: из Celery `reverse` без urlconf даёт
  маршруты public-хоста).
"""

from __future__ import annotations

import secrets
from dataclasses import dataclass
from datetime import timedelta
from urllib.parse import urlencode

from django.conf import settings
from django.core import signing
from django.db import IntegrityError, transaction
from django.urls import reverse
from django.utils import timezone
from django.utils.translation import gettext as _

from apps.core import city_categories as cc
from apps.core import districts

from .models import AggregatorListing, AggregatorPortal, FollowSubscription, PortalUser

DOI_SALT = "portal-follow-doi"
DOI_TTL = 7 * 86400
NEW_DAYS = 14  # = portal_home_blocks.NEW_DAYS: «Alle anzeigen» ведёт на ?neu=1 с тем же окном
FREQUENCIES = tuple(k for k, _l in FollowSubscription.FREQUENCIES)


def _cfg(key: str, default):
    return getattr(settings, "AGGREGATOR_FOLLOW", {}).get(key, default)


# --- цели -------------------------------------------------------------------------------


class FollowLimitReached(Exception):
    """T-8.10d Р-1: у жителя уже максимум подписок (всего или подписок на поиск)."""


@dataclass(frozen=True)
class Target:
    kind: str
    key: str
    city: str = ""
    # T-8.10d: канонический набор фильтров (кортеж пар) — только у вида «query».
    query: tuple = ()

    @property
    def allows_instant(self) -> bool:
        return self.kind == FollowSubscription.TARGET_BUSINESS

    @property
    def label(self) -> str:
        if self.kind == FollowSubscription.TARGET_BUSINESS:
            from apps.tenants.models import Tenant

            name = (
                Tenant.objects.filter(schema_name=self.key).values_list("name", flat=True).first()
            )
            return name or self.key
        if self.kind == FollowSubscription.TARGET_QUERY:
            from . import follow_query

            return follow_query.describe(self.query, city=self.city)
        if self.kind == FollowSubscription.TARGET_SECTION:
            section = cc.section(self.key)
            return str(section.label) if section else self.key
        return districts.label(self.city, self.key) or self.key

    @property
    def kind_label(self) -> str:
        return str(dict(FollowSubscription.TARGETS).get(self.kind, self.kind))

    @property
    def query_string(self) -> str:
        """Query-строка ссылки «Folgen» (все пары, корректно разделённые)."""
        from urllib.parse import urlencode

        return urlencode(self.as_params())

    def as_params(self) -> list[tuple[str, str]]:
        """Параметры ссылки «Folgen» (обратная операция `parse_target`)."""
        if self.kind == FollowSubscription.TARGET_BUSINESS:
            from apps.tenants.models import Tenant

            slug = (
                Tenant.objects.filter(schema_name=self.key).values_list("slug", flat=True).first()
            )
            return [("unternehmen", slug or "")]
        if self.kind == FollowSubscription.TARGET_QUERY:
            return [("art", "suche"), ("city", self.city), *self.query]
        if self.kind == FollowSubscription.TARGET_SECTION:
            return [("bereich", self.key)]
        return [("stadtteil", self.key)]


def business_target(tenant) -> Target | None:
    """Цель «бизнес» — только живой, не демо и видимый в каталоге."""
    from .visibility import listable

    if tenant is None or tenant.schema_name == "public" or getattr(tenant, "is_demo", False):
        return None
    if not listable(tenant):
        return None
    return Target(FollowSubscription.TARGET_BUSINESS, tenant.schema_name)


def parse_target(params, *, portal) -> Target | None:
    """`?unternehmen=<slug>` | `?bereich=<раздел|категория>` | `?stadtteil=<slug>` → Target.

    Раздел и район требуют города портала (область сводки); категория сворачивается в
    свой раздел (Р-1b). Незнакомое → None. T-8.10d: `?art=suche&…` — набор фильтров поиска.
    """
    if (params.get("art") or "") == "suche":
        return query_target(params, portal=portal)
    slug = (params.get("unternehmen") or "").strip()
    if slug:
        from apps.tenants.models import Tenant

        tenant = Tenant.objects.filter(slug=slug, is_active=True).first()
        return business_target(tenant)
    city = districts.city_label(getattr(portal, "city", "") or "") if portal else ""
    bereich = (params.get("bereich") or "").strip()
    if bereich and city:
        if cc.section(bereich):
            return Target(FollowSubscription.TARGET_SECTION, bereich, city)
        category = cc.category(bereich)
        if category:
            return Target(FollowSubscription.TARGET_SECTION, category.section, city)
        return None
    stadtteil = (params.get("stadtteil") or "").strip()
    if stadtteil and city:
        slug = districts.normalize(city, stadtteil)
        return Target(FollowSubscription.TARGET_DISTRICT, slug, city) if slug else None
    return None


def query_target(params, *, portal) -> Target | None:
    """T-8.10d: набор фильтров поиска → цель. Набор из одного старого условия (компания,
    раздел, район) сводится к прежней цели — двух подписок на одно и то же нет."""
    from . import follow_query

    city = follow_query.city_for(params, portal)
    pairs = follow_query.canonical(params, city=city, portal=portal is not None)
    if not pairs or not follow_query.valid_business(pairs):
        return None
    legacy = follow_query.legacy(pairs, city=city)
    if legacy is not None:
        kind, key = legacy
        if kind == FollowSubscription.TARGET_BUSINESS:
            schema = follow_query.business_schema(key)
            return Target(kind, schema) if schema else None
        return Target(kind, key, city)
    return Target(FollowSubscription.TARGET_QUERY, follow_query.key(pairs), city, query=pairs)


def target_from_follow(sub: FollowSubscription) -> Target:
    from . import follow_query

    query = (
        follow_query.from_stored(sub.query)
        if sub.target_kind == FollowSubscription.TARGET_QUERY
        else ()
    )
    return Target(sub.target_kind, sub.target_key, sub.city, query=query)


def target_from_payload(payload: dict) -> Target | None:
    """Цель из DOI-токена. Набор поиска ПЕРЕПРОВЕРЯЕТСЯ белым списком: подпись подписью,
    но правила канонизации могли измениться, пока письмо лежало."""
    kind = payload.get("k", "")
    if kind != FollowSubscription.TARGET_QUERY:
        return Target(kind, payload.get("t", ""), payload.get("c", ""))
    from . import follow_query

    city = payload.get("c", "")
    on_portal = payload.get("p") is not None
    if not on_portal and not follow_query.known_city(city):
        return None
    pairs = follow_query.canonical(
        follow_query.from_stored(payload.get("q")), city=city, portal=on_portal
    )
    if not pairs or follow_query.key(pairs) != payload.get("t"):
        return None
    if not follow_query.valid_business(pairs):
        return None
    return Target(kind, follow_query.key(pairs), city, query=pairs)


# --- DOI --------------------------------------------------------------------------------


def normalize_frequency(value: str, target: Target) -> str:
    value = (value or "").strip()
    if value not in FREQUENCIES:
        return FollowSubscription.FREQ_DAILY
    if value == FollowSubscription.FREQ_INSTANT and not target.allows_instant:
        return FollowSubscription.FREQ_DAILY
    return value


def normalize_locale(value: str) -> str:
    value = (value or "").split("-")[0].lower()
    return value if value in getattr(settings, "CABINET_LANGUAGES", ["de"]) else "de"


def make_doi_token(*, email: str, target: Target, frequency: str, portal, locale: str) -> str:
    payload = {
        "e": email.strip().lower(),
        "k": target.kind,
        "t": target.key,
        "c": target.city,
        "f": normalize_frequency(frequency, target),
        "p": portal.pk if portal is not None else None,
        "l": normalize_locale(locale),
    }
    if target.query:
        payload["q"] = [list(p) for p in target.query]
    return signing.dumps(payload, salt=DOI_SALT, compress=True)


def load_doi_token(token: str) -> dict | None:
    """Полезная нагрузка DOI-токена или None (подпись/срок/форма)."""
    ttl = int(_cfg("doi_ttl_days", 7)) * 86400
    try:
        payload = signing.loads(token or "", salt=DOI_SALT, max_age=ttl)
    except (signing.BadSignature, TypeError, ValueError):
        return None
    if not isinstance(payload, dict) or not payload.get("e") or not payload.get("k"):
        return None
    return payload


def _new_token() -> str:
    return secrets.token_urlsafe(32)


def ensure_follow_token(user: PortalUser) -> str:
    """Токен управления; conditional UPDATE — две гонки не перезапишут уже отправленный."""
    if not user.follow_token:
        PortalUser.objects.filter(pk=user.pk, follow_token__isnull=True).update(
            follow_token=_new_token()
        )
        user.refresh_from_db(fields=["follow_token"])
    return user.follow_token


def _check_cap(user, target: Target) -> None:
    """Р-1: не больше `max_follows` подписок, из них не больше `max_query_follows` поисков.
    Вызывать под блокировкой строки жителя (две вкладки не обойдут лимит)."""
    if find(user, target) is not None:
        return  # повтор существующей подписки — не новая
    follows = FollowSubscription.objects.filter(user=user)
    if follows.count() >= int(_cfg("max_follows", 20)):
        raise FollowLimitReached
    if target.kind == FollowSubscription.TARGET_QUERY and follows.filter(
        target_kind=FollowSubscription.TARGET_QUERY
    ).count() >= int(_cfg("max_query_follows", 10)):
        raise FollowLimitReached


def _upsert(user, target: Target, *, frequency: str, portal, source_host: str, now=None):
    from . import follow_query

    now = now or timezone.now()
    defaults = {
        "portal": portal,
        "frequency": normalize_frequency(frequency, target),
    }
    with transaction.atomic():
        PortalUser.objects.select_for_update().filter(pk=user.pk).first()
        _check_cap(user, target)
        sub, created = FollowSubscription.objects.get_or_create(
            user=user,
            target_kind=target.kind,
            target_key=target.key,
            city=target.city,
            channel=FollowSubscription.CHANNEL_EMAIL,
            defaults={
                **defaults,
                "token": _new_token(),
                "confirmed_at": now,
                "source_host": (source_host or "")[:253],
                "query": follow_query.stored(target.query) if target.query else {},
            },
        )
        if not created:
            changed = []
            for field, value in defaults.items():
                if getattr(sub, field) != value:
                    setattr(sub, field, value)
                    changed.append(field)
            if changed:
                sub.save(update_fields=[*changed, "updated_at"])
        ensure_follow_token(user)
    return sub


def confirm(payload: dict, *, source_host: str = "") -> FollowSubscription | None:
    """Подтверждение DOI: создать PortalUser (если нет) и подписку. Идемпотентно.
    T-8.10d: лимит подписок → FollowLimitReached (вид показывает понятный отказ)."""
    target = target_from_payload(payload)
    if target is None or target.kind not in dict(FollowSubscription.TARGETS) or not target.key:
        return None
    if target.kind == FollowSubscription.TARGET_BUSINESS:
        from apps.tenants.models import Tenant

        tenant = Tenant.objects.filter(schema_name=target.key).first()
        if business_target(tenant) is None:  # бизнес ушёл из каталога, пока письмо лежало
            return None
    email = payload["e"].strip().lower()
    portal = (
        AggregatorPortal.objects.filter(pk=payload.get("p")).first() if payload.get("p") else None
    )
    with transaction.atomic():
        user, _created = PortalUser.objects.get_or_create(email=email)
        locale = normalize_locale(payload.get("l", ""))
        if user.locale != locale:
            user.locale = locale
            user.save(update_fields=["locale", "updated_at"])
        if not user.is_active:
            return None
        return _upsert(
            user, target, frequency=payload.get("f", ""), portal=portal, source_host=source_host
        )


def follow_now(user: PortalUser, target: Target, *, frequency: str, portal, source_host: str = ""):
    """Вошедший житель (почта подтверждена magic-link'ом) подписывается без DOI."""
    return _upsert(user, target, frequency=frequency, portal=portal, source_host=source_host)


def is_following(user, target: Target) -> bool:
    if user is None:
        return False
    return FollowSubscription.objects.filter(
        user=user, target_kind=target.kind, target_key=target.key, city=target.city
    ).exists()


def find(user, target: Target) -> FollowSubscription | None:
    return FollowSubscription.objects.filter(
        user=user, target_kind=target.kind, target_key=target.key, city=target.city
    ).first()


def user_follows(user) -> list[FollowSubscription]:
    return list(
        FollowSubscription.objects.filter(user=user).select_related("portal").order_by("created_at")
    )


def set_frequency(sub: FollowSubscription, frequency: str) -> bool:
    """Сменить частоту; «Sofort» у раздела/района отвергается (False)."""
    if frequency not in FREQUENCIES:
        return False
    if frequency == FollowSubscription.FREQ_INSTANT and not target_from_follow(sub).allows_instant:
        return False
    if sub.frequency != frequency:
        sub.frequency = frequency
        sub.save(update_fields=["frequency", "updated_at"])
    return True


def forget_if_empty(user: PortalUser) -> bool:
    """Удалить неявно созданного PortalUser, у которого больше нет НИКАКИХ данных.

    Неявный — тот, кто никогда не входил (нет `last_login_at`) и не оставил избранного или
    отзывов. Иначе запись остаётся — её данные принадлежат жителю, а не подписке.
    """
    if user.last_login_at is not None:
        return False
    if user.follows.exists() or user.favorites.exists():
        return False
    if hasattr(user, "reviews") and user.reviews.exists():
        return False
    user.delete()
    return True


def unsubscribe(sub: FollowSubscription) -> None:
    user = sub.user
    sub.delete()
    forget_if_empty(user)


def unsubscribe_all(user: PortalUser) -> int:
    count, _ = FollowSubscription.objects.filter(user=user).delete()
    if not forget_if_empty(user):  # житель остаётся — старая ссылка управления гаснет
        user.follow_token = None
        user.save(update_fields=["follow_token", "updated_at"])
    return int(count)


def by_token(token: str) -> FollowSubscription | None:
    if not token:
        return None
    return FollowSubscription.objects.filter(token=token).select_related("user", "portal").first()


def user_by_follow_token(token: str) -> PortalUser | None:
    if not token:
        return None
    return PortalUser.objects.filter(follow_token=token, is_active=True).first()


# --- выборка новинок --------------------------------------------------------------------


def item_key(listing) -> str:
    return f"{listing.tenant_schema}|{listing.listing_kind}|{listing.source_ref}"


def since_for(sub: FollowSubscription, now=None):
    """Нижняя граница «нового»: с последнего письма, но не раньше подтверждения и
    не глубже окна «Neu» портала (иначе «Alle anzeigen» показало бы меньше письма)."""
    now = now or timezone.now()
    floor = now - timedelta(days=NEW_DAYS)
    candidates = [floor, sub.confirmed_at]
    if sub.last_sent_at:
        candidates.append(sub.last_sent_at)
    return max(candidates)


def items_for(sub: FollowSubscription, *, since, now=None):
    """ЕДИНСТВЕННАЯ выборка письма — через `portal_scope.pool` (видимость T-8.6, без
    демо; T-8.14: у подписки портала — его город, тип и тема, как «Alle anzeigen»)."""
    from . import portal_scope

    portal = getattr(sub, "portal", None)

    def scoped(**filters):
        # Пустой город подписки = город портала (pool понял бы "" как «без города»).
        if portal is not None and not filters.get("city"):
            filters.pop("city", None)
        return portal_scope.pool(portal, **filters)

    if sub.target_kind == FollowSubscription.TARGET_BUSINESS:
        # Все виды предложений бизнеса (Р-2), но не его собственная карточка «Unternehmen».
        qs = (
            scoped(include_demo=False)
            .filter(tenant_schema=sub.target_key)
            .exclude(listing_kind=AggregatorListing.KIND_BUSINESS)
        )
    elif sub.target_kind == FollowSubscription.TARGET_QUERY:
        from . import follow_query

        qs = follow_query.queryset(sub)
    elif sub.target_kind == FollowSubscription.TARGET_SECTION:
        qs = scoped(
            city=sub.city,
            kinds=AggregatorListing.OFFER_KINDS,
            city_category=sub.target_key,
            include_demo=False,
        )
    else:
        qs = scoped(
            city=sub.city,
            district=sub.target_key,
            kinds=AggregatorListing.OFFER_KINDS,
            include_demo=False,
        )
    return qs.filter(created_at__gt=since).order_by("-created_at", "-pk")


# --- ссылки -----------------------------------------------------------------------------


def _scheme() -> str:
    return "http" if getattr(settings, "DEBUG", False) else "https"


def base_url(portal) -> str:
    host = portal.host if portal is not None else settings.TENANT_DOMAIN_BASE
    return f"{_scheme()}://{host}"


def urlconf_for(portal) -> str:
    return "config.urls_portal" if portal is not None else "config.urls_public"


def absolute(portal, name: str, *, args=(), kwargs=None, params=None) -> str:
    path = reverse(name, args=args, kwargs=kwargs, urlconf=urlconf_for(portal))
    url = base_url(portal) + path
    if params:
        pairs = [(k, v) for k, v in params if v]
        if pairs:
            url += "?" + urlencode(pairs)
    return url


def scope_url(sub: FollowSubscription, *, ch: str = "digest") -> str:
    """«Alle anzeigen»: область портала, которая содержит все элементы письма (⊇)."""
    portal = sub.portal
    if sub.target_kind == FollowSubscription.TARGET_BUSINESS:
        from apps.tenants.models import Tenant

        slug = (
            Tenant.objects.filter(schema_name=sub.target_key).values_list("slug", flat=True).first()
        )
        if not slug:
            return base_url(portal)
        return absolute(portal, "portal-business", kwargs={"slug": slug}, params=[("ch", ch)])
    if sub.target_kind == FollowSubscription.TARGET_QUERY:
        from . import follow_query

        pairs = follow_query.url_params(follow_query.from_stored(sub.query))
        if portal is None:
            return absolute(
                None, "aggregator-index", params=[("city", sub.city), *pairs, ("ch", ch)]
            )
        return absolute(portal, "portal-home", params=[*pairs, ("neu", "1"), ("ch", ch)])
    if portal is None:  # без портала область раздела/района — /entdecken/ по городу
        return absolute(
            None,
            "aggregator-index",
            params=[
                ("city", sub.city),
                (
                    "kat" if sub.target_kind == FollowSubscription.TARGET_SECTION else "stadtteil",
                    sub.target_key,
                ),
                ("ch", ch),
            ],
        )
    if sub.target_kind == FollowSubscription.TARGET_SECTION:
        return absolute(
            portal, "portal-home", params=[("kat", sub.target_key), ("neu", "1"), ("ch", ch)]
        )
    return absolute(
        portal,
        "portal-district",
        kwargs={"district": sub.target_key},
        params=[("neu", "1"), ("ch", ch)],
    )


def manage_url(user: PortalUser, portal) -> str:
    return absolute(portal, "aggregator-follow-manage", kwargs={"token": ensure_follow_token(user)})


def unsubscribe_url(sub: FollowSubscription) -> str:
    return absolute(sub.portal, "aggregator-follow-unsubscribe", kwargs={"token": sub.token})


def unsubscribe_all_url(user: PortalUser, portal) -> str:
    return absolute(
        portal,
        "aggregator-follow-unsubscribe",
        kwargs={"token": ensure_follow_token(user)},
        params=[("alle", "1")],
    )


def confirm_url(portal, token: str) -> str:
    return absolute(portal, "aggregator-follow-confirm", kwargs={"token": token})


def describe(sub: FollowSubscription) -> str:
    """Подпись подписки для писем/кабинета: «Bäckerei X» / «Bereich: Essen» / «Stadtteil: Ohligs»."""
    target = target_from_follow(sub)
    if sub.target_kind == FollowSubscription.TARGET_BUSINESS:
        return target.label
    return _("%(kind)s: %(name)s") % {"kind": target.kind_label, "name": target.label}


__all__ = [
    "Target",
    "parse_target",
    "business_target",
    "make_doi_token",
    "load_doi_token",
    "confirm",
    "follow_now",
    "is_following",
    "find",
    "user_follows",
    "set_frequency",
    "unsubscribe",
    "unsubscribe_all",
    "forget_if_empty",
    "ensure_follow_token",
    "items_for",
    "query_target",
    "target_from_payload",
    "FollowLimitReached",
    "since_for",
    "scope_url",
    "IntegrityError",
]
