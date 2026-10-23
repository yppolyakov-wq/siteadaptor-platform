"""T-8.4 «Schnell-Aktion» + лимит 5 активных акций (Р-5).

План — docs/t8-4-assistant-plan-2026-10-10.md.
"""

import io
from datetime import datetime, timedelta

import pytest
from django.contrib.auth import get_user_model
from django.contrib.messages.middleware import MessageMiddleware
from django.contrib.sessions.middleware import SessionMiddleware
from django.core.files.storage import default_storage
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import RequestFactory, override_settings
from django.utils import timezone
from PIL import Image

from apps.catalog.images import delete_stored_image
from apps.promotions import limits, quick, views
from apps.promotions.models import Promotion
from apps.promotions.tasks import roll_due_promotions
from apps.promotions.tests.factories import PromotionFactory
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db


@pytest.fixture
def user(db):
    return get_user_model().objects.create_user(
        username="quick", email="quick@test.de", password="pw12345678"
    )


def _tenant(
    slug, *, profile="aktionen", status="trial", demo=False, disabled=("orders",), hours=None
):
    tenant = TenantFactory(
        schema_name=slug.replace("-", "_"),
        slug=slug,
        name=slug,
        subscription_status=status,
        is_demo=demo,
        disabled_modules=list(disabled),
    )
    if profile:
        tenant.site_config = {**(tenant.site_config or {}), "profile": profile}
    if hours is not None:
        tenant.opening_hours_structured = hours
    tenant.save()
    return tenant


def _attach(request, user, tenant=None):
    SessionMiddleware(lambda r: None).process_request(request)
    MessageMiddleware(lambda r: None).process_request(request)
    request.user = user
    if tenant is not None:
        request.tenant = tenant
    return request


def _png():
    buf = io.BytesIO()
    Image.new("RGB", (10, 10), "red").save(buf, "PNG")
    return SimpleUploadedFile("x.png", buf.getvalue(), content_type="image/png")


def _actives(n):
    for _ in range(n):
        PromotionFactory(status="active")


def _post(data, user, tenant, files=None):
    payload = {"term": "week", "customer_response": "reserve", **data}
    if files:
        payload.update(files)
    req = RequestFactory().post("/promotions/schnell/", payload)
    return views.promotion_quick(_attach(req, user, tenant))


# --- лимит Р-5 -------------------------------------------------------------------


def test_limit_only_for_free_lite_storefront():
    assert limits.active_limit(_tenant("t84-lite")) == 5
    assert limits.active_limit(_tenant("t84-paid", status="active")) is None
    assert limits.active_limit(_tenant("t84-full", profile="")) is None
    assert limits.active_limit(_tenant("t84-demo", demo=True)) is None
    assert limits.active_limit(None) is None


@override_settings(LITE_FREE_ACTIVE_PROMOS=5)
def test_sixth_activation_refused_fifth_allowed(user):
    tenant = _tenant("t84-six")
    _actives(4)
    fifth = PromotionFactory(status="draft")
    limits.activate(fifth, tenant)
    assert fifth.status == "active"
    sixth = PromotionFactory(status="draft")
    with pytest.raises(limits.ActivationLimit):
        limits.activate(sixth, tenant)
    sixth.refresh_from_db()
    assert sixth.status == "draft"
    # Черновики и запланированные — без ограничений.
    PromotionFactory(status="draft")
    PromotionFactory(status="scheduled")


def test_transition_button_refuses_over_limit_with_contact(user):
    tenant = _tenant("t84-btn")
    _actives(5)
    promo = PromotionFactory(status="draft")
    req = _attach(
        RequestFactory().post(f"/promotions/{promo.pk}/transition/", {"target": "active"}),
        user,
        tenant,
    )
    views.promotion_transition(req, pk=promo.pk)
    promo.refresh_from_db()
    assert promo.status == "draft"
    texts = [str(m) for m in req._messages]
    assert any("kontakt@siteadaptor.de" in t for t in texts)


def test_paid_tenant_activates_without_limit(user):
    tenant = _tenant("t84-paid2", status="active")
    _actives(8)
    promo = PromotionFactory(status="draft")
    limits.activate(promo, tenant)
    assert promo.status == "active"


def test_beat_keeps_scheduled_when_full_and_activates_when_free():
    from django.db import connection

    tenant = _tenant("t84-beat")
    now = timezone.now()
    actives = [PromotionFactory(status="active") for _ in range(5)]
    waiting = PromotionFactory(
        status="scheduled", starts_at=now - timedelta(minutes=5), ends_at=now + timedelta(days=1)
    )
    orig = connection.schema_name
    connection.schema_name = tenant.schema_name
    try:
        roll_due_promotions(now)
        waiting.refresh_from_db()
        assert waiting.status == "scheduled"
        # одна из активных истекла → место освободилось на том же проходе
        actives[0].ends_at = now - timedelta(minutes=1)
        actives[0].save(update_fields=["ends_at"])
        roll_due_promotions(now)
        waiting.refresh_from_db()
        assert waiting.status == "active"
    finally:
        connection.schema_name = orig


# --- срок чипами -------------------------------------------------------------------


def _at(day, hh, mm=0):
    return timezone.make_aware(
        datetime.combine(day, datetime.min.time().replace(hour=hh, minute=mm))
    )


def test_term_today_uses_closing_time_or_end_of_day():
    monday = datetime(2026, 10, 12).date()  # понедельник
    tenant = _tenant("t84-hours", hours={"0": ["08:00", "18:30"]})
    now = _at(monday, 10)
    end = timezone.localtime(quick.term_end("today", tenant, now=now))
    assert (end.hour, end.minute) == (18, 30)
    # после закрытия и без часов — конец дня
    end = timezone.localtime(quick.term_end("today", tenant, now=_at(monday, 19)))
    assert (end.hour, end.minute) == (23, 59)
    end = timezone.localtime(quick.term_end("today", _tenant("t84-nohours"), now=now))
    assert (end.date(), end.hour) == (monday, 23)


def test_term_weekend_and_week():
    wed = datetime(2026, 10, 14).date()
    now = _at(wed, 9)
    end = timezone.localtime(quick.term_end("weekend", None, now=now))
    assert end.date() == datetime(2026, 10, 18).date()  # воскресенье
    end = timezone.localtime(quick.term_end("week", None, now=now))
    assert end.date() == wed + timedelta(days=7)


# --- ассистент ---------------------------------------------------------------------


def test_assistant_publishes_promotion_with_photo_price_term_response(user):
    tenant = _tenant("t84-pub")
    resp = _post(
        {"title": "Feierabendtüte", "new_price": "5.00", "old_price": "10.00", "quantity": "8"},
        user,
        tenant,
        files={"photo": _png()},
    )
    assert resp.status_code == 302
    promo = Promotion.objects.get()
    assert resp.url == f"/promotions/{promo.pk}/fertig/"
    assert promo.status == "active"
    assert promo.title["de"] == "Feierabendtüte"
    assert str(promo.price_override) == "5.00" and str(promo.compare_at_price) == "10.00"
    assert promo.available_quantity == 8
    assert promo.metadata["response"] == "reserve"
    assert promo.ends_at > timezone.now() + timedelta(days=6)
    assert promo.gallery_images and promo.gallery_images[0]["is_primary"]
    delete_stored_image(promo.gallery_images[0])


def test_assistant_draft_button_does_not_activate(user):
    tenant = _tenant("t84-draft")
    _post({"title": "Später", "publish": "draft"}, user, tenant)
    assert Promotion.objects.get().status == "draft"


def test_assistant_over_limit_saves_draft_and_explains(user):
    tenant = _tenant("t84-full2")
    _actives(5)
    resp = _post({"title": "Sechste"}, user, tenant)
    promo = Promotion.objects.get(title__de="Sechste")
    assert promo.status == "draft"
    req = _attach(RequestFactory().get(resp.url), user, tenant)
    body = views.promotion_quick_done(req, pk=promo.pk).content.decode()
    assert "data-limit-reached" in body
    assert "mailto:" in body


def test_custom_date_in_past_is_rejected(user):
    tenant = _tenant("t84-past")
    yesterday = (timezone.localdate() - timedelta(days=1)).isoformat()
    resp = _post({"title": "X", "term": "date", "until": yesterday}, user, tenant)
    assert resp.status_code == 200
    assert not Promotion.objects.exists()


def test_price_and_percent_together_rejected(user):
    tenant = _tenant("t84-both")
    resp = _post({"title": "X", "new_price": "3.00", "percent": "20"}, user, tenant)
    assert resp.status_code == 200
    assert not Promotion.objects.exists()


def test_only_feasible_responses_offered(user):
    lite = _tenant("t84-opts", disabled=("orders", "jobs"))
    keys = [k for k, _l, _h in quick.response_options(lite)]
    # без заказов и заявок — ни «купить», ни «спросить»; купон (T-8.3) — всегда
    assert keys == ["reserve", "coupon", "show"]
    shop = _tenant("t84-opts2", profile="", disabled=())
    keys = [k for k, _l, _h in quick.response_options(shop)]
    assert keys[0] == "buy" and "inquire" in keys
    body = views.promotion_quick(
        _attach(RequestFactory().get("/promotions/schnell/"), user, lite)
    ).content.decode()
    assert 'value="buy"' not in body and 'value="inquire"' not in body
    assert 'capture="environment"' in body
    assert "data-limit-usage" in body


# --- «Wiederholen» -------------------------------------------------------------------


def test_repeat_prefills_and_copies_photo_as_own_file(user):
    from apps.catalog.images import save_product_image

    tenant = _tenant("t84-rep")
    ref = save_product_image(_png(), is_primary=True, folder="promotions")
    old = PromotionFactory(
        status="ended",
        title={"de": "Kuchen der Woche"},
        price_override="2.50",
        compare_at_price="3.20",
        images=[ref],
        metadata={"response": "show"},
    )
    body = views.promotion_quick(
        _attach(RequestFactory().get(f"/promotions/schnell/?von={old.pk}"), user, tenant)
    ).content.decode()
    assert "Kuchen der Woche" in body and "data-source-photo" in body

    _post(
        {
            "title": "Kuchen der Woche",
            "new_price": "2.50",
            "customer_response": "show",
            "photo_from": str(old.pk),
        },
        user,
        tenant,
    )
    new = Promotion.objects.exclude(pk=old.pk).get()
    assert new.gallery_images and new.gallery_images[0]["path"] != ref["path"]
    # удаление фото у старой акции не трогает новую
    delete_stored_image(ref)
    assert default_storage.exists(new.gallery_images[0]["path"])
    delete_stored_image(new.gallery_images[0])


def test_list_shows_quick_entry_repeat_and_counters(user):
    tenant = _tenant("t84-list")
    PromotionFactory(status="ended", title={"de": "Alt"})
    PromotionFactory(status="active", title={"de": "Neu"})
    body = views.promotion_list(
        _attach(RequestFactory().get("/promotions/"), user, tenant)
    ).content.decode()
    assert "/promotions/schnell/" in body and "data-quick-fab" in body
    assert body.count("data-repeat") == 1  # только у прошлой акции
    assert "data-promo-counters" in body
    assert "data-limit-usage" in body


def test_done_screen_for_active_has_link_qr_and_share(user):
    tenant = _tenant("t84-done", status="active")
    promo = PromotionFactory(status="active", title={"de": "Brot"})
    body = views.promotion_quick_done(
        _attach(RequestFactory().get(f"/promotions/{promo.pk}/fertig/"), user, tenant), pk=promo.pk
    ).content.decode()
    assert f"/p/{promo.pk}/qr.svg" in body
    assert "data-copy-link" in body and "wa.me" in body


# --- T-8.5b: несколько фото, переводы, «Bearbeiten» ---------------------------------


def test_several_photos_first_is_title_and_too_many_refused(user):
    from apps.promotions import quick

    tenant = _tenant("t85b-photos")
    resp = _post(
        {"title": "Drei Fotos", "new_price": "3"},
        user,
        tenant,
        files={"photo": [_png(), _png(), _png()]},
    )
    assert resp.status_code == 302
    promo = Promotion.objects.get()
    assert len(promo.gallery_images) == 3
    assert [i["is_primary"] for i in promo.gallery_images] == [True, False, False]
    assert [i["sort_order"] for i in promo.gallery_images] == [0, 1, 2]
    for ref in promo.gallery_images:
        delete_stored_image(ref)

    many = [_png() for _ in range(quick.MAX_PHOTOS + 1)]
    resp = _post({"title": "Zu viele", "new_price": "3"}, user, tenant, files={"photo": many})
    assert resp.status_code == 200 and Promotion.objects.count() == 1


def test_repeat_copies_all_photos(user):
    from apps.catalog.images import save_product_image

    tenant = _tenant("t85b-rep")
    refs = [
        save_product_image(_png(), is_primary=(i == 0), sort_order=i, folder="promotions")
        for i in range(2)
    ]
    old = PromotionFactory(status="ended", title={"de": "Zwei"}, images=refs)
    _post({"title": "Zwei", "new_price": "2", "photo_from": str(old.pk)}, user, tenant)
    new = Promotion.objects.exclude(pk=old.pk).get()
    assert len(new.gallery_images) == 2 and new.gallery_images[0]["is_primary"]
    assert {i["path"] for i in new.gallery_images}.isdisjoint({r["path"] for r in refs})
    for ref in [*refs, *new.gallery_images]:
        delete_stored_image(ref)


def test_done_screen_offers_edit_and_translation_links(user):
    tenant = _tenant("t85b-done")
    tenant.enabled_locales = ["de", "en", "ru"]
    tenant.save(update_fields=["enabled_locales"])
    promo = PromotionFactory(status="active", title={"de": "Brot"})
    body = views.promotion_quick_done(
        _attach(RequestFactory().get(f"/promotions/{promo.pk}/fertig/"), user, tenant), pk=promo.pk
    ).content.decode()
    assert "data-quick-edit" in body and f"/promotions/{promo.pk}/edit/" in body
    assert f"/promotions/{promo.pk}/edit/?sprache=en" in body
    assert f"/promotions/{promo.pk}/edit/?sprache=ru" in body
    assert 'data-translate-link="de"' not in body  # базовый язык не переводится


def test_done_screen_asks_for_opening_hours_until_they_are_set(user):
    """T-8.23b: без часов работы — подсказка «Öffnungszeiten ergänzen» на «Fertig»."""
    tenant = _tenant("t823-hours")
    promo = PromotionFactory(status="active", title={"de": "Brot"})

    def body():
        req = _attach(RequestFactory().get(f"/promotions/{promo.pk}/fertig/"), user, tenant)
        return views.promotion_quick_done(req, pk=promo.pk).content.decode()

    # T-8.32b: у лёгкого пакета полных настроек нет — часы правятся в «Geschäft».
    assert "data-missing-hours" in body() and "/dashboard/geschaeft/" in body()
    tenant.opening_hours = "Mo–Fr 7–18 Uhr"
    tenant.save(update_fields=["opening_hours"])
    assert "data-missing-hours" not in body()


# --- T-8.23d: акция всегда от товара ------------------------------------------------


def test_quick_promo_creates_product_from_the_same_data(user):
    from decimal import Decimal

    from apps.catalog.models import Category

    tenant = _tenant("t823d-new")
    resp = _post(
        {
            "title": "Bauernbrot 1 kg",
            "new_price": "3",
            "old_price": "4.50",
            "quantity": "5",
            "sku": "BR-01",
            "category": "__new",
            "new_category": "Brot",
        },
        user,
        tenant,
        files={"photo": _png()},
    )
    assert resp.status_code == 302
    promo = Promotion.objects.get(title__de="Bauernbrot 1 kg")
    product = promo.product
    assert product is not None and product.name_text == "Bauernbrot 1 kg"
    assert product.base_price == Decimal("4.50") and product.sku == "BR-01"
    assert product.category == Category.objects.get(slug__startswith="brot")
    assert product.stock_quantity is None  # S1: остатки не ведутся, штуки — в акции
    assert promo.available_quantity == 5
    # фото переехали в товар; витрина акции берёт их и цену «statt» у товара
    assert promo.images == [] and len(product.images) == 1
    assert promo.primary_image == product.primary_image
    assert promo.old_price == Decimal("4.50") and promo.new_price == Decimal("3")
    for ref in product.images:
        delete_stored_image(ref)


def test_quick_promo_for_existing_product_links_it(user):
    from apps.catalog.tests.factories import ProductFactory

    tenant = _tenant("t823d-old")
    product = ProductFactory(base_price="10")
    _post({"title": "Wochenknaller", "new_price": "7", "product": str(product.pk)}, user, tenant)
    promo = Promotion.objects.get(title__de="Wochenknaller")
    assert promo.product_id == product.pk
    from apps.catalog.models import Product

    assert Product.objects.count() == 1  # нового товара нет
    assert str(promo.old_price) == "10.00"  # «statt» — цена товара


def test_percent_only_promo_stays_without_product(user):
    tenant = _tenant("t823d-pct")
    _post({"title": "20 % auf alles", "percent": "20"}, user, tenant)
    assert Promotion.objects.get(title__de="20 % auf alles").product_id is None


def test_aktion_from_product_opens_short_assistant_prefilled(user):
    from apps.catalog.tests.factories import ProductFactory

    tenant = _tenant("t823d-pre")
    product = ProductFactory(name={"de": "Kaffee 500 g"}, base_price="8.90")
    req = _attach(
        RequestFactory().get("/promotions/schnell/", {"product": product.pk}), user, tenant
    )
    body = views.promotion_quick(req).content.decode()
    assert 'value="Kaffee 500 g"' in body
    assert f'<option value="{product.pk}" selected' in body
    assert 'value="8.90"' in body


def test_convert_lite_promotions_turns_free_promos_into_products(monkeypatch):
    """S3: свободные акции лёгких магазинов → товар + акция; модуль акций включается."""
    import contextlib

    from django.core.management import call_command

    from apps.promotions.management.commands import convert_lite_promotions as cmd

    monkeypatch.setattr(cmd, "tenant_context", lambda t: contextlib.nullcontext())
    tenant = _tenant("t823s3", disabled=("orders", "promotions"))
    free = PromotionFactory(
        title={"de": "Maus"}, price_override="10", compare_at_price="50", images=[]
    )
    pct = PromotionFactory(title={"de": "20 %"}, price_override=None, compare_at_price=None)

    call_command("convert_lite_promotions")  # пробный прогон ничего не меняет
    free.refresh_from_db()
    assert free.product_id is None

    call_command("convert_lite_promotions", "--apply")
    free.refresh_from_db()
    pct.refresh_from_db()
    assert free.product is not None and free.product.name_text == "Maus"
    assert str(free.product.base_price) == "50.00"
    assert pct.product_id is None  # без цены товар не создать
    tenant.refresh_from_db()
    assert "promotions" not in tenant.disabled_modules

    call_command("convert_lite_promotions", "--apply")  # повтор — без дублей
    from apps.catalog.models import Product

    assert Product.objects.count() == 1


@pytest.mark.parametrize("enabled", [True, False])
def test_done_screen_offers_next_promo_with_ai_only_when_enabled(user, settings, enabled):
    settings.AI_ENABLED = enabled
    tenant = _tenant(f"t-ai-done-{int(enabled)}", status="active")
    promo = PromotionFactory(status="active", title={"de": "Brot"})
    body = views.promotion_quick_done(
        _attach(RequestFactory().get(f"/promotions/{promo.pk}/fertig/"), user, tenant), pk=promo.pk
    ).content.decode()
    assert ("Nächste Aktion mit KI" in body) is enabled
