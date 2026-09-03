"""Публичная витрина брони (без логина), на корне субдомена бизнеса.

Защита публичных форм: honeypot (website), rate-limit по IP (apps.core.ratelimit,
Hardening H8 — бронь/waitlist по IP+акции, QR-вьюхи по IP против перебора кодов)
и идемпотентность сабмита (form_token) против двойной отправки по F5.
"""

import io
import uuid
from urllib.parse import quote

import segno
from django.conf import settings
from django.contrib import messages
from django.core.cache import cache
from django.db.models import F, Q
from django.http import Http404, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import NoReverseMatch, reverse
from django.utils.translation import gettext as _
from django.views.decorators.clickjacking import xframe_options_sameorigin

from apps.catalog.price_history import lowest_price_30d
from apps.catalog.views import FOOD_BUSINESS_TYPES as _FOOD_TYPES
from apps.core import grid_filler, ratelimit
from apps.core.models import resolve_overlay
from apps.core.pagecache import cache_storefront_page
from apps.core.pagination import paginate
from apps.core.seo import offer_ld
from apps.loyalty.models import LoyaltyCard, LoyaltyProgram, Voucher
from apps.promotions import group_styles, rules_text

from .forms import PublicReservationForm, WaitlistForm
from .models import (
    Customer,
    Promotion,
    Reservation,
    WaitlistEntry,
)
from .services import OutOfStock, ReservationLimitReached, reserve

RL_LIMIT = 5  # попыток (бронь/waitlist на IP+акцию)
RL_WINDOW = 600  # за 10 минут
QR_RL_LIMIT = 60  # QR-вьюх на IP (страница подтверждения рендерит их легитимно)
TOKEN_TTL = 600


def _qr_limited(request) -> bool:
    """Общий лимит QR-вьюх по IP — против перебора кодов броней/ваучеров/карт."""
    return ratelimit.hit("qr", ratelimit.client_ip(request), limit=QR_RL_LIMIT, window=RL_WINDOW)


def _abs_promo_url(request, pk) -> str:
    return request.build_absolute_uri(reverse("storefront-promotion", args=[pk]))


def _detail_ctx(request, promo, form) -> dict:
    img = promo.primary_image
    og_image = request.build_absolute_uri(img["url"]) if img and img.get("url") else ""
    if promo.discount_style == "mystery":
        # SF-1.4: превью ссылки (og:image) показывало НЕразмытое фото товара-
        # носителя — «секрет» раскрывался в мессенджере до клика.
        og_image = ""
    share_url = _abs_promo_url(request, promo.pk)
    # §11 PAngV (M1 Boutique): у зачёркнутой Sale-цены — низшая цена товара за
    # 30 дней (PriceLog). Нет привязанного товара/данных → None, строка молчит.
    lowest_30d = None
    if promo.has_discount and promo.product_id:
        lowest_30d = lowest_price_30d(promo.product)
    # DL-16.3 (AD1): цель акции — карточкой «Gilt für» (mystery — нет: раскрыла бы товар).
    target_card = None
    if promo.target_kind and promo.discount_style != "mystery":
        try:
            from apps.core.sellable import sellable_for

            se = sellable_for(promo.target_kind, promo.target)
            target_card = {
                "kind": promo.target_kind,
                "name": se.name,
                "url": se.detail_url,
                "image_url": se.image_url,
            }
        except Exception:  # noqa: BLE001 — витрина не падает из-за адаптера
            target_card = None
    # DL-16.3 (AD3): «Weitere Aktionen» — та же группа, иначе другие активные.
    others = Promotion.objects.filter(status="active").exclude(pk=promo.pk).order_by("-created_at")
    related = list(others.filter(group=promo.group)[:8]) if promo.group else []
    if len(related) < 2:
        related = list(others[:8])
    return {
        "promotion": promo,
        "form": form,
        "waitlist_form": WaitlistForm(),
        "share_url": share_url,
        "qr_url": reverse("storefront-promotion-qr", args=[promo.pk]),
        "og_image": og_image,
        "ld_offer": offer_ld(promo, url=share_url, image_url=og_image),
        "lowest_30d": lowest_30d,
        "target_card": target_card,
        "conditions": rules_text.conditions_for(promo),  # DL-16.3 AD2
        "related_promos": _attach_lowest_30d(related),
    }


def _capture_channel(request) -> str:
    """Канал из ?ch= запоминаем в сессии, чтобы донести до момента брони."""
    ch = (request.GET.get("ch") or "").strip()[:50]
    if ch:
        request.session["src_ch"] = ch
    return ch or request.session.get("src_ch", "")


def _attach_lowest_30d(promos) -> list:
    """SF-3 (§11 PAngV): низшая цена 30 дней — и на КАРТОЧКАХ со скидкой.

    Батч по товарам-носителям (bulk, без N+1); вешает `p.lowest_30d` только
    там, где карточка реально анонсирует снижение (has_discount + товар).
    Материализует queryset — карточные поверхности не пагинируются."""
    from apps.catalog.price_history import lowest_price_30d_bulk

    promos = list(promos)
    ids = [p.product_id for p in promos if p.product_id and p.has_discount]
    lows = lowest_price_30d_bulk(ids) if ids else {}
    for p in promos:
        p.lowest_30d = lows.get(p.product_id) if p.has_discount else None
    return promos


# Same-origin framing разрешён: кабинет владельца (тот же субдомен-origin)
# показывает витрину в iframe (live-preview конструктора + страница Preview).
# Прод ставит X-Frame-Options: DENY глобально — это бы блокировало iframe.
@xframe_options_sameorigin
@cache_storefront_page
def storefront_home(request):
    _capture_channel(request)
    # Конструктор витрины v1 (Track C2): главная собирается из секций конфига.
    from apps.tenants import siteconfig

    # V1 live-preview: при ?preview=1 и черновике в сессии (из конструктора
    # главной) рендерим несохранённое состояние. Только для вошедшего владельца
    # (черновик в его сессии); standalone-редирект в превью пропускаем.
    preview = request.GET.get("preview") == "1"
    raw = request.tenant.site_config
    if preview and isinstance(request.session.get("site_preview_draft"), dict):
        raw = request.session["site_preview_draft"]
    site = siteconfig.normalize(raw)
    # S4: standalone-режим — корень `/` ведёт на лендинг выбранного архетипа
    # (если он активен и имеет публичную страницу), иначе обычная главная.
    root = site.get("storefront_root", "home")
    if root and root != "home" and not preview:
        from apps.core import modules

        spec = modules.get_module(root)
        if spec and spec.storefront_landing and modules.is_module_active(request.tenant, root):
            try:
                return redirect(reverse(spec.storefront_landing))
            except NoReverseMatch:
                pass
    # H2 (мультиархетип-дефолт главной): если владелец НЕ настраивал композицию (в сыром
    # конфиге нет "sections"), включаем «главный» блок КАЖДОГО активного архетипа в его
    # естественной позиции (магазин+ретриты+услуги → products+events+services …). Рендер
    # гейтится модулем+данными → пустых секций не появится. Если "sections" заданы — НЕ
    # трогаем (не переписываем интент владельца). Обобщает прежний M20U-2 (одна primary →
    # все): products/promotions включены по умолчанию (enable идемпотентен), events/
    # stay_rooms/services — добавляются для активных архетипов.
    if not (isinstance(raw, dict) and raw.get("sections")):
        from apps.core import archetypes

        want = {a["key"] for a in archetypes.aggregate_primary_sections(request.tenant)}
        for s in site["sections"]:
            if s["key"] in want:
                s["enabled"] = True
    # Двуязычная витрина (i18n): свернуть тексты site_config к текущей локали —
    # EN-оверлей поверх базовых DE-значений. Платформенный механизм; переводы
    # сидятся демо-китом. DE/без оверлея → базовые значения (без изменений).
    from django.utils.translation import get_language

    site = siteconfig.localize(site, get_language())
    # DL-3: stateless-превью сборки (?preview=1&bundle=) — кожу даёт context-
    # processor, но КОМПОЗИЦИЮ главной (стили/включение секций, hero_style)
    # рендерит эта вьюха из СВОЕГО site — без оверлея здесь превью сборки
    # показывало бы сохранённую раскладку. Read-only, на копии рядов.
    # DL-8e: тот же ключ приходит и из демо-сессии («Design testen» на витрине).
    from apps.core.demo_switch import overlay_bundle_key

    _ov_bundle = overlay_bundle_key(request)
    if _ov_bundle:
        from apps.tenants import sitetemplates

        site = sitetemplates.apply_preview_bundle(site, _ov_bundle)
    sections = [s["key"] for s in site["sections"] if s["enabled"]]
    # D.2: полные записи включённых секций (фикс + C-блоки с данными) для рендера
    # через {% render_block %}; `sections` (ключи) остаётся для гейтинга запросов.
    # UC6-3a: последовательные узкие C-блоки → ряды (md:flex в home.html).
    section_blocks = siteconfig.group_block_rows([s for s in site["sections"] if s["enabled"]])

    promos_all = (
        list(
            _attach_lowest_30d(
                Promotion.objects.filter(status="active")
                .select_related("product")
                .order_by("-created_at")
            )
        )
        if "promotions" in sections
        else []
    )
    # DL-3 (стиль spotlight секции акций): чипы «Endet bald» над гридом —
    # акции, заканчивающиеся в ближайшие 3 дня (как полоса /aktionen/, SF-2).
    # DL-13 C4: полоса — из ПОЛНОЙ выборки, срез лимита ниже её не режет.
    promo_ending_soon = []
    if promos_all:
        from datetime import timedelta

        from django.utils import timezone as _tz

        _soon = _tz.now() + timedelta(days=3)
        promo_ending_soon = [p for p in promos_all if p.ends_at and p.ends_at <= _soon][:4]
    # DL-13 C4 (решение владельца «лимит 9»): секция главной — первые N акций
    # (настраивается в Studio, дефолт 9) + «Alle Aktionen»; раньше выводились ВСЕ.
    promos = promos_all[: siteconfig.section_limit(site, "promotions")]
    products_preview = []
    if "products" in sections:
        from apps.catalog.models import Product

        # M20U-7: источник товаров секции (избранные/новые/избранные-первыми).
        # KAT-3: select_related — карточки строят SEO-URL через category.slug.
        prod_qs = Product.objects.filter(is_active=True).select_related("category")
        source = siteconfig.product_source(site)
        if source == "featured_only":
            prod_qs = prod_qs.filter(is_featured=True).order_by("-created_at")
        elif source == "newest":
            prod_qs = prod_qs.order_by("-created_at")
        else:  # featured_first
            prod_qs = prod_qs.order_by("-is_featured", "-created_at")
        from .price_layer import attach_promos

        # SF-4b: главная показывает те же промо-цены, что каталог и корзина.
        products_preview = attach_promos(prod_qs[: siteconfig.section_limit(site, "products")])
    # M20U-2: сетка категорий каталога (верхний уровень, активные).
    categories = []
    if "categories" in sections:
        from apps.catalog.models import Category

        # DS-5: владелец задаёт число плиток (Anzahl в Studio; было — все).
        categories = list(
            Category.objects.filter(is_active=True, parent__isnull=True).order_by(
                "sort_order", "slug"
            )[: siteconfig.section_limit(site, "categories")]
        )
    # S2: сетка тизеров активных архетипов («Наши разделы»).
    archetype_teasers = []
    if "archetypes" in sections:
        from apps.tenants import storefront

        archetype_teasers = storefront.archetype_teasers(request.tenant)
    # Карточки номеров на главной (только при активном модуле stays).
    from apps.core import modules

    stay_rooms = []
    if "stay_rooms" in sections and modules.is_module_active(request.tenant, "stays"):
        from apps.stays.models import StayUnit

        stay_rooms = list(StayUnit.objects.filter(is_active=True))
    # M20U-2: ближайшие мероприятия/ретриты (primary items архетипа events).
    events_preview = []
    if "events" in sections and modules.is_module_active(request.tenant, "events"):
        from django.utils import timezone

        from apps.events.models import Event

        events_preview = list(
            Event.objects.filter(
                status=Event.STATUS_PUBLISHED, starts_at__gte=timezone.now()
            ).order_by("starts_at")[: siteconfig.section_limit(site, "events")]
        )
    # MT-F1: поездки (тур-продукты) — главный товар тур-оператора. Гейт по
    # ДАННЫМ, а не по типу бизнеса: у ретрит-кита туров нет, и его главная
    # остаётся прежней даже при включённой секции.
    tours_preview = []
    if "tours" in sections and modules.is_module_active(request.tenant, "events"):
        from apps.events.models import Tour

        tours_preview = list(
            Tour.objects.filter(is_published=True).prefetch_related(Tour.upcoming_prefetch())[
                : siteconfig.section_limit(site, "tours")
            ]
        )
    # HF-1: лента новостей (модуль blog). Черновики и запланированные посты сюда
    # не попадают — на главную идёт только опубликованное.
    blog_preview = []
    if "blog" in sections and modules.is_module_active(request.tenant, "blog"):
        from apps.events.models import BlogPost

        blog_preview = list(
            BlogPost.objects.filter(is_published=True)[: siteconfig.section_limit(site, "blog")]
        )
    # A3: блок «Leistungen & Preise» — услуги (Service) при активном модуле booking.
    services_preview = []
    if "services" in sections and modules.is_module_active(request.tenant, "booking"):
        from apps.booking.models import Service

        services_preview = list(Service.objects.filter(is_active=True))
    # A9/A7: у ремесла/автосервиса (активен модуль jobs — Angebot/Kostenvoranschlag)
    # услуги с ценой подаём как Festpreis — сигнал доверия (прозрачные фикс-цены).
    services_festpreis = modules.is_module_active(request.tenant, "jobs")
    # M20U-5: «главный товар» архетипа — для CTA hero-баннера (ведёт на лендинг
    # primary item: магазин → товары, ретрит → события, отель → номера…).
    from apps.core import archetypes

    primary_item = archetypes.primary_item(request.tenant)
    # MT-F3: вторая кнопка первого экрана («Menu» → каталог) показывается только
    # при наполненном каталоге — иначе она вела на пустую страницу. Модель
    # импортируем здесь: выше она есть лишь внутри ветки секции products.
    from apps.catalog.models import Product as _Product

    has_products = bool(products_preview) or _Product.objects.filter(is_active=True).exists()
    return render(
        request,
        "storefront/home.html",
        {
            "sections": sections,
            "section_blocks": section_blocks,
            "site": site,
            "promotions": promos,
            "promo_ending_soon": promo_ending_soon,  # DL-3: чипы spotlight-стиля
            "products_preview": products_preview,
            "categories": categories,
            "category_tile_aspect": siteconfig.CATEGORY_TILE_ASPECTS.get(
                siteconfig.section_style(site, "categories"), "aspect-[4/3]"
            ),
            "archetype_teasers": archetype_teasers,
            "stay_rooms": stay_rooms,
            "events_preview": events_preview,
            "tours_preview": tours_preview,
            "has_products": has_products,
            "blog_preview": blog_preview,  # HF-1: секция новостей
            "services_preview": services_preview,
            "services_festpreis": services_festpreis,
            "primary_item": primary_item,
        },
    )


#: Сколько акций должно быть в группе, чтобы она получила СВОЮ секцию с
#: заголовком. Сетка страницы — 3 колонки, поэтому группа из одной карточки
#: оставляет две трети строки пустыми (фидбэк владельца 2026-08-07).
MIN_GROUP_SECTION = 2


def _promo_grouping_for(request) -> str:
    """DL-13 C3: режим страницы акций — из сохранённого конфига, а в превью
    сборки (?preview=1&bundle= / «Design testen») — из ОСИ сборки: стенд показал,
    что Retro в превью рисовал тематические группы (ось читалась только из БД)."""
    from apps.core.demo_switch import overlay_bundle_key
    from apps.tenants import siteconfig, sitetemplates

    key = overlay_bundle_key(request)
    if key:
        bundle = sitetemplates.get_bundle(key)
        if bundle is not None:
            return siteconfig.normalize_promo_grouping(bundle["config"].get("promo_grouping"))
    raw = _promo_page_config(request)
    return siteconfig.normalize_promo_grouping(raw.get("promo_grouping"))


def _promo_page_config(request) -> dict:
    """DL-17.3: конфиг страницы акций — с учётом ЧЕРНОВИКА билдера при ?preview=1.
    Без этого правка «Aktionsseite: Aufbau/Gruppierung» в Studio не была видна на
    канве до «Опубликовать», хотя остальные витринные вьюхи черновик читают."""
    if request.GET.get("preview") == "1" and isinstance(
        getattr(request, "session", None) and request.session.get("site_preview_draft"), dict
    ):
        return request.session["site_preview_draft"]
    return request.tenant.site_config if isinstance(request.tenant.site_config, dict) else {}


def _time_groups(promotions, now):
    """DL-13 C3 («Prospekt по времени», анализ DL-12 §2 — Lidl/ALDI/PENNY
    группируют предложения по сроку, а не по теме): секции «Endet heute» ·
    «Endet diese Woche» · «Länger gültig» · «Dauerhaft» (без ends_at) в порядке
    срочности; внутри — ближайший конец первым. Пустые секции выпадают, порог
    MIN_GROUP_SECTION здесь НЕ действует: одна акция «Endet heute» — важнее
    полного ряда (ряд добивает плитка-подсказка DL-11). Будущие «Ab Montag»
    (scheduled) — v2: их деталь наружу закрыта (SF-3), карточка вела бы в 404."""
    from datetime import timedelta

    end_today = now.replace(hour=23, minute=59, second=59, microsecond=999999)
    end_week = end_today + timedelta(days=6 - now.weekday())
    buckets = {"heute": [], "woche": [], "laenger": [], "dauerhaft": []}
    for promo in promotions:
        if promo.ends_at is None:
            buckets["dauerhaft"].append(promo)
        elif promo.ends_at <= end_today:
            buckets["heute"].append(promo)
        elif promo.ends_at <= end_week:
            buckets["woche"].append(promo)
        else:
            buckets["laenger"].append(promo)
    for key in ("heute", "woche", "laenger"):
        buckets[key].sort(key=lambda p: p.ends_at)
    labels = {
        "heute": _("Endet heute"),
        "woche": _("Endet diese Woche"),
        "laenger": _("Länger gültig"),
        "dauerhaft": _("Dauerhaft"),
    }
    return [(key, labels[key], items) for key, items in buckets.items() if items]


def _upcoming_buckets(promos, now):
    """DL-17.4 (A1 «Vorschau»): будущие акции — по НАЧАЛУ: «Ab dieser Woche» ·
    «Ab nächster Woche» · «Demnächst». Prospekt-привычка DACH: покупатель видит,
    что будет дёшево со следующего понедельника, и планирует поход.

    Порог MIN_GROUP_SECTION тут не действует — одна будущая акция тоже новость."""
    from datetime import timedelta

    end_today = now.replace(hour=23, minute=59, second=59, microsecond=999999)
    end_week = end_today + timedelta(days=6 - now.weekday())
    end_next = end_week + timedelta(days=7)
    buckets = {"start_woche": [], "start_naechste": [], "start_spaeter": []}
    for promo in promos:
        if promo.starts_at is None or promo.starts_at <= end_week:
            buckets["start_woche"].append(promo)
        elif promo.starts_at <= end_next:
            buckets["start_naechste"].append(promo)
        else:
            buckets["start_spaeter"].append(promo)
    labels = {
        "start_woche": _("Ab dieser Woche"),
        "start_naechste": _("Ab nächster Woche"),
        "start_spaeter": _("Demnächst"),
    }
    return [(key, labels[key], items) for key, items in buckets.items() if items]


_TIME_MORE = {"heute": "?endet=heute", "woche": "?endet=woche"}


def _group_more_url(key: str, grouping: str) -> str:
    """DL-16.2 (A3): ссылка «Alle anzeigen →» секции — тот же URL, что чип группы
    (тема) или чип срока (время: heute/woche); у остальных секций пусто."""
    if not key:
        return ""
    if grouping == "time":
        return _TIME_MORE.get(key, "")
    from urllib.parse import urlencode

    return "?" + urlencode({"gruppe": key})


def promotion_list(request):
    """Публичный список акций /aktionen/ (S6 → SF-2: рельсы U-B).

    Дефолт без фильтров — Prospekt-секции по группам (фидбэк владельца
    2026-07-29/08-07, MIN_GROUP_SECTION); любой активный фильтр/поиск/
    сортировка → плоская сетка (прежнее поведение ?gruppe=). Системные
    фильтры (Endet heute/Diese Woche, −N %+, Reservierbar), ?q= и сорт —
    PromoFacets (SF-2), состояние живёт в URL (чипы = обычные ссылки)."""
    from datetime import timedelta

    from django.utils import timezone

    from apps.core import facets as facets_registry
    from apps.core import modules
    from apps.tenants import siteconfig

    from .facets import DISCOUNT_PRESETS

    if not modules.is_module_active(request.tenant, "promotions"):
        raise Http404
    provider = facets_registry.provider_for("promotion")
    base = (
        Promotion.objects.filter(status="active").select_related("product").order_by("-created_at")
    )
    q = (request.GET.get("q") or "").strip()
    sort = request.GET.get("sort") or ""
    sel = provider.selected(request.GET)
    # DL-16.2 (A4): посетительский вид «Liste» — плоская таблица для сравнения; ключ
    # `ansicht` как у каталога (серверная ссылка, KAT-5 меняет без перезагрузки).
    list_view = (request.GET.get("ansicht") or "") == "liste"
    _base_qs = request.GET.copy()
    _base_qs.pop("ansicht", None)
    ansicht_base_qs = _base_qs.urlencode()
    # DL-16.2 (A3): раскладка групп — сетка или ленты-слайдеры (Studio-панель)
    # DL-17.3: конфиг страницы с учётом черновика билдера (?preview=1) — один раз
    # на запрос: из него берутся и раскладка групп (A3), и шаблон страницы группы (DL-20).
    page_cfg = _promo_page_config(request)
    cfg = siteconfig.normalize(page_cfg)
    promo_layout = siteconfig.normalize_promo_layout(page_cfg.get("promo_layout"))
    # DL-21.2: шаблон ОБЗОРА (только без выбранной группы — у группы свой, DL-20).
    # «Preisliste» делает таблицу видом владельца; явный ?ansicht=karten сильнее.
    page_style = (
        group_styles.promo_page_style(cfg.get("promo_page_style")) if not sel["gruppe"] else ""
    )
    if page_style == "preisliste" and (request.GET.get("ansicht") or "") != "karten":
        list_view = True
    # поиск ДО apply: фильтр «−N %+» материализует список (см. PromoFacets)
    promotions = _attach_lowest_30d(
        provider.sort(provider.apply(provider.search(base, q), request.GET), sort)
    )

    # Ключ группы — плоское значение (по нему фильтр `?gruppe=`), метка — с
    # оверлеем локали. Карту строим по НЕотфильтрованной выдаче, иначе при
    # выбранной группе остальные чипы остались бы без перевода.
    group_labels = {
        g: resolve_overlay(g, ov) for g, ov in base.values_list("group", "group_i18n") if g
    }
    groups = sorted(group_labels)
    selected = sel["gruppe"]
    has_filters = bool(
        selected or sel["endet"] or sel["rabatt"] or sel["reservierbar"] or q or sort
    )

    # Фидбэк 2026-07-29: группы акций (Wochenangebote/Räumung/…) — СЕКЦИЯМИ с
    # заголовками, а не только чипами-фильтрами (иначе типы акций не считывались).
    # Порядок — по первому вхождению в выдачу (свежая группа первой); акции без
    # группы — в конец под «More offers». Выбран фильтр или групп нет →
    # прежняя плоская сетка.
    grouped = []
    # DL-13 C3: владелец выбрал «по времени» (site_config.promo_grouping, панель
    # в кабинете / ось сборки) — секции по сроку вместо тематических групп.
    promo_grouping = _promo_grouping_for(request)
    if not has_filters and promo_grouping == "time":
        grouped = _time_groups(promotions, timezone.localtime())
    elif not has_filters and groups and page_style not in ("kompakt", "navigator", "magazin"):
        by_group: dict[str, list] = {}
        order: list[str] = []
        for promo in promotions:
            key = promo.group or ""
            if key not in by_group:
                by_group[key] = []
                order.append(key)
            by_group[key].append(promo)
        order.sort(key=lambda g: g == "")  # безгрупповые в конец
        # Фидбэк 2026-08-07 («страница выглядит незаполненной»): секцию получает
        # только группа, которой хватает на осмысленный блок; остальные — одним
        # блоком в конце. Чипы-фильтры сверху показывают ВСЕ группы.
        sections, rest = [], []
        for key in order:
            items = by_group[key]
            # DL-21.2 «Regale»: лента — у КАЖДОЙ группы, порог секции не действует
            if key and len(items) >= (1 if page_style == "regale" else MIN_GROUP_SECTION):
                sections.append((key, group_labels.get(key, key), items))
            else:
                rest.extend(items)
        if not sections:
            grouped = []  # группировать нечего → плоская сетка (ветка шаблона)
        else:
            grouped = sections + ([("", "", rest)] if rest else [])
    # DL-16.2 (A3): «Alle anzeigen →» у секции = чип этой группы/времени (у «More
    # offers»/länger/dauerhaft ссылки нет); 4-й элемент кортежа читает шаблон.
    if list_view:
        grouped = []  # A4: таблица — плоская, без секций и полосы «Endet bald»
    grouped = [
        (key, label, items, _group_more_url(key, promo_grouping)) for key, label, items in grouped
    ]

    # DL-21.2: композиции обзора поверх секций.
    if page_style == "regale":
        promo_layout = "slider"  # Regale = группы лентами со стрелками (та же лента A3)
    promo_hero = None
    if page_style == "schaufenster" and promotions and not has_filters and not list_view:
        promo_hero = promotions[0]
        # герой не дублируется в секциях/сетке
        promotions = [p for p in promotions if p.pk != promo_hero.pk]
        grouped = [
            (k, lbl, [p for p in items if p.pk != promo_hero.pk], more)
            for k, lbl, items, more in grouped
        ]
        grouped = [g for g in grouped if g[2]]
    promo_tabs = []
    if page_style == "tabs" and groups:
        promo_tabs = [
            {"label": _("All"), "url": reverse("storefront-aktionen"), "active": True}
        ] + [
            {"label": group_labels[g], "url": _group_more_url(g, ""), "active": False}
            for g in groups
        ]
    if page_style == "magazin":
        for promo in promotions:
            promo.conditions = rules_text.conditions_for(promo)
    _heroes = cfg.get("heroes") or []
    promo_head_photo = cfg.get("hero_image") or (
        (_heroes[0] or {}).get("image", "") if _heroes and isinstance(_heroes[0], dict) else ""
    )

    # SF-2: компактная полоса «⏳ Endet bald» над секциями — только на чистом
    # виде и только если есть чем наполнить (пустые секции не показываем).
    ending_soon = []
    if not has_filters and not list_view:
        now = timezone.now()
        ending_soon = _attach_lowest_30d(
            base.filter(ends_at__gt=now, ends_at__lte=now + timedelta(days=3)).order_by("ends_at")[
                :4
            ]
        )

    # DL-17.4 (A1): «Vorschau» — акции в статусе `scheduled` с будущим стартом.
    # Отдельным запросом (не в `base`): активные и будущие нельзя мешать в одной
    # выдаче — у будущих нет ни countdown, ни покупки, а фасеты «Endet …» им чужие.
    upcoming_groups = []
    if not has_filters and not list_view:
        _now = timezone.now()
        upcoming = _attach_lowest_30d(
            Promotion.objects.filter(status="scheduled", starts_at__gt=_now)
            .select_related("product")
            .order_by("starts_at")[:8]
        )
        if upcoming:
            upcoming_groups = _upcoming_buckets(upcoming, timezone.localtime())
    # DL-23 (фидбэк «разделим блоками и сделаем их рядом»): бакетов ≥ 2 и в каждом ≤ 2
    # карточек → блоки колонками в одном ряду (иначе три почти пустых ряда по карточке).
    upcoming_columns = (
        len(upcoming_groups)
        if len(upcoming_groups) >= 2 and all(len(items) <= 2 for _k, _l, items in upcoming_groups)
        else 0
    )

    def _chip(label, param, value):
        """Чип-ссылка: тумблер своего параметра с carry остальных (состояние в URL)."""
        params = request.GET.copy()
        active = params.get(param) == str(value)
        if active:
            params.pop(param, None)
        else:
            params[param] = value
        encoded = params.urlencode()
        return {
            "label": label,
            "active": active,
            "url": f"{request.path}?{encoded}" if encoded else request.path,
        }

    system_chips = [
        _chip(_("Ends today"), "endet", "heute"),
        _chip(_("This week"), "endet", "woche"),
        *[_chip(f"−{n} %+", "rabatt", n) for n in DISCOUNT_PRESETS],
        _chip(_("Reservable"), "reservierbar", "1"),
    ]
    # DL-20: страница ГРУППЫ акций. До этой волны её фактически не было — фильтр
    # `?gruppe=` отдавал плоскую сетку под общим заголовком, и посетитель, пришедший
    # по ссылке из меню, не видел даже названия открытой группы. Теперь у группы есть
    # заголовок (всегда) и шаблон страницы: свой у группы → дефолт сайта → Standard.
    group_label, group_style, group_ends_at, group_valid_until = "", "", None, None
    if selected:
        group_label = group_labels.get(selected, selected)
        group_style = group_styles.group_style(
            selected,
            cfg.get("promo_groups"),
            cfg["site_defaults"].get("promo_group_style", ""),
        )
        ends = [p.ends_at for p in promotions if p.ends_at]
        group_ends_at = min(ends) if ends else None
        group_valid_until = max(ends) if ends else None
        if group_style == "countdown" and not sort:
            # «Countdown» — про срочность: первыми истекающие. Явный выбор сорта
            # посетителем сильнее (иначе его переключатель молча не работал бы).
            promotions = sorted(
                promotions, key=lambda p: (p.ends_at is None, p.ends_at or timezone.now())
            )
        if group_style == "magazin":
            # DL-16.3: условия акции человеческим языком — на карточке, а не только
            # на детальной (для группы услуг «Mo–Mi до 14:00» важнее размера скидки).
            for promo in promotions:
                promo.conditions = rules_text.conditions_for(promo)

    toolbar_hidden = [
        (k, v)
        for k, v in (
            ("gruppe", selected),
            ("endet", sel["endet"]),
            ("rabatt", str(sel["rabatt"] or "")),
            ("reservierbar", "1" if sel["reservierbar"] else ""),
        )
        if v
    ]
    return render(
        request,
        "storefront/promotions_list.html",
        {
            "promotions": promotions,
            "groups": [(g, group_labels[g]) for g in groups],
            "selected_group": selected,
            "grouped_promotions": grouped,
            "ending_soon": ending_soon,
            "upcoming_groups": upcoming_groups,
            "system_chips": system_chips,
            "has_filters": has_filters,
            "result_count": len(promotions) if has_filters else None,
            "show_listing_toolbar": True,
            "q": q,
            "sort": sort,
            "sort_options": provider.sort_options(),
            "toolbar_hidden": toolbar_hidden,
            "promo_layout": promo_layout,  # DL-16.2 A3
            # DL-21.2: обзорная страница — шаблон композиции + её данные.
            "promo_page_style": page_style,
            "promo_hero": promo_hero,
            "promo_tabs": promo_tabs,
            "promo_head_photo": promo_head_photo,
            "promo_total": len(promotions) + (1 if promo_hero else 0),
            "promo_group_count": len(groups),
            "upcoming_columns": upcoming_columns,
            # DL-20: страница группы — заголовок и шаблон композиции.
            "group_label": group_label,
            "group_page_style": group_style,
            "group_ends_at": group_ends_at,
            "group_valid_until": group_valid_until,
            # «Vergleich»: средняя колонка помечается «Popular» — при нечётном числе
            # акций это середина, при чётном пометки нет (иначе выбор произволен).
            "promo_middle": (
                len(promotions) // 2 if group_style == "vergleich" and len(promotions) % 2 else None
            ),
            "list_view": list_view,  # DL-16.2 A4
            "ansicht_base_qs": ansicht_base_qs,
        },
    )


def about_page(request):
    """Отдельная страница «О компании» /ueber-uns/ (S8): тексты about + контакты."""
    from django.utils.translation import get_language

    from apps.tenants import siteconfig

    site = siteconfig.localize(siteconfig.normalize(request.tenant.site_config), get_language())
    # DL-6: контакт-блок страницы уважает стиль секции contact (split/map_first/…).
    return render(
        request,
        "storefront/about.html",
        {"site": site, "sections": [], "section_row": _section_row(site, "contact")},
    )


def _site_ctx(request):
    """ST-8: локализованный site_config для отдельных страниц витрины."""
    from django.utils.translation import get_language

    from apps.tenants import siteconfig

    return siteconfig.localize(siteconfig.normalize(request.tenant.site_config), get_language())


def _section_row(site, key):
    """DL-6: ряд секции из нормализованного конфига — тот же section_row, что
    получает партиал на главной (вид секции действует и на своей странице)."""
    return next((s for s in site["sections"] if s["key"] == key), None)


def _pdf_course_groups(cat_title, products):
    """MEN-6: внутри категории — подгруппы по Gang'ам («Bäckerei · Vorspeise»).

    Порядок реестра COURSES; товары без Gang'а идут ОДНОЙ группой с названием
    категории (пекарня/ретейл ничего не заполняли — их карта не меняется).
    """
    from apps.catalog.food import COURSES

    by_course: dict[str, list] = {}
    for p in products:
        by_course.setdefault(p.course or "", []).append(p)
    if set(by_course) <= {""}:  # Gang не заполнен — прежний вид (байт-в-байт)
        return [(cat_title, products)]
    out = [
        (f"{cat_title} · {label}", by_course[code]) for code, label in COURSES if code in by_course
    ]
    if "" in by_course:
        out.append((cat_title, by_course[""]))
    return out


def speisekarte_pdf(request):
    """GK-13: печатная Speisekarte из каталога (PDF, язык = ?lang=/язык витрины).

    catalog — core (модульного гейта нет); без активных товаров → 404 (пустой
    документ бесполезен, и кнопка на каталоге в этом случае не рендерится)."""
    from django.utils import translation

    from apps.catalog.models import Category, Product
    from apps.catalog.pdf import build_menu_pdf
    from apps.core.documents import document_language

    products = list(
        Product.objects.filter(is_active=True).select_related("category").order_by("created_at")
    )
    if not products:
        raise Http404
    lang = document_language(request, tenant=request.tenant)
    with translation.override(lang):
        groups: dict = {}
        for prod in products:
            key = prod.category_id
            groups.setdefault(key, []).append(prod)
        ordered = []
        for cat in Category.objects.order_by("sort_order", "id"):
            if cat.id in groups:
                ordered.extend(_pdf_course_groups(cat.get_i18n("name"), groups.pop(cat.id)))
        if groups:  # без категории — в конец
            rest = [p for items in groups.values() for p in items]
            ordered.extend(_pdf_course_groups(str(_("Other")), rest))
        pdf = build_menu_pdf(request.tenant, ordered)
    response = HttpResponse(pdf, content_type="application/pdf")
    response["Content-Disposition"] = 'inline; filename="speisekarte.pdf"'
    return response


def gallery_page(request):
    """ST-8: отдельная страница «Галерея» /galerie/.

    Гейт — по НАЛИЧИЮ контента (пустая галерея → 404, пункт меню гаснет сам):
    так «нужный раздел для нужных китов» получается из данных, без whitelist
    архетипов, который врал бы владельцу, наполнившему раздел вручную.
    """
    site = _site_ctx(request)
    if not (site.get("gallery") or site.get("gallery_video")):
        raise Http404
    return render(
        request,
        "storefront/gallery.html",
        # as_page: партиал секции не рисует свою шапку и ссылку «Все фото»
        # (заголовок уже на странице, ссылка вела бы сюда же).
        # DL-6: section_row — вид секции владельца (strip/large/…) действует
        # и на отдельной странице, а не только на главной.
        {
            "site": site,
            "sections": [],
            "as_page": True,
            "section_row": _section_row(site, "gallery"),
        },
    )


def team_page(request):
    """ST-8: отдельная страница «Команда/Мастера» /team/ (404 без команды)."""
    site = _site_ctx(request)
    if not site.get("team"):
        raise Http404
    return render(
        request,
        "storefront/team.html",
        {"site": site, "sections": [], "as_page": True, "section_row": _section_row(site, "team")},
    )


def reviews_page(request):
    """ST-8: отдельная страница «Отзывы» /bewertungen/.

    Показывает отзывы о бизнесе с портала (те же, что тизером на главной), но
    полным списком. 404, если отзывов нет.
    """
    from apps.core.templatetags.seo import business_rating, storefront_reviews

    site = _site_ctx(request)
    # Два источника: отзывы с портала (BusinessReview) и кураторские отзывы
    # владельца из site_config (`testimonials` — секция главной). Страница
    # существует, если есть хоть что-то; иначе 404 (пустых страниц не плодим).
    reviews = storefront_reviews(50)
    testimonials = site.get("testimonials") or []
    if not reviews and not testimonials:
        raise Http404
    return render(
        request,
        "storefront/reviews.html",
        {
            "site": site,
            "sections": [],
            "page_reviews": reviews,
            "page_testimonials": testimonials,
            "business_rating_value": business_rating(),
        },
    )


def finder_page(request):
    """FD-1: Finder «вопросы → 3 предложения» (/finder/).

    Серверные шаги БЕЗ JS: чипы — ссылки, накапливающие ответы в `?a=q.chip,…`;
    все вопросы отвечены → 3 карточки (лучшая в середине, «Unser Vorschlag»).
    Finder — ОПЦИЯ (решение владельца 2026-07-18): 404 пока не включён."""
    from django.utils.translation import get_language

    from apps.core import finder
    from apps.tenants import siteconfig

    if not finder.enabled(request.tenant):
        raise Http404
    # Ответы из ?a=: "anlass.geburtstag,budget.klein" (порядок не важен).
    answers = {}
    for pair in (request.GET.get("a") or "").split(","):
        if "." in pair:
            q_key, _, chip_key = pair.partition(".")
            if q_key and chip_key:
                answers[q_key[:40]] = chip_key[:40]
    state = finder.resolve(request.tenant, answers, get_language())
    site = siteconfig.localize(siteconfig.normalize(request.tenant.site_config), get_language())
    carry = ",".join(f"{k}.{v}" for k, v in sorted(answers.items()))
    ctx = {"site": site, "sections": [], "answers_carry": carry, **state}
    return render(request, "storefront/finder.html", ctx)


def loyalty_page(request):
    """Публичная страница программы лояльности /treue/ (S5).

    Описывает активные штамп-карты и приглашает завести аккаунт (если включён
    модуль customer_account) для сбора штампов. Гейтинг модуля loyalty → 404.
    """
    from apps.core import modules

    if not modules.is_module_active(request.tenant, "loyalty"):
        raise Http404
    programs = LoyaltyProgram.objects.filter(is_active=True).order_by("label")
    return render(
        request,
        "storefront/loyalty.html",
        {
            "programs": programs,
            "account_enabled": modules.is_module_active(request.tenant, "customer_account"),
        },
    )


# Сортировки каталога живут в CatalogFacets.sort_keys() (UB2-2): ключ → (поле БД,
# descending) для keyset-пагинации (paginate сам ставит order_by(field, pk)).


def _carry_qs(params: dict) -> str:
    """urlencode непустых параметров (для «Show more»/диет-чипов/скрытых полей)."""
    from urllib.parse import urlencode

    return urlencode({k: v for k, v in params.items() if v not in (None, "", False)})


def product_list(request, slug=None):
    """Публичный каталог витрины (Track C1): активные товары + фасет-фильтры + сортировка.

    Фасеты (категория, диета, цена, бейдж, наличие) — нативные поля БД, поэтому
    композируются с keyset-пагинацией. Гейтятся тумблером `catalog_show_filters` и
    наличием данных (есть разброс цен / есть бейджи / что-то распродано) — нерелевантные
    фильтры само-скрываются (анти-Битрикс простота).

    KAT-1: та же вьюха обслуживает СТРАНИЦУ КАТЕГОРИИ /sortiment/<slug>/ —
    категория из пути (неизвестный slug → 404, это посадочная страница), шапка
    по Category.page_style, `kategorie` в carry не попадает (ссылки/формы бьют
    в текущий путь). Легаси-форма ?kategorie= продолжает работать."""

    from apps.catalog.models import Category, Product
    from apps.core import facets as facets_registry

    provider = facets_registry.provider_for("product")
    # KAT-3: select_related — карточки листинга строят SEO-URL через category.slug.
    products = Product.objects.filter(is_active=True).select_related("category")
    category = None
    path_mode = slug is not None
    if path_mode:
        category = get_object_or_404(Category, slug=slug, is_active=True)
    else:
        slug = request.GET.get("kategorie", "")
        if slug:
            category = Category.objects.filter(slug=slug, is_active=True).first()
            if category is None:
                return redirect("storefront-products")
    # M20U-7 (per-page): конфиг витрины. SE-2a-2: при ?preview=1 — черновик из сессии
    # (раскладка/сортировка/фильтры/подкатегории видны на канве сразу).
    from apps.tenants import siteconfig

    is_preview = request.GET.get("preview") == "1"
    raw_cfg = request.tenant.site_config
    if is_preview and isinstance(request.session.get("site_preview_draft"), dict):
        raw_cfg = request.session["site_preview_draft"]
    cfg = siteconfig.normalize(raw_cfg)
    # KAT-1/DL-20: шаблон СТРАНИЦЫ категории. Два слоя — своё значение категории
    # побеждает общий дефолт сайта `site_defaults["category_page_style"]`; мусор в
    # любом слое → Standard. Конфиг поднят выше по вьюхе именно ради этого дефолта
    # (раньше он читался только к раскладке, ниже по коду).
    from apps.catalog.category_styles import page_style as _category_page_style
    from apps.catalog.category_styles import root_page_style as _root_page_style

    _cat_style_default = cfg["site_defaults"].get("category_page_style", "")
    cat_style = _category_page_style(category, _cat_style_default) if category is not None else ""
    # DL-21.1: у КОРНЯ /sortiment/ свой ключ `catalog_page_style` — дефолт категорий
    # сюда не наследуется (Р-2 плана); роль подкатегорий играют корневые направления.
    if not path_mode:
        cat_style = _root_page_style(cfg.get("catalog_page_style", ""))
    # Снимок набора в рамках выбранной категории ДО фасет-фильтров — из него считаем
    # доступные значения фасетов (границы цены / присутствующие бейджи / есть ли
    # распроданное), чтобы показывать только релевантные фильтры и реальные диапазоны.
    facet_base = provider.apply(products, {"kategorie": slug})
    # KAT-1: при path-режиме категория приходит ИЗ ПУТИ — провайдер получает её
    # мерджем (request.GET её не содержит; явный ?kategorie= в GET подавляется).
    _params = {**request.GET.dict(), "kategorie": slug} if path_mode else request.GET
    sel = provider.selected(_params)
    diet = sel["diet"]
    # UB2-1/2-3: все фасеты провайдера одним вызовом — категория/диета/цена/наличие/
    # происхождение/рейтинг (рейтинг — bulk-summary отзывов, pk__in, keyset-safe).
    products = provider.apply(products, _params)
    # UB2-2: поиск ?q= — по name/description на всех локалях (keyset-safe WHERE);
    # снимок facet_base (границы цены/бейджи/наличие) поиск не сужает — как у диеты.
    q = (request.GET.get("q") or "").strip()
    products = provider.search(products, q)
    # DL-16.5 (K2 «Regale»): товары подкатегорий уже стоят на «полках» — сетка ниже показывает
    # только ПРЯМЫЕ товары направления (иначе всё дублировалось бы; семантика KAT-1 «контейнер
    # включает детей» остаётся у Standard/прочих шаблонов).
    if path_mode and category is not None and cat_style == "regale":
        products = products.filter(category=category)
    # Доступные значения фасетов — из снимка категории (present провайдера).
    chips = provider.present(facet_base, request.GET)
    diet_chips = chips["diet_chips"]
    price_lo, price_hi = chips["price_lo"], chips["price_hi"]
    show_price_filter = chips["show_price_filter"]
    show_stock_filter = chips["show_stock_filter"]
    price_min, price_max = sel["preis_von"], sel["preis_bis"]
    price_min_val = request.GET.get("preis_von", "").strip() if price_min is not None else ""
    price_max_val = request.GET.get("preis_bis", "").strip() if price_max is not None else ""
    only_available = sel["nur_verfuegbar"]
    herkunft, bewertung = sel["herkunft"], sel["bewertung"]
    groesse = sel.get("groesse", "")  # M2 Boutique: фасет размера
    kollektion = sel.get("kollektion", "")  # M4-B Lookbook: подборка товаров

    # --- Фасет-бейдж (Neu/Beliebt/Angebot/Tagesgericht…): только присутствующие;
    # остаётся во вьюхе (вне единого набора UB2-3). ---
    _present_badges = set(facet_base.exclude(badge="").values_list("badge", flat=True).distinct())
    badge_chips = [
        (code, label) for code, label in Product.BADGE_CHOICES if code and code in _present_badges
    ]
    badge = request.GET.get("badge", "")
    badge = badge if badge in {c for c, _ in badge_chips} else ""
    if badge:
        products = products.filter(badge=badge)

    # DL-18.2: направления каталога — КОРНЕВЫЕ категории с товарами в поддереве.
    # Раньше фильтр брал любую категорию с товарами, поэтому магазин с полками
    # («Frische» → Obst & Gemüse / Backwaren) показывал на /sortiment/ не четыре
    # направления, а шесть листьев — иерархия витрины пропадала. Плоский каталог
    # (товары лежат прямо в корневых) не меняется: те же категории, тот же порядок.
    categories = (
        Category.objects.filter(is_active=True, parent__isnull=True)
        .filter(Q(products__is_active=True) | Q(children__products__is_active=True))
        .distinct()
    )
    # Фидбэк 2026-08-07: плитки с фото — только когда фото ЕСТЬ; иначе прежние
    # чипы (у большинства тенантов Category.images пуст, сетка серых
    # прямоугольников была бы хуже текста).
    categories_have_images = any(c.image_url for c in categories)
    # M20U-3: подкатегории выбранной категории — выводим карточками первыми.
    subcategories = (
        list(category.children.filter(is_active=True).order_by("sort_order", "slug"))
        if category is not None
        else []
    )
    # Фидбэк 2026-08-26 («добавь в категории фото»): подкатегории рисовались
    # ТЕКСТОВЫМИ карточками при любом шаблоне, кроме «kopfbild» — у направления
    # с шестью Gängen (pranasy/catering) это шесть серых прямоугольников. Гейт
    # тот же, что у верхнего списка: есть фото — плитки, нет ни у одной —
    # прежняя текстовая сетка байт-в-байт (у большинства тенантов images пуст).
    subcategories_have_images = any(c.image_url for c in subcategories)
    # DL-16.5 (K2 «Regale»): у направления с подкатегориями каждая подкатегория —
    # лента ≤ 8 товаров со слайдером (16.1) + «Alle anzeigen»; прямые товары — сеткой ниже.
    shelves = []
    # полки/табы считают по ВСЕМ активным товарам, не по отфильтрованной выдаче страницы
    _all_products = Product.objects.filter(is_active=True)
    _shelf_sources = subcategories if path_mode else categories  # DL-21.1: корень — направления
    if cat_style == "regale" and _shelf_sources:
        from .price_layer import attach_promos as _attach_promos_shelf

        for sub in _shelf_sources:
            if path_mode:
                sub_qs = _all_products.filter(category=sub)
            else:
                # корневое направление держит товары в детях (KAT-1: контейнер включает
                # прямых детей) — полка собирает поддерево на один уровень
                _ids = [sub.pk, *sub.children.filter(is_active=True).values_list("pk", flat=True)]
                sub_qs = _all_products.filter(category_id__in=_ids)
            items = list(sub_qs.order_by("-is_featured", "-created_at")[:8])
            if items:
                _attach_promos_shelf(items)
                shelves.append({"category": sub, "items": items, "total": sub_qs.count()})
    # DL-16.5 (K3 «Tabs»): подкатегории табами; на странице подкатегории — табы родителя.
    tabs_source = None
    if path_mode and category is not None:
        if cat_style == "tabs" and subcategories:
            tabs_source = category
        elif (
            category.parent_id
            and _category_page_style(category.parent, _cat_style_default) == "tabs"
        ):
            tabs_source = category.parent
    category_tabs = []
    if tabs_source is not None:
        from django.db.models import Count as _Count

        _subs = list(tabs_source.children.filter(is_active=True).order_by("sort_order", "slug"))
        _counts = {
            r["category_id"]: r["n"]
            for r in _all_products.filter(category__in=_subs)
            .values("category_id")
            .annotate(n=_Count("id"))
        }
        category_tabs = [
            {
                "label": tabs_source,
                "url": reverse("storefront-category", args=[tabs_source.slug]),
                "active": category == tabs_source,
                "count": _all_products.filter(category__in=[tabs_source, *_subs]).count(),
            }
        ] + [
            {
                "label": sub,
                "url": reverse("storefront-category", args=[sub.slug]),
                "active": sub == category,
                "count": _counts.get(sub.pk, 0),
            }
            for sub in _subs
        ]
    if not path_mode and cat_style == "tabs" and categories:
        # DL-21.1: корень — «Alle» (актив) + корневые направления со счётчиком поддерева.
        from django.db.models import Count as _Count

        _child_ids = {
            c.pk: [c.pk, *c.children.filter(is_active=True).values_list("pk", flat=True)]
            for c in categories
        }
        _by_cat = {
            r["category_id"]: r["n"]
            for r in _all_products.filter(
                category_id__in=[i for ids in _child_ids.values() for i in ids]
            )
            .values("category_id")
            .annotate(n=_Count("id"))
        }
        category_tabs = [
            {
                "label": _("All"),
                "url": reverse("storefront-products"),
                "active": True,
                "count": _all_products.count(),
            }
        ] + [
            {
                "label": c,
                "url": reverse("storefront-category", args=[c.slug]),
                "active": False,
                "count": sum(_by_cat.get(i, 0) for i in _child_ids[c.pk]),
            }
            for c in categories
        ]
    # DL-16.5 (K1): хлебные крошки страницы категории (видимые + BreadcrumbList).
    catalog_breadcrumbs = []
    catalog_breadcrumb_ld = ""
    if path_mode and category is not None:
        from apps.core.seo import breadcrumb_ld as _breadcrumb_ld

        chain = []
        node = category
        while node is not None and len(chain) < 5:
            chain.append(node)
            node = node.parent
        chain.reverse()
        root_label = (request.tenant.site_config or {}).get("catalog_title") or _("Our products")
        catalog_breadcrumbs = [(root_label, reverse("storefront-products"))] + [
            (str(c), reverse("storefront-category", args=[c.slug]) if c != category else "")
            for c in chain
        ]
        catalog_breadcrumb_ld = _breadcrumb_ld(
            [(n, request.build_absolute_uri(u) if u else "") for n, u in catalog_breadcrumbs]
        )
    # MEN-24d (фидбэк «переключатели видов рядом с сортировкой»): посетительский
    # вид каталога — серверный ?ansicht=<preset> (работает при ЛЮБОМ стиле
    # владельца, вкл. авторские karte/buch — class-swap их не умел). Мусор →
    # выбор владельца (normalize_layout, один источник правды с билдером).
    _owner_preset = cfg["catalog_layout"]["preset"]
    # KAT-1: шаблон категории «Preisliste» — прайс-вид как per-page ДЕФОЛТ этой
    # страницы (carry считает отличие от него → чистые URL без ?ansicht=).
    # DL-20: у трёх новых шаблонов плотность сетки — часть композиции (журнал по 2,
    # мозаика по 4, компакт по 6), поэтому они задают тот же per-page дефолт, что и
    # «Preisliste». Посетительский `?ansicht=` остаётся сильнее (carry ниже).
    _STYLE_PRESET = {
        "preisliste": "preisliste",
        "magazin": "cols2",
        "mosaik": "cols4",
        "kompakt": "cols6",
    }
    if cat_style in _STYLE_PRESET:
        # Стенд DL-20: `cfg["catalog_layout"]` уже нормализован и несёт ЯВНЫЕ cols/
        # mobile/tablet — normalize_layout ставит их выше пресета, и «cols4» менял
        # только ярлык (сетка оставалась 3-колоночной). Шаблон задаёт плотность —
        # явные колонки снимаем, gap/width/tail владельца остаются.
        _keep = {
            k: v for k, v in cfg["catalog_layout"].items() if k not in ("cols", "mobile", "tablet")
        }
        if cat_style == "mosaik":
            # Бенто — настоящая grid-сетка со спанами; хвост «spread» (DL-14) сделал бы
            # контейнер flex, а DL-15 дорисовал бы широкую одиночную карточку поверх
            # спанов. «show» = всё показать, ничего не распределять.
            _keep["tail"] = "show"
        cfg["catalog_layout"] = siteconfig.normalize_layout(
            {**_keep, "preset": _STYLE_PRESET[cat_style]},
            {"preset": _owner_preset},
            extra_presets=siteconfig.PAGE_EXTRA_PRESETS["catalog_layout"],
        )
        _owner_preset = cfg["catalog_layout"]["preset"]
    _ansicht_raw = (request.GET.get("ansicht") or "").strip()
    if _ansicht_raw:
        cfg["catalog_layout"] = siteconfig.normalize_layout(
            {**cfg["catalog_layout"], "preset": _ansicht_raw},
            {"preset": _owner_preset},
            extra_presets=siteconfig.PAGE_EXTRA_PRESETS["catalog_layout"],
        )
    # carry только при реальном отличии — дефолтные URL остаются чистыми
    ansicht = (
        cfg["catalog_layout"]["preset"] if cfg["catalog_layout"]["preset"] != _owner_preset else ""
    )
    catalog_grid = siteconfig.grid_class_string(cfg["catalog_layout"])
    # DL-11 → DL-14: листинг контент не прячет; неполный ряд по умолчанию
    # РАСПРЕДЕЛЯЕТСЯ по ширине (spread) + авто-колонки по числу элементов — атрибуты
    # ставит {% sf_grid_attrs catalog_layout count=… %} в шаблоне (число элементов
    # известно только там). Плитка-подсказка DL-11 — только при tail="fill" в
    # раскладке страницы.
    catalog_layout = cfg["catalog_layout"]
    catalog_filler = (
        grid_filler.filler_for("catalog", request.tenant, exclude=("catalog",))
        if catalog_layout.get("tail") == "fill"
        else None
    )
    # Фидбэк владельца 2026-08-27 («категории по 3 в ряд»): число колонок у плиток
    # категорий не подчинялось настройке. Верхний список звал {% grid_classes site
    # 'categories' %}, но `site` в контекст этой вьюхи НЕ кладётся — тег молча брал
    # дефолт секции; сетка подкатегорий была захардкожена (lg:grid-cols-4). Оба
    # берут раскладку секции «categories»; подкатегории оставляют свой плотный
    # отступ (gap "sm") — при дефолте cols4 строки классов прежние байт-в-байт.
    _categories_layout = siteconfig.section_layout(cfg, "categories")
    categories_grid = siteconfig.grid_class_string(_categories_layout)
    subcategory_grid = siteconfig.grid_class_string({**_categories_layout, "gap": "sm"})
    categories_filler = (
        grid_filler.filler_for("categories", request.tenant)
        if _categories_layout.get("tail") == "fill"
        else None
    )
    # Сортировка: из ?sort= (выбор покупателя) либо дефолт витрины; keyset по (поле, pk).
    _sort_keys = provider.sort_keys()
    sort = request.GET.get("sort") or cfg.get("catalog_sort", "newest")
    if sort not in _sort_keys:
        sort = "newest"
    _field, _desc = _sort_keys[sort]
    # DL-11: размер страницы кратен колонкам десктопа И планшета (24 делится на
    # 2/3/4/6; при 5 колонках — 20), иначе каждая страница кончалась бы обрывком.
    page = paginate(
        products,
        order_field=_field,
        descending=_desc,
        limit=20 if cfg["catalog_layout"]["cols"] == 5 else 24,
        cursor=request.GET.get("cursor"),
    )
    # A1/A2: рейтинг ★ на карточке каталога — bulk-агрегат по видимой странице (без N+1
    # и без GROUP BY на keyset-запросе): один запрос на pk текущей страницы, навешиваем
    # review_avg/review_count атрибутами на инстансы (page.items — материализованный список).
    if page.items:
        from apps.reviews import services as review_services

        _rating = review_services.bulk_summary("product", [_p.pk for _p in page.items])
        for _p in page.items:
            _row = _rating.get(_p.pk)
            _p.review_avg = _row["avg"] if _row else None
            _p.review_count = _row["count"] if _row else 0
        # P6 «ценовой слой» → SF-4b (вариант A): карточка показывает ПРОМО-ЦЕНУ
        # (бейдж/зачёркнутая база/§11 PAngV-референс) — bulk одним хелпером.
        from .price_layer import attach_promos

        attach_promos(page.items)
    # A4: комбо-наборы (Menü-Sets/Tagesgericht), если есть и модуль orders активен.
    # M20U/A4: показываем тизер-карточками вверху меню (до 3) — не только текст-ссылкой,
    # — чтобы Kombo/Tagesgericht были на виду (сильный апселл гастро). Только на 1-й
    # странице каталога без выбранной категории (чтобы не дублировать при пагинации/фильтре).
    from apps.catalog.combos import active_combos

    any_facet_active = bool(
        diet
        or badge
        or price_min is not None
        or price_max is not None
        or only_available
        or herkunft
        or groesse
        or kollektion
        or bewertung
        or q
    )
    has_combos = request.tenant.is_module_active("orders") and active_combos().exists()
    combos_teaser = (
        list(active_combos()[:3])
        if has_combos
        and category is None
        and not request.GET.get("cursor")
        and not any_facet_active
        else []
    )
    # KAT-1: контент шапки страницы категории (бывший лендинг /bereich/).
    cat_photos = (
        [img.get("url") for img in (category.images or []) if img.get("url")]
        if category is not None
        else []
    )
    # KAT-2: наборы ЭТОЙ категории — полоса карточек (видимость как у /kombi/:
    # каталог core, цены гейтит карточка); на «Show more»/фасетах не дублируем.
    category_combos = (
        list(
            active_combos()
            .filter(category=category)
            .prefetch_related("groups__options")
            .order_by("sort_order", "created_at")[:6]
        )
        if category is not None and not request.GET.get("cursor") and not any_facet_active
        else []
    )
    # Carry-over параметров между формами/ссылками (чтобы фильтры/сорт не терялись):
    #  • filter_hidden / filter_qs — все активные фасеты КРОМЕ sort (для формы сорта и
    #    ссылки «Show more», которая сама добавляет sort+cursor);
    #  • filter_form_hidden — нефасетные параметры (для формы цены/бейджа/наличия);
    _facets = {
        # KAT-1: path-режим — категория живёт В ПУТИ, в carry её не носим
        # (иначе каждая ссылка продублировала бы её GET-параметром поверх).
        "kategorie": "" if path_mode else (category.slug if category else ""),
        "diet": diet,
        "badge": badge,
        "preis_von": price_min_val,
        "preis_bis": price_max_val,
        "nur_verfuegbar": "1" if only_available else "",
        "herkunft": herkunft,  # UB2-3: Bio/Regional-происхождение
        "groesse": groesse,  # M2: размер
        "kollektion": kollektion,  # M4-B: подборка (лукбук)
        "bewertung": str(bewertung) if bewertung else "",  # UB2-3: минимум звёзд
        "q": q,  # UB2-2: поиск — полноправный фасет в carry
        "ansicht": ansicht,  # MEN-24d: посетительский вид (пусто = вид владельца)
        "preview": "1" if is_preview else "",
    }
    filter_hidden = [(k, v) for k, v in _facets.items() if v]
    filter_qs = _carry_qs(_facets)
    # MEN-24d: qs для ссылок самого переключателя — carry БЕЗ ansicht (иначе
    # параметр дублировался бы в href «?…&ansicht=X»).
    ansicht_base_qs = _carry_qs({k: v for k, v in _facets.items() if k != "ansicht"})
    # Фидбэк 2026-08-07: диета переехала В панель фильтров (видимый селект), так
    # что скрытым полем её больше не носим — иначе в форме было бы два `diet`.
    filter_form_hidden = [
        (k, v)
        for k, v in (
            ("kategorie", _facets["kategorie"]),  # KAT-1: в path-режиме пусто
            ("q", q),
            ("sort", sort if sort != "newest" else ""),
            ("ansicht", ansicht),  # MEN-24d: «Anwenden» панели не сбрасывает вид
            ("preview", _facets["preview"]),
        )
        if v
    ]
    _heroes = cfg.get("heroes") or []
    _root_header_photo = cfg.get("hero_image") or (
        (_heroes[0] or {}).get("image", "") if _heroes and isinstance(_heroes[0], dict) else ""
    )
    return render(
        request,
        "storefront/products.html",
        {
            "page": page,
            "categories": categories,
            "categories_have_images": categories_have_images,
            "categories_grid": categories_grid,
            "categories_layout": _categories_layout,  # DL-14: {% sf_grid_attrs %} в шаблоне
            "categories_filler": categories_filler,
            "category_tile_aspect": siteconfig.CATEGORY_TILE_ASPECTS.get(
                siteconfig.section_style(cfg, "categories"), "aspect-[4/3]"
            ),
            "current_category": category,
            # «Категории с описанием»: i18n-описание выбранной категории (или "").
            "category_description": category.get_i18n("description") if category else "",
            # KAT-1/KAT-2: страница категории — шаблон, шапка, полоса наборов.
            "category_page_style": cat_style,
            "category_header_ready": bool(category is not None and category.landing_ready),
            # шапка — у шаблонов kopfbild/sets при наличии контента; Standard ""
            # остаётся байт-в-байт прежним видом фильтра (замки характеризации).
            "show_category_header": bool(
                path_mode
                and category is not None
                and category.landing_ready
                # DL-20: «Magazin» и «Schaufenster» тоже открываются шапкой — она у них
                # часть композиции (обложка / представление направления).
                and cat_style in ("kopfbild", "sets", "magazin", "schaufenster")
            ),
            "category_photos": cat_photos[:6],
            "category_photo": (cat_photos[:1] or [""])[0],
            "category_combos": category_combos,
            "is_category_page": path_mode,
            # H1.2: кастомные заголовок/интро страницы каталога (инлайн-правка на канве).
            "catalog_title": cfg.get("catalog_title", ""),
            "catalog_intro": cfg.get("catalog_intro", ""),
            "subcategories": subcategories,
            "subcategory_grid": subcategory_grid,
            "subcategories_have_images": subcategories_have_images,
            # DL-16.5: «полки»/табы/крошки; плитки подкатегорий в этих шаблонах не дублируем
            "shelves": shelves,
            "category_tabs": category_tabs,
            # DL-20: «Navigator» уводит подкатегории в боковую колонку, «Kompakt» —
            # в компактный указатель; плитки в общем потоке в обоих случаях лишние.
            "subcats_hidden": cat_style in ("regale", "tabs", "navigator", "kompakt"),
            # DL-20: боковая колонка «Navigator» — фасеты и структура рядом с товарами.
            "category_side_nav": cat_style == "navigator",
            # DL-21.1: корень — те же композиции над корневыми направлениями.
            "root_list_hidden": (
                not path_mode and cat_style in ("regale", "tabs", "navigator", "kompakt")
            ),
            "side_categories": subcategories if path_mode else categories,
            "show_root_header": bool(
                not path_mode
                and cat_style in ("kopfbild", "magazin", "schaufenster")
                and (cfg.get("catalog_intro") or _root_header_photo)
            ),
            "root_header_photo": _root_header_photo,
            # корень «Regale»: страница = полки; общая сетка всех товаров дублировала бы их
            "shelves_only": bool(not path_mode and cat_style == "regale" and shelves),
            "catalog_breadcrumbs": catalog_breadcrumbs,
            "catalog_breadcrumb_ld": catalog_breadcrumb_ld,
            # KAT-1/фидбэк 2026-08-26: у страницы категории — свой хост C-блоков
            # («catalog:<slug>»), поэтому галерея/отзывы/команда добавляются на
            # ОДНУ категорию, а не на весь каталог. Пусто вне path-режима.
            "category_block_host": (
                siteconfig.category_host(category.slug)
                if path_mode and category is not None
                else ""
            ),
            "has_combos": has_combos,
            "combos_teaser": combos_teaser,  # A4: тизер-карточки Kombo/Tagesgericht
            "diet_chips": diet_chips,  # A4: фасет-чипы диет (только встречающиеся)
            # GK-13: кнопка «Speisekarte (PDF)» — гастро-типам, при непустом каталоге
            # (по ВСЕМ товарам, не по текущему фильтру — карта всегда полная).
            "menu_pdf_available": (
                request.tenant.business_type in _FOOD_TYPES
                and Product.objects.filter(is_active=True).exists()
            ),
            "active_diet": diet,
            "catalog_grid": catalog_grid,
            "catalog_layout": catalog_layout,  # DL-14: {% sf_grid_attrs %} в шаблоне
            # DL-16.1 S4: нормализованный конфиг под именем `site` — гейты шаблонов
            # (`site.menu_show_prices`, `site.menu_labels`) раньше молча давали '' на /sortiment/.
            "site": cfg,
            "grid_filler": catalog_filler,
            # DS-3a (Fokus): вид «прайс-лист» — шаблон ветвится по пресету.
            "catalog_preset": cfg["catalog_layout"]["preset"],
            # KAT-4: стартовая плотность контрола «− N +» = колонки владельца.
            "catalog_cols": cfg["catalog_layout"]["cols"],
            # MEN-24d: серверный переключатель видов у сортировки.
            "ansicht": ansicht,
            "ansicht_base_qs": ansicht_base_qs,
            "owner_preset": _owner_preset,
            # Билдер: показывать ли фильтры на странице каталога (group=catalog).
            "catalog_show_filters": cfg.get("catalog_show_filters", True),
            # Фасет цены (диапазон base_price) — показываем при разбросе цен.
            "show_price_filter": show_price_filter,
            "price_lo": price_lo,
            "price_hi": price_hi,
            "price_min_val": price_min_val,
            "price_max_val": price_max_val,
            # Фасет-бейдж (Neu/Beliebt/…) — чипы только присутствующих.
            "badge_chips": badge_chips,
            "active_badge": badge,
            # Тумблер «только в наличии» — показываем только если что-то распродано.
            "show_stock_filter": show_stock_filter,
            "only_available": only_available,
            # UB2-3: происхождение (Bio/Regional) — чипы реально указанных значений.
            "origin_chips": chips["origin_chips"],
            "active_herkunft": herkunft,
            # M2 Boutique: фасет размера (чипы из вариантов, только доступные).
            "size_chips": chips["size_chips"],
            "active_groesse": groesse,
            # M4-B Lookbook: чипы подборок владельца (?kollektion=<slug>).
            "collection_chips": chips["collection_chips"],
            "active_kollektion": kollektion,
            # UB2-3: рейтинг-фасет (минимум звёзд) — только когда есть отзывы.
            "show_rating_filter": chips["show_rating_filter"],
            "rating_thresholds": chips["rating_thresholds"],
            "active_bewertung": bewertung,
            # Активен ли хоть один фасет (для кнопки сброса / подавления комбо-тизера).
            "any_facet_active": any_facet_active,
            # Carry-over для формы сорта и ссылки «Show more».
            "filter_hidden": filter_hidden,
            "filter_qs": filter_qs,
            "filter_form_hidden": filter_form_hidden,
            # UB2-2: тулбар каркаса (поиск + сортировка из провайдера); carry — все
            # активные фасеты, кроме q (у тулбара свой инпут) и sort (свой select).
            "show_listing_toolbar": bool(page.items or q),
            "q": q,
            "toolbar_hidden": [(k, v) for k, v in _facets.items() if v and k != "q"],
            "sort": sort,
            "sort_options": provider.sort_options(),
            # Билдер: показывать ли подкатегории карточками первыми (group=catalog).
            "catalog_subcats_first": cfg.get("catalog_subcats_first", True),
            # SE-2c-2: в режиме редактора (?preview=1) на чипах категорий — ссылка
            # «✎» на полную правку категории в кабинете (имя/slug/родитель/иконка).
            "is_preview": is_preview,
        },
    )


def product_detail(request, pk=None, pslug=None, cslug=None):
    from apps.catalog.models import Product

    # KAT-3: три адреса одной детали — uuid (легаси/письма/QR), /sortiment/p/<slug>/
    # (без категории) и /sortiment/<категория>/<slug>/. Слаговый резолв СТРОГИЙ:
    # чужая категория в пути → 404 (не дублируем контент по любым путям).
    if pk is not None:
        product = get_object_or_404(Product, pk=pk, is_active=True)
    elif cslug is not None:
        product = get_object_or_404(
            Product.objects.select_related("category"),
            slug=pslug,
            category__slug=cslug,
            is_active=True,
        )
    else:
        product = get_object_or_404(Product, slug=pslug, category__isnull=True, is_active=True)
    from .price_layer import attach_promos

    related = attach_promos(
        Product.objects.filter(is_active=True, category=product.category)
        .select_related("category")  # KAT-3: карточки → SEO-URL без N+1
        .exclude(pk=product.pk)
        .order_by("-is_featured", "-created_at")[:8]  # DL-16.6 (D4): до 8 — лента, если > ряда
        if product.category_id
        else []
    )
    from apps.tenants import siteconfig

    # При ?preview=1 — черновик из сессии (on-canvas правка видимости секций детальной).
    _raw = getattr(request.tenant, "site_config", {}) or {}
    if request.GET.get("preview") == "1" and isinstance(
        request.session.get("site_preview_draft"), dict
    ):
        _raw = request.session["site_preview_draft"]
    _cfg = siteconfig.normalize(_raw)
    related_grid = siteconfig.grid_class_string(_cfg["detail_related_layout"])
    # DL-14: атрибуты «полных рядов» ставит шаблон (spread + авто-колонки по числу).
    related_layout = _cfg["detail_related_layout"]
    # DL-16.6 (D4): похожих больше, чем колонок ряда → лента [data-sf-slider]; в пределах
    # ряда — сетка (лента из 2 карточек на десктопе выглядела бы как обрубок). Явный
    # scroll-режим Studio отдаёт ленту сам (движок раскладок, scroll → slider с DL-16.1).
    related_strip = not related_layout.get("scroll") and len(related) > int(
        related_layout.get("cols") or 4
    )
    from apps.catalog import reviews as product_reviews
    from apps.core.sellable import sellable_for

    from .price_layer import promo_for_product

    return render(
        request,
        "storefront/product_detail.html",
        {
            "product": product,
            # P6 «ценовой слой»: активная акция на ЭТОТ товар — баннер с промо-ценой
            # и ссылкой на акцию (чекаут по промо-цене — там, /p/<uuid>/kaufen/).
            "target_promo": (target_promo := promo_for_product(product)),
            # SF-3 (§11 PAngV): референс низшей цены — и под rose-тизером акции
            # (зачёркнутая цена в баннере тоже «Bekanntgabe» снижения).
            "target_promo_lowest": (
                lowest_price_30d(product)
                if target_promo is not None and target_promo.has_discount
                else None
            ),
            # UA2-1 (U-A): единый контракт продаваемой сущности в контексте детали
            # (шов для buy-box UA3 / секций UA4 / JSON-LD UA4-4b).
            "sellable": sellable_for("product", product),
            # M2 Boutique: распроданные размеры → форма Warteliste на карточке.
            "waitlist_variants": list(product.variants.filter(is_active=True, stock_quantity=0)),
            # M3 Boutique: Click&Reserve — гейт опции + доступные размеры.
            "site_anprobe": bool(_cfg.get("anprobe")),
            "anprobe_variants": list(
                product.variants.filter(is_active=True).exclude(stock_quantity=0)
            ),
            "related": related,
            "related_grid": related_grid,
            "related_layout": related_layout,
            "related_strip": related_strip,
            "grid_filler": (
                grid_filler.filler_for("related", request.tenant)
                if related_layout.get("tail") == "fill"
                else None
            ),
            # Кнопка «Zur Abholung bestellen» (D2a) — только при активном модуле.
            "orders_enabled": request.tenant.is_module_active("orders"),
            # GK-14: browse-only каталог (orders off) — buy-box падает в Anfrage-CTA.
            "jobs_active": request.tenant.is_module_active("jobs"),
            # A1/A2: отзывы о товаре (только верифицированные покупатели).
            "reviews": list(product_reviews.published_for(product)),
            "review_summary": product_reviews.summary(product),
            "review_form_token": uuid.uuid4().hex,
            # Скрытые опц. секции детальной товара (билдер: group=catalog_detail).
            "product_detail_hidden": siteconfig.product_detail_hidden(_cfg),
            # DL-16.6 (D2): "" — описание/Kennzeichnung в правой колонке, отзывы телом;
            # "tabs" — все три панелями тела (аккордеон <md, табы md+).
            "product_detail_layout": siteconfig.product_detail_layout(_cfg),
            # Гейт панели/блока Kennzeichnung — есть хоть одно поле (LMIV/Textil).
            "product_has_info": bool(
                product.origin
                or product.ingredients
                or product.allergen_labels
                or product.additive_labels
                or product.material
                or product.care
            ),
        },
    )


RECENT_MAX = 8


def products_recent(request):
    """DL-16.6 (D4): фрагмент «Zuletzt angesehen» — карточки по pk из localStorage
    посетителя (`?ids=a,b,…`, порядок клиента, ≤8, только активные; мусор молча
    выпадает). Хранилище — браузер, а не сессия: cache-сессия писалась бы на КАЖДЫЙ
    анонимный просмотр товара (Redis-ключ на каждого бота) и ставила бы куку витрине
    без действия посетителя (UX-принцип владельца: без трекинг-кук)."""
    from apps.catalog.models import Product

    from .price_layer import attach_promos

    ids = []
    for raw in (request.GET.get("ids") or "").split(",")[:RECENT_MAX]:
        try:
            ids.append(uuid.UUID(raw.strip()))
        except ValueError:
            continue
    if not ids:
        return HttpResponse("")
    by_pk = {
        p.pk: p
        for p in Product.objects.filter(pk__in=ids, is_active=True).select_related("category")
    }
    products = attach_promos([by_pk[i] for i in ids if i in by_pk])
    if not products:
        return HttpResponse("")
    return render(request, "storefront/_recent_strip.html", {"products": products})


def product_review_submit(request, pk):
    """A1/A2: приём отзыва о товаре. Только верифицированный покупатель (есть заказ
    с этим товаром по email). Один отзыв на (товар, email) — повтор обновляет.

    UA4-4a: пишем в generic `reviews.Review` (`entity_kind='product'`); верификация —
    per-kind адаптер `reviews.services.is_verified_buyer` (fail-closed)."""
    from apps.catalog.models import Product
    from apps.reviews import services as review_services
    from apps.reviews.models import Review

    product = get_object_or_404(Product, pk=pk, is_active=True)
    detail_url = product.get_absolute_url()  # KAT-3: SEO-URL
    if request.method != "POST":
        return redirect(detail_url)
    # Рейтлимит на отправку (анти-спам), как в публичных формах акций/заявок.
    if ratelimit.hit("product_review", ratelimit.client_ip(request), limit=10, window=3600):
        messages.error(request, _("Zu viele Versuche. Bitte später erneut."))
        return redirect(detail_url)
    name = (request.POST.get("author_name") or "").strip()[:120]
    email = (request.POST.get("email") or "").strip()
    comment = (request.POST.get("comment") or "").strip()
    try:
        rating = int(request.POST.get("rating") or 0)
    except (TypeError, ValueError):
        rating = 0
    if not (name and email and 1 <= rating <= 5):
        messages.error(request, _("Bitte Name, E-Mail und Bewertung (1–5) angeben."))
        return redirect(detail_url)
    if not review_services.is_verified_buyer("product", product, email):
        messages.error(
            request,
            _(
                "Nur verifizierte Käufer können bewerten — wir haben keine Bestellung mit dieser E-Mail gefunden."
            ),
        )
        return redirect(detail_url)
    Review.objects.update_or_create(
        entity_kind="product",
        entity_id=product.pk,
        email=email.lower(),
        defaults={
            "rating": rating,
            "author_name": name,
            "comment": comment,
            "verified": True,
            "is_published": True,
        },
    )
    messages.success(request, _("Danke für Ihre Bewertung!"))
    return redirect(detail_url + "#bewertungen")


def promotion_detail(request, pk):
    from django.utils import timezone

    promo = get_object_or_404(Promotion, pk=pk)
    # DL-17.4 (A1 «Vorschau»): у будущей акции деталь ОТКРЫТА, но без покупки —
    # состав и условия видны заранее (Prospekt), кнопка появится на старте.
    # Раньше scheduled отдавал голый 404, из-за чего карточку «Ab Mo.» показать
    # было нельзя (комментарий в _time_groups).
    if promo.status == "scheduled" and promo.starts_at and promo.starts_at > timezone.now():
        form = PublicReservationForm(initial={"form_token": uuid.uuid4().hex})
        ctx = _detail_ctx(request, promo, form)
        ctx["promo_preview"] = True
        return render(request, "storefront/promotion_detail.html", ctx)
    if promo.status != "active":
        # SF-3: QR с флаера/старая ссылка после конца акции вели в голый 404.
        # Публичной акция БЫЛА только в ended/paused/archived — им дружелюбная
        # страница (беендет — HTTP 410 Gone для краулеров, пауза — 200);
        # draft/scheduled наружу не светились → прежний 404 (не раскрываем).
        if promo.status not in ("ended", "archived", "paused"):
            raise Http404
        from apps.core import modules

        alternatives = []
        if modules.is_module_active(request.tenant, "promotions"):
            alternatives = _attach_lowest_30d(
                Promotion.objects.filter(status="active")
                .exclude(pk=promo.pk)
                .select_related("product")
                .order_by("-created_at")[:3]
            )
        response = render(
            request,
            "storefront/promotion_ended.html",
            {
                "promotion": promo,
                "paused": promo.status == "paused",
                "alternatives": alternatives,
            },
        )
        if promo.status != "paused":
            response.status_code = 410
        return response
    ch = _capture_channel(request)
    # аналитика: атомарный счётчик просмотров (не блокирует рендер)
    Promotion.objects.filter(pk=promo.pk).update(views=F("views") + 1)
    form = PublicReservationForm(initial={"form_token": uuid.uuid4().hex, "channel": ch})
    return render(request, "storefront/promotion_detail.html", _detail_ctx(request, promo, form))


def set_language(request):
    """Переключатель языка витрины: ставит cookie, LocaleMiddleware подхватит.

    L1 (Волна L): валидируем против `tenant.active_locales` (включённые владельцем
    локали этого тенанта), а не всего реестра `settings.LANGUAGES` — нельзя
    переключиться на язык, который тенант не открыл. Неизвестная/выключенная локаль
    → `default_locale` тенанта.
    """
    tenant = getattr(request, "tenant", None)
    if tenant is not None:
        allowed, fallback = tenant.active_locales, tenant.default_locale
    else:
        # Вне тенант-контекста (напр. юнит-тест) — валидируем против всего реестра
        # `settings.LANGUAGES`, как до L1 (нет тенанта → нет per-tenant-ограничения).
        allowed, fallback = list(dict(settings.LANGUAGES)), settings.LANGUAGE_CODE
    lang = request.GET.get("lang", "")
    if lang not in allowed:
        lang = fallback
    resp = redirect(request.GET.get("next") or reverse("storefront-home"))
    resp.set_cookie(settings.LANGUAGE_COOKIE_NAME, lang, max_age=60 * 60 * 24 * 365)
    return resp


def promotion_qr(request, pk):
    """SVG QR акции. С ?ch=<канал> кодирует ссылку с меткой источника
    (instagram/flyer/schaufenster…) — для печати на каждый канал свой QR."""
    promo = get_object_or_404(Promotion, pk=pk, status="active")
    url = _abs_promo_url(request, promo.pk)
    ch = (request.GET.get("ch") or "").strip()
    if ch:
        url += ("&" if "?" in url else "?") + "ch=" + quote(ch)
    buf = io.BytesIO()
    segno.make(url, error="m").save(buf, kind="svg", scale=6, border=2)
    return HttpResponse(buf.getvalue(), content_type="image/svg+xml")


def reservation_qr(request, code):
    """Персональный QR брони. Кодирует ссылку погашения в кабинете —
    сотрудник сканирует штатной камерой и попадает на страницу выдачи."""
    if _qr_limited(request):
        return HttpResponse(status=429)
    code = code.strip().upper()
    get_object_or_404(Reservation, reference_code=code)
    redeem_url = request.build_absolute_uri(reverse("promotions:redeem-detail", args=[code]))
    buf = io.BytesIO()
    segno.make(redeem_url, error="m").save(buf, kind="svg", scale=6, border=2)
    return HttpResponse(buf.getvalue(), content_type="image/svg+xml")


def voucher_qr(request, code):
    """QR ваучера. Кодирует ссылку погашения в кабинете (сотрудник сканирует)."""
    if _qr_limited(request):
        return HttpResponse(status=429)
    code = code.strip().upper()
    get_object_or_404(Voucher, code=code)
    redeem_url = (
        request.build_absolute_uri(reverse("promotions:voucher-redeem")) + "?code=" + quote(code)
    )
    buf = io.BytesIO()
    segno.make(redeem_url, error="m").save(buf, kind="svg", scale=6, border=2)
    return HttpResponse(buf.getvalue(), content_type="image/svg+xml")


def reservation_create(request, pk):
    promo = get_object_or_404(Promotion, pk=pk, status="active")
    if request.method != "POST":
        return redirect("storefront-promotion", pk=pk)

    # honeypot — тихо игнорируем ботов (отдаём вид успеха)
    if request.POST.get("website"):
        return redirect("storefront-promotion", pk=pk)

    form = PublicReservationForm(request.POST)
    ctx = _detail_ctx(request, promo, form)
    if not form.is_valid():
        return render(request, "storefront/promotion_detail.html", ctx)

    # rate-limit по IP+акции (атомарный, см. apps.core.ratelimit)
    rl_ident = f"{ratelimit.client_ip(request)}:{pk}"
    if ratelimit.hit("resv", rl_ident, limit=RL_LIMIT, window=RL_WINDOW):
        messages.error(request, _("Zu viele Versuche. Bitte später erneut."))
        return render(request, "storefront/promotion_detail.html", ctx)

    # идемпотентность: токен «занимаем» на время попытки, на успехе оставляем,
    # на ошибке освобождаем (чтобы клиент мог повторить с другими данными)
    token = form.cleaned_data.get("form_token")
    token_key = f"resv_token:{token}" if token else None
    if token_key and not cache.add(token_key, "1", TOKEN_TTL):
        return redirect("storefront-promotion", pk=pk)  # дубль сабмита

    channel = (form.cleaned_data.get("channel") or request.session.get("src_ch") or "").strip()
    try:
        res = reserve(
            promo,
            name=form.cleaned_data["name"],
            email=form.cleaned_data.get("email", ""),
            phone=form.cleaned_data.get("phone", ""),
            quantity=form.cleaned_data["quantity"],
            source_channel=channel,
        )
    except OutOfStock:
        if token_key:
            cache.delete(token_key)
        messages.error(request, _("Leider ausverkauft."))
        return render(request, "storefront/promotion_detail.html", ctx)
    except ReservationLimitReached:
        if token_key:
            cache.delete(token_key)
        messages.error(request, _("Limit pro Kunde erreicht."))
        return render(request, "storefront/promotion_detail.html", ctx)

    return redirect("storefront-confirmation", code=res.reference_code)


def promotion_purchase(request, pk):
    """P5 «ценовой слой»: покупка акции СТАНДАРТНЫМ заказом (цель product/combo
    или свободная акция). Гейты — как у reservation_create (honeypot, rate-limit,
    идемпотентный токен); успех → штатное подтверждение заказа. Цели service/
    stay сюда не ходят — их CTA ведёт в собственную воронку (промо-цена там
    применяется автоматически)."""
    promo = get_object_or_404(Promotion, pk=pk, status="active")
    if request.method != "POST" or promo.target_kind in ("service", "stay"):
        return redirect("storefront-promotion", pk=pk)
    if request.POST.get("website"):  # honeypot
        return redirect("storefront-promotion", pk=pk)

    form = PublicReservationForm(request.POST)
    ctx = _detail_ctx(request, promo, form)
    if not form.is_valid():
        return render(request, "storefront/promotion_detail.html", ctx)

    rl_ident = f"{ratelimit.client_ip(request)}:{pk}"
    if ratelimit.hit("resv", rl_ident, limit=RL_LIMIT, window=RL_WINDOW):
        messages.error(request, _("Zu viele Versuche. Bitte später erneut."))
        return render(request, "storefront/promotion_detail.html", ctx)

    token = form.cleaned_data.get("form_token")
    token_key = f"resv_token:{token}" if token else None
    if token_key and not cache.add(token_key, "1", TOKEN_TTL):
        return redirect("storefront-promotion", pk=pk)  # дубль сабмита

    channel = (form.cleaned_data.get("channel") or request.session.get("src_ch") or "").strip()
    from . import services as promo_services

    try:
        order = promo_services.purchase(
            promo,
            quantity=form.cleaned_data["quantity"],
            name=form.cleaned_data["name"],
            email=form.cleaned_data.get("email", ""),
            phone=form.cleaned_data.get("phone", ""),
            source_channel=channel,
        )
    except OutOfStock:
        if token_key:
            cache.delete(token_key)
        messages.error(request, _("Leider ausverkauft."))
        return render(request, "storefront/promotion_detail.html", ctx)

    return redirect("storefront-order", code=order.reference_code)


def waitlist_join(request, pk):
    """Записать в лист ожидания распроданной акции."""
    promo = get_object_or_404(Promotion, pk=pk, status="active")
    if request.method != "POST" or request.POST.get("website"):
        return redirect("storefront-promotion", pk=pk)
    rl_ident = f"{ratelimit.client_ip(request)}:{pk}"
    if ratelimit.hit("waitlist", rl_ident, limit=RL_LIMIT, window=RL_WINDOW):
        messages.error(request, _("Zu viele Versuche. Bitte später erneut."))
        return redirect("storefront-promotion", pk=pk)
    form = WaitlistForm(request.POST)
    if form.is_valid():
        WaitlistEntry.objects.get_or_create(
            promotion=promo,
            email=form.cleaned_data["email"].lower(),
            defaults={"name": form.cleaned_data.get("name", "")},
        )
        messages.success(request, _("Wir benachrichtigen Sie, sobald wieder verfügbar."))
    else:
        messages.error(request, _("Bitte eine gültige E-Mail angeben."))
    return redirect("storefront-promotion", pk=pk)


def product_waitlist_join(request, pk):
    """M2 Boutique: подписка на возврат товара/размера (Warteliste). Гейты — как
    у промо-waitlist: honeypot + rate-limit по IP+товару; идемпотентно."""
    from apps.catalog import waitlist as product_waitlist
    from apps.catalog.models import Product, ProductVariant

    product = get_object_or_404(Product, pk=pk, is_active=True)
    if request.method != "POST" or request.POST.get("website"):
        return redirect(product.get_absolute_url())
    rl_ident = f"{ratelimit.client_ip(request)}:{pk}"
    if ratelimit.hit("waitlist", rl_ident, limit=RL_LIMIT, window=RL_WINDOW):
        messages.error(request, _("Zu viele Versuche. Bitte später erneut."))
        return redirect(product.get_absolute_url())
    email = (request.POST.get("email") or "").strip().lower()
    if not email or "@" not in email:
        messages.error(request, _("Bitte eine gültige E-Mail angeben."))
        return redirect(product.get_absolute_url())
    variant = None
    variant_pk = (request.POST.get("variant") or "").strip()
    if variant_pk:
        variant = ProductVariant.objects.filter(pk=variant_pk, product=product).first()
    product_waitlist.join(product, email, variant=variant)
    messages.success(request, _("Wir benachrichtigen Sie, sobald wieder verfügbar."))
    return redirect(product.get_absolute_url())


def product_anprobe_reserve(request, pk):
    """M3 Boutique: Click&Reserve — зарезервировать вещь в примерочную (48 ч,
    без оплаты). Гейты: site_config.anprobe + модуль orders + наличие; honeypot +
    rate-limit как у Warteliste."""
    from django.utils import timezone

    from apps.catalog.models import Product, ProductVariant
    from apps.orders.anprobe import create_anprobe
    from apps.orders.services import OutOfStock
    from apps.tenants import siteconfig

    product = get_object_or_404(Product, pk=pk, is_active=True)
    if request.method != "POST" or request.POST.get("website"):
        return redirect(product.get_absolute_url())
    cfg = siteconfig.normalize(getattr(request.tenant, "site_config", {}) or {})
    if not cfg.get("anprobe") or not request.tenant.is_module_active("orders"):
        return redirect(product.get_absolute_url())
    rl_ident = f"{ratelimit.client_ip(request)}:{pk}"
    if ratelimit.hit("anprobe", rl_ident, limit=RL_LIMIT, window=RL_WINDOW):
        messages.error(request, _("Zu viele Versuche. Bitte später erneut."))
        return redirect(product.get_absolute_url())
    name = (request.POST.get("name") or "").strip()
    email = (request.POST.get("email") or "").strip().lower()
    if not name or not email or "@" not in email:
        messages.error(request, _("Bitte Name und eine gültige E-Mail angeben."))
        return redirect(product.get_absolute_url())
    variant = None
    variant_pk = (request.POST.get("variant") or "").strip()
    if variant_pk:
        variant = ProductVariant.objects.filter(pk=variant_pk, product=product).first()
    try:
        order = create_anprobe(product=product, variant=variant, name=name, email=email)
    except OutOfStock:
        messages.error(request, _("Leider gerade nicht verfügbar."))
        return redirect(product.get_absolute_url())
    from django.utils import formats

    until = formats.date_format(timezone.localtime(order.reserve_expires_at), "d.m.Y H:i")
    messages.success(
        request,
        _("Zurückgelegt bis %(until)s — wir freuen uns auf Sie!") % {"until": until},
    )
    return redirect(product.get_absolute_url())


def reservation_confirmation(request, code):
    # MEDIUM-6: троттлим перебор короткого reference_code.
    if ratelimit.hit(
        "resv_confirm", ratelimit.client_ip(request), limit=QR_RL_LIMIT, window=RL_WINDOW
    ):
        return HttpResponse(status=429)
    res = get_object_or_404(Reservation.objects.select_related("promotion"), reference_code=code)
    return render(request, "storefront/confirmation.html", {"reservation": res})


def unsubscribe(request, token):
    """Быстрая отписка от писем по токену (one-click, GET и POST)."""
    customer = Customer.objects.filter(unsubscribe_token=token).first()
    if customer is not None and not customer.unsubscribed:
        customer.unsubscribed = True
        customer.save(update_fields=["unsubscribed", "updated_at"])
    return render(request, "storefront/unsubscribed.html", {"ok": customer is not None})


def newsletter_signup(request):
    """G3: подписка на рассылку с Double-Opt-In (UWG §7). POST — создаём/находим
    клиента по e-mail и шлём письмо подтверждения; согласие ставит только
    переход по ссылке из письма."""
    from . import newsletter

    state = "form"
    if request.method == "POST":
        # honeypot — тихо игнорируем ботов (нейтральный вид «отправлено»)
        if request.POST.get("website"):
            return render(request, "storefront/newsletter.html", {"state": "sent"})
        email = (request.POST.get("email") or "").strip().lower()
        name = (request.POST.get("name") or "").strip()
        if "@" not in email:
            return render(request, "storefront/newsletter.html", {"state": "error"})
        # rate-limit по IP: анти-спам (email-бомбинг чужих адресов + неогранич. рост Customer)
        if ratelimit.hit("news", ratelimit.client_ip(request), limit=RL_LIMIT, window=RL_WINDOW):
            return render(request, "storefront/newsletter.html", {"state": "error"})
        customer = Customer.objects.filter(email__iexact=email).order_by("created_at").first()
        if customer is None:
            customer = Customer.objects.create(
                name=name, email=email, created_source=Customer.SOURCE_MANUAL
            )
        # нейтральный ответ независимо от статуса (не раскрываем, подписан ли e-mail);
        # уже подтверждённому подписчику письмо повторно НЕ шлём (анти-спам)
        if not (customer.marketing_opt_in and not customer.unsubscribed):
            newsletter.send_doi_email(
                customer, base_url=request.build_absolute_uri("/").rstrip("/")
            )
        state = "sent"
    return render(request, "storefront/newsletter.html", {"state": state})


def newsletter_confirm(request, token):
    """G3: подтверждение Double-Opt-In по подписанной ссылке из письма."""
    from . import newsletter

    customer = newsletter.load_doi_token(token)
    if customer is not None:
        newsletter.confirm_opt_in(customer)
    return render(
        request, "storefront/newsletter.html", {"state": "confirmed" if customer else "error"}
    )


def _legal_page(request, title, body):
    return render(request, "storefront/legal.html", {"legal_title": title, "legal_body": body})


def impressum(request):
    # L5: тексты через резолвер LegalDoc (per-locale) с фолбэком на Tenant-поля.
    from apps.core.legal import legal_text

    return _legal_page(request, "Impressum", legal_text(request.tenant, "impressum"))


def privacy(request):
    from apps.core.legal import legal_text

    return _legal_page(request, "Datenschutz", legal_text(request.tenant, "datenschutz"))


def withdrawal(request):
    from apps.core.legal import legal_text

    # C.1: для дистанционной продажи товаров показываем кнопку онлайн-Widerruf.
    return render(
        request,
        "storefront/legal.html",
        {
            "legal_title": "Widerruf",
            "legal_body": legal_text(request.tenant, "widerruf"),
            "show_widerruf_button": bool(getattr(request.tenant, "delivery_enabled", False)),
        },
    )


def shared_preview(request, token):
    """A4: анонимное read-only превью черновика по share-токену.

    Снапшот из cache (фиксирован при выпуске, TTL 7 дней) кладём в сессию
    посетителя под `site_preview_draft` и уводим на `/?preview=1` — штатный
    draft-путь витрины (главная + хром). Правок логики чтения не требуется;
    page-кэш обходится сам (непустая сессия/GET). Нет/истёк → 410.
    """
    draft = cache.get(f"share_preview:{token}")
    if not isinstance(draft, dict):
        return render(
            request,
            "storefront/legal.html",
            {
                "legal_title": _("Link abgelaufen"),
                "legal_body": _(
                    "Diese Vorschau-Ansicht ist abgelaufen oder wurde nicht gefunden. "
                    "Bitten Sie den Absender um einen neuen Link."
                ),
            },
            status=410,
        )
    request.session["site_preview_draft"] = draft
    return redirect("/?preview=1")


def agb(request):
    """E-2/L5: страница AGB — только при заданном тексте (фолбэка нет)."""
    from apps.core.legal import legal_text

    text = legal_text(request.tenant, "agb")
    if not text.strip():
        raise Http404
    return _legal_page(request, "AGB", text)


def withdrawal_form(request):
    """C.1: онлайн-форма Widerruf (§ 312k BGB) — заявление уходит продавцу.

    Доступна всегда (право на отзыв нельзя «спрятать»). honeypot + rate-limit.
    Заявление и копию показываем клиенту; продавцу — письмом (+ inbox-тред, если
    модуль активен), чтобы Widerruf был зафиксирован независимо от настроек.
    """
    tenant = request.tenant
    fields = ("name", "email", "address", "goods", "ordered_at", "order_code")
    if request.method == "POST":
        if request.POST.get("website"):  # honeypot
            return redirect("storefront-withdrawal-form")
        if ratelimit.hit("widerruf", ratelimit.client_ip(request), limit=5, window=600):
            return HttpResponse(status=429)
        data = {k: request.POST.get(k, "").strip()[:500] for k in fields}
        if not (data["name"] and data["goods"]):
            messages.error(request, _("Please enter your name and the goods."))
            return render(request, "storefront/withdrawal_form.html", {"data": data})
        _deliver_withdrawal(request, tenant, data)
        return render(request, "storefront/withdrawal_form.html", {"sent": True, "data": data})
    return render(request, "storefront/withdrawal_form.html", {"data": {}})


def _deliver_withdrawal(request, tenant, data):
    """Доставить заявление о Widerruf продавцу: inbox-тред (если активен) + email."""
    decl = (
        "Widerruf eines Kaufvertrags\n\n"
        f"Hiermit widerrufe ich den Vertrag über den Kauf folgender Waren:\n{data['goods']}\n\n"
        f"Bestellnummer: {data['order_code'] or '—'}\n"
        f"Bestellt/erhalten am: {data['ordered_at'] or '—'}\n"
        f"Name: {data['name']}\n"
        f"E-Mail: {data['email'] or '—'}\n"
        f"Anschrift: {data['address'] or '—'}\n"
    )
    # 1) inbox-тред (бизнес видит в кабинете), если модуль активен.
    if tenant.is_module_active("inbox"):
        try:
            from apps.inbox import services as inbox_services

            inbox_services.start_conversation(
                subject="Widerruf",
                body=decl[:5000],
                name=data["name"],
                email=data["email"],
                phone="",
            )
        except Exception:
            pass
    # 2) письмо продавцу (фиксирует Widerruf независимо от inbox).
    to = tenant.public_email or tenant.contact_email
    if to:
        try:
            from django.core.mail import send_mail

            send_mail(
                f"Widerruf — {tenant.name}",
                decl,
                getattr(settings, "DEFAULT_FROM_EMAIL", "noreply@example.com"),
                [to],
                fail_silently=True,
            )
        except Exception:
            pass


def loyalty_card_qr(request, token):
    """QR карты лояльности: кодирует ссылку начисления штампа в кабинете."""
    if _qr_limited(request):
        return HttpResponse(status=429)
    card = get_object_or_404(LoyaltyCard.objects.select_related("program"), token=token)
    stamp_url = (
        request.build_absolute_uri(reverse("promotions:loyalty-stamp", args=[card.program_id]))
        + "?card="
        + str(card.token)
    )
    buf = io.BytesIO()
    segno.make(stamp_url, error="m").save(buf, kind="svg", scale=6, border=2)
    return HttpResponse(buf.getvalue(), content_type="image/svg+xml")


def sitemap_xml(request):
    """Sitemap витрины (Track B5): главная + активные акции, абсолютные URL хоста.

    Без django.contrib.sitemaps (мульти-тенант: домен берём из request, не из
    Sites). Простой и тестируемый XML.
    """
    from xml.sax.saxutils import escape

    urls = [request.build_absolute_uri(reverse("storefront-home"))]
    urls += [
        request.build_absolute_uri(reverse("storefront-promotion", args=[pk]))
        for pk in Promotion.objects.filter(status="active").values_list("pk", flat=True)
    ]
    # Каталог витрины (Track C1).
    from apps.catalog.models import Product

    # KAT-3: в sitemap — канонический SEO-URL товара (get_absolute_url; без
    # слага — uuid-фолбэк); select_related — slug категории без N+1.
    sm_products = list(Product.objects.filter(is_active=True).select_related("category"))
    if sm_products:
        urls.append(request.build_absolute_uri(reverse("storefront-products")))
        # KAT-1: страницы категорий — посадочные для non-brand запросов
        # («Käse Hilden»); только категории с активными товарами.
        from apps.catalog.models import Category

        urls += [
            request.build_absolute_uri(reverse("storefront-category", args=[cslug]))
            for cslug in Category.objects.filter(is_active=True, products__is_active=True)
            .distinct()
            .values_list("slug", flat=True)
        ]
        urls += [request.build_absolute_uri(p.get_absolute_url()) for p in sm_products]
    # CM-1: блог — свежий контент для локального SEO (только при активном модуле).
    tenant = getattr(request, "tenant", None)
    if tenant is not None and tenant.is_module_active("blog"):
        from apps.events.models import BlogPost

        blog_slugs = list(BlogPost.objects.filter(is_published=True).values_list("slug", flat=True))
        if blog_slugs:
            urls.append(request.build_absolute_uri(reverse("storefront-blog")))
            urls += [
                request.build_absolute_uri(reverse("storefront-blog-post", args=[slug]))
                for slug in blog_slugs
            ]
    # MT-1: тур-продукты — самостоятельные посадочные страницы (модуль events).
    if tenant is not None and tenant.is_module_active("events"):
        from apps.events.models import Tour

        tour_slugs = list(Tour.objects.filter(is_published=True).values_list("slug", flat=True))
        if tour_slugs:
            urls.append(request.build_absolute_uri(reverse("storefront-tours")))
            urls += [
                request.build_absolute_uri(reverse("storefront-tour", args=[slug]))
                for slug in tour_slugs
            ]
    body = "".join(f"<url><loc>{escape(u)}</loc></url>" for u in urls)
    xml = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
        f"{body}</urlset>"
    )
    return HttpResponse(xml, content_type="application/xml")


def robots_txt(request):
    """robots.txt витрины: всё открыто + ссылка на sitemap (Track B5).

    SEO-3b: если владелец выключил ИИ-индексацию (site_config["seo"]["allow_ai"]
    == False) — добавляем Disallow для известных AI-краулеров (GEO-контроль)."""
    sitemap = request.build_absolute_uri(reverse("storefront-sitemap"))
    body = f"User-agent: *\nAllow: /\nSitemap: {sitemap}\n"
    tenant = getattr(request, "tenant", None)
    cfg = tenant.site_config if isinstance(getattr(tenant, "site_config", None), dict) else {}
    if (cfg.get("seo") or {}).get("allow_ai") is False:
        from apps.core.seo import AI_CRAWLERS

        body += "\n" + "".join(f"\nUser-agent: {bot}\nDisallow: /\n" for bot in AI_CRAWLERS)
    return HttpResponse(body, content_type="text/plain")


def llms_txt(request):
    """SEO-3c: llms.txt — краткое машиночитаемое описание бизнеса для AI-ассистентов
    (GEO). Имя, город, описание, разделы витрины + ключевые ссылки. Ошибки внутри
    гасим (страница-обвязка не должна ронять; всегда отдаём хотя бы имя)."""
    from django.urls import NoReverseMatch

    tenant = getattr(request, "tenant", None)
    if tenant is None:
        return HttpResponse("", content_type="text/plain; charset=utf-8")
    cfg = tenant.site_config if isinstance(getattr(tenant, "site_config", None), dict) else {}
    base = request.build_absolute_uri("/").rstrip("/")
    lines = [f"# {tenant.name}", ""]
    desc = (cfg.get("hero_text") or cfg.get("about_text") or "").strip()
    if desc:
        lines += ["> " + " ".join(desc.split()), ""]
    if (getattr(tenant, "city", "") or "").strip():
        lines += [f"Standort: {tenant.city}", ""]
    try:
        from apps.core import modules

        sections = []
        for spec in modules.active_modules(tenant):
            if not spec.storefront_landing:
                continue
            try:
                url = base + reverse(spec.storefront_landing)
            except NoReverseMatch:
                continue
            sections.append(f"- [{spec.storefront_label or spec.label_de}]({url})")
        if sections:
            lines += ["## Angebot", *sections, ""]
    except Exception:  # noqa: BLE001 — обвязка не должна ронять llms.txt
        pass
    lines += ["## Seiten", f"- [Startseite]({base}/)"]
    body = "\n".join(lines) + "\n"
    return HttpResponse(body, content_type="text/plain; charset=utf-8")


def product_feed_xml(request):
    """Product-feed (M23b): Google Merchant / Meta Commerce RSS по активным товарам.

    Публичный URL на субдомене бизнеса; площадки тянут по расписанию. Домен —
    из request (мульти-тенант). Без фото/идентификатора товар всё равно в фиде.
    """
    from apps.catalog.feed import build_google_feed
    from apps.catalog.models import Product

    products = (
        Product.objects.filter(is_active=True)
        .select_related("category")  # KAT-3: SEO-link в фиде без N+1
        .prefetch_related("variants")
        .order_by("-created_at")
    )
    tenant = getattr(request, "tenant", None)
    name = getattr(tenant, "name", "") or "Shop"
    xml = build_google_feed(
        products=products,
        title=name,
        link=request.build_absolute_uri(reverse("storefront-home")),
        description=_("Products from %(name)s") % {"name": name},
        product_url=lambda p: request.build_absolute_uri(p.get_absolute_url()),
        absolutize=request.build_absolute_uri,
    )
    return HttpResponse(xml, content_type="application/xml")
