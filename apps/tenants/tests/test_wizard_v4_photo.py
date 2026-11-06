"""AIS W4-4: «Foto der Speisekarte / Preisliste» в шаге v4 «Angebot prüfen».

Путь: фото → «Foto lesen» (фоновая задача) → «Ergebnis anzeigen» (POST) → та же таблица
«Prüfen» → «Übernehmen». План — docs/ais-w4-4-photo-lines-plan-2026-11-06.md §5."""

import io
import json
from types import SimpleNamespace
from unittest import mock

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import RequestFactory
from PIL import Image

from apps.catalog.models import Product
from apps.core import offer_batch, offer_photo, tasks
from apps.core import views as core_views
from apps.tenants.tests.test_wizard_v4_pruefen import Owner, _confirm_data, _v4

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _tenant_urlconf(settings):
    settings.ROOT_URLCONF = "config.urls_tenant"


@pytest.fixture
def ai_task_on(settings, isolated_ratelimit):
    settings.AI_ENABLED = True
    settings.AI_REQUIRE_EU = False
    settings.AI_ROUTE_STRONG = ["fake"]
    settings.AI_TASKS_ENABLED = [*settings.AI_TASKS_ENABLED, offer_photo.TASK]
    return settings


ITEMS = {
    "is_price_list": True,
    "items": [
        {"name": "Roggenbrot", "price_text": "3,50 €"},
        {"name": "Butterbrezel", "price_text": "1,20 €"},
        {"name": "Torte des Tages", "price_text": ""},
    ],
}


def _jpeg(name="karte.jpg"):
    buf = io.BytesIO()
    Image.new("RGB", (80, 60), (200, 200, 200)).save(buf, "JPEG")
    return SimpleUploadedFile(name, buf.getvalue(), content_type="image/jpeg")


def _inline(data=ITEMS):
    """Celery синхронно, ИИ — заданным ответом."""
    run = mock.patch.object(
        tasks.offer_photo_lines, "delay", side_effect=lambda **kw: tasks.offer_photo_lines(**kw)
    )
    gen = mock.patch.object(offer_photo, "generate", return_value=SimpleNamespace(data=data))
    return run, gen


def _scan(owner, files=None, text="", kind="waren"):
    return owner(
        "post",
        {
            "action": "offer_scan",
            "kind": kind,
            "offer_text": text,
            "menu_photo": files if files is not None else [_jpeg()],
        },
    )


def test_without_ai_no_photo_block_and_step_works(settings):
    settings.AI_ENABLED = False
    owner = Owner(_v4())
    html = owner().content.decode()
    assert "data-pruefen-scan>" not in html
    assert 'name="menu_photo"' not in html
    assert "data-pruefen-form" in html
    _scan(owner)
    assert offer_photo.SESSION_KEY not in owner.session
    assert any("nicht verfügbar" in m for m in owner.messages)


def test_photo_block_shown_when_enabled(ai_task_on):
    html = Owner(_v4())().content.decode()
    assert 'name="menu_photo"' in html and 'value="offer_scan"' in html
    assert 'enctype="multipart/form-data"' in html
    assert "{% ai_notice" not in html  # тег отрендерен (на фейке вне ЕС пометки нет)


def test_us_route_shows_ai_notice(ai_task_on):
    ai_task_on.AI_ROUTE_STRONG = ["anthropic"]
    assert "data-ai-notice" in Owner(_v4())().content.decode()


def test_full_path_nothing_created_until_confirm(ai_task_on):
    owner = Owner(_v4())
    run, gen = _inline()
    with run, gen:
        _scan(owner)
    assert offer_photo.SESSION_KEY in owner.session
    html = owner().content.decode()
    assert "data-pruefen-scan-wait" in html and "data-pruefen-scan-apply" in html
    owner("post", {"action": "offer_scan_apply"})
    draft = owner.session[offer_batch.SESSION_KEY]
    assert draft["source"] == "photo" and draft["batch"]
    assert "Roggenbrot — 3,50 €" in draft["text"] and "Torte des Tages — ?" in draft["text"]
    assert Product.objects.count() == 0
    html = owner().content.decode()
    assert "data-pruefen-from-photo" in html and "data-pruefen-review" in html
    assert "Preis fehlt" in html  # строка без цены не получила выдуманной
    rows = [
        {"on": "1", "name": "Roggenbrot", "price": "3,50"},
        {"on": "1", "name": "Butterbrezel", "price": "1,20"},
        {"name": "Torte des Tages", "price": ""},
    ]
    owner("post", _confirm_data(owner, rows))
    assert set(Product.objects.values_list("name__de", flat=True)) == {"Roggenbrot", "Butterbrezel"}


def test_double_scan_starts_one_job(ai_task_on):
    owner = Owner(_v4())
    with mock.patch.object(tasks.offer_photo_lines, "delay") as delay:
        _scan(owner)
        _scan(owner)
    assert delay.call_count == 1
    assert any("schon gelesen" in m for m in owner.messages)


def test_double_apply_gives_one_draft(ai_task_on):
    owner = Owner(_v4())
    run, gen = _inline()
    with run, gen:
        _scan(owner)
    stale = dict(owner.session)  # вторая вкладка держит указатель на ту же задачу
    owner("post", {"action": "offer_scan_apply"})
    assert owner.session[offer_batch.SESSION_KEY]["source"] == "photo"
    owner.session = stale
    owner("post", {"action": "offer_scan_apply"})
    # Результат одноразовый: вторая вкладка черновик не создаёт и ошибкой не пугает.
    assert offer_batch.SESSION_KEY not in owner.session
    assert owner.messages == []


def test_right_removed_between_scan_and_apply(ai_task_on, monkeypatch):
    owner = Owner(_v4())
    run, gen = _inline()
    with run, gen:
        _scan(owner)
    monkeypatch.setattr(offer_batch, "offer_kinds", lambda tenant, user: [])
    owner("post", {"action": "offer_scan_apply"})
    assert offer_batch.SESSION_KEY not in owner.session
    assert any("Berechtigung" in m for m in owner.messages)


def test_kind_not_allowed_for_scan(ai_task_on):
    owner = Owner(_v4())
    with mock.patch.object(tasks.offer_photo_lines, "delay") as delay:
        _scan(owner, kind="tickets")
    assert delay.call_count == 0
    assert any("Berechtigung" in m for m in owner.messages)


def test_too_many_or_not_image_refused_without_spending_limit(ai_task_on):
    from apps.core import ratelimit

    owner = Owner(_v4())
    with (
        mock.patch.object(tasks.offer_photo_lines, "delay") as delay,
        mock.patch.object(ratelimit, "hit", return_value=False) as hit,
    ):
        _scan(owner, files=[_jpeg(f"{i}.jpg") for i in range(4)])
        assert any("Höchstens 3" in m for m in owner.messages)
        pdf = SimpleUploadedFile("karte.pdf", b"%PDF-1.4 x", content_type="application/pdf")
        _scan(owner, files=[pdf])
        assert any("nicht lesbar" in m for m in owner.messages)
        _scan(owner, files=[])
    assert delay.call_count == 0 and hit.call_count == 0


def test_rate_limit_gives_quota(ai_task_on):
    from apps.core import ratelimit

    owner = Owner(_v4())
    with (
        mock.patch.object(tasks.offer_photo_lines, "delay") as delay,
        mock.patch.object(ratelimit, "hit", return_value=True),
    ):
        _scan(owner)
    assert delay.call_count == 0
    assert any("Zu viele Fotos" in m for m in owner.messages)


def test_broker_down_is_calm_and_cache_clean(ai_task_on):
    owner = Owner(_v4())
    with mock.patch.object(tasks.offer_photo_lines, "delay", side_effect=OSError("down")):
        _scan(owner)
    assert offer_photo.SESSION_KEY not in owner.session
    assert any("nicht verfügbar" in m for m in owner.messages)


def test_failed_reading_is_reported(ai_task_on):
    owner = Owner(_v4())
    run, gen = _inline({"is_price_list": False, "items": []})
    with run, gen:
        _scan(owner)
    assert "data-pruefen-scan-wait" in owner().content.decode()
    owner("post", {"action": "offer_scan_apply"})
    assert offer_photo.SESSION_KEY not in owner.session
    assert any("keine Preisliste" in m for m in owner.messages)


def test_typed_text_is_kept_and_back_to_text_keeps_flag(ai_task_on):
    owner = Owner(_v4())
    run, gen = _inline()
    with run, gen:
        _scan(owner, text="Bauernbrot — 4,20 €\nRoggenbrot — 3,50 €")
    owner("post", {"action": "offer_scan_apply"})
    text = owner.session[offer_batch.SESSION_KEY]["text"]
    assert text.startswith("Bauernbrot — 4,20 €")
    assert "Butterbrezel" in text
    assert "Doppelt" in owner().content.decode()  # Roggenbrot дважды — таблица пометила
    owner("post", {"action": "offer_edit"})
    assert owner.session[offer_batch.SESSION_KEY]["source"] == "photo"
    owner("post", {"action": "offer_preview", "kind": "waren", "offer_text": text})
    assert owner.session[offer_batch.SESSION_KEY]["source"] == "photo"
    owner("post", {"action": "offer_examples", "kind": "waren"})
    assert "source" not in owner.session[offer_batch.SESSION_KEY]


def _poll(owner, method="get"):
    request = getattr(RequestFactory(), method)("/dashboard/setup/foto/")
    from django.contrib.sessions.middleware import SessionMiddleware

    SessionMiddleware(lambda r: None).process_request(request)
    if owner.session:
        request.session.update(owner.session)
        request.session.modified = False
    request.tenant = owner.tenant
    request.user = owner.user
    return request, core_views.setup_offer_photo_state(request)


def test_poll_endpoint_reads_only(ai_task_on):
    owner = Owner(_v4())
    owner()
    _req, resp = _poll(owner)
    assert json.loads(resp.content) == {"state": "none"}
    with mock.patch.object(tasks.offer_photo_lines, "delay"):
        _scan(owner)
    req, resp = _poll(owner)
    assert json.loads(resp.content) == {"state": "pending"}
    assert req.session.modified is False
    _req, resp = _poll(owner, "post")
    assert resp.status_code == 405


def test_poll_endpoint_requires_login():
    from django.contrib.auth.models import AnonymousUser

    request = RequestFactory().get("/dashboard/setup/foto/")
    request.user = AnonymousUser()
    resp = core_views.setup_offer_photo_state(request)
    assert resp.status_code == 302
