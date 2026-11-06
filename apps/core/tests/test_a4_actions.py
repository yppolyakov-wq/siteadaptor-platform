# ruff: noqa: F811 — фикстуры из test_assistant_a2 импортируются и переопределяются параметрами
"""AIS A-4a: пакет «создать» из помощника — предпросмотр, «Alles übernehmen», «Rückgängig».

Замки (план docs/ais-a4-ki-actions-plan-2026-11-06.md §5, §8):
* реестр закрыт: только *.create, ни одного объекта/глагола из запретного списка;
* до клика в базе ничего; пакет — только из кэша задачи (не из POST и не из истории);
* POST меняет только значения полей и галочки; двойной POST — один пакет;
* всё или ничего; без права — без кнопки и без записи; чужой job — нечего применять;
* откат: только автор, окно 10 минут, по снимку полей, в обратном порядке, стартовый
  остаток склада и первая запись журнала цен — свои строки; проданное не удаляется.
"""

from datetime import timedelta
from decimal import Decimal
from unittest import mock

import pytest
from django.utils import timezone

from apps.catalog.models import Category, Product
from apps.core import assistant_actions, assistant_views
from apps.core.models import AssistantChange, AssistantTurn
from apps.core.tests.test_assistant_a2 import (  # noqa: F401 — фикстуры и хелперы
    _ask,
    _clean,
    _req,
    _urlconf,
    _user,
    bakery,
    isolated_ratelimit,
)
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db

KUCHEN = "neue Kategorie Kuchen, Produkt Käsekuchen 3,20 € in Kuchen"


@pytest.fixture
def ai_off(settings, isolated_ratelimit):  # noqa: F811
    settings.AI_ENABLED = False
    return settings


def _html(tenant, user, job):
    resp = assistant_views.assistant_answer(_req(tenant, user=user, drawer=True), job)
    return resp.content.decode()


def _apply(tenant, user, job, data=None, drawer=True):
    return assistant_views.assistant_apply(
        _req(tenant, "post", data or {}, user=user, drawer=drawer), job
    )


def _undo(tenant, user, job):
    return assistant_views.assistant_undo(_req(tenant, "post", {}, user=user, drawer=True), job)


def _kuchen(tenant):
    user, got = _ask(tenant, KUCHEN)
    return user, got["job"]


# ── реестр ──────────────────────────────────────────────────────────────────────────


def test_registry_is_closed():
    """A-4b: реестр расширен изменениями, но по-прежнему ЗАКРЫТ — точный список действий,
    ни одного объекта/глагола из запретного списка; цена — только правом preise.edit."""
    assert set(assistant_actions.ACTIONS) == {
        "category.create",
        "product.create",
        "service.create",
        "product.price",
        "service.price",
        "product.visibility",
        "service.visibility",
        "category.visibility",
        "product.move",
        "page.setting",
    }
    for key, spec in assistant_actions.ACTIONS.items():
        obj, verb = key.split(".")
        assert obj not in assistant_actions.FORBIDDEN_OBJECTS
        assert verb not in assistant_actions.FORBIDDEN_VERBS
        assert spec.perm and spec.screen and spec.edit_screen
        # модуль — у всех, кроме настройки страницы (её тип проверяет page_settings.validate)
        assert spec.module or spec.verb == "page"
        if spec.verb == "create":
            assert any(f.name == "name" and f.required for f in spec.fields)
        if spec.verb == "price":
            assert spec.perm == "preise.edit"


# ── предпросмотр ────────────────────────────────────────────────────────────────────


def test_package_is_previewed_and_nothing_is_written(ai_off, bakery):
    user, job = _kuchen(bakery)
    html = _html(bakery, user, job)
    assert "data-assistant-apply" in html and "Alles übernehmen" in html
    assert 'value="Käsekuchen"' in html and 'value="3,20"' in html
    assert 'value="item:0" selected' in html  # категория — новая из того же пакета
    assert not Category.objects.exists() and not Product.objects.exists()
    assert not AssistantChange.objects.exists()


def test_history_keeps_no_package(ai_off, bakery):
    user, job = _kuchen(bakery)
    entry = AssistantTurn.objects.get(job=job).entry
    assert "actions" not in entry and "job" not in entry
    html = assistant_views.assistant_view(_req(bakery, user=user)).content.decode()
    assert html.count("data-assistant-apply") <= 1  # из истории применить нельзя


def test_no_right_no_button(ai_off, bakery, monkeypatch):
    user, job = _kuchen(bakery)
    monkeypatch.setattr(
        assistant_actions, "allowed", lambda request, spec: (False, "keine Berechtigung")
    )
    html = _html(bakery, user, job)
    assert "data-assistant-action-blocked" in html and "data-assistant-apply-btn" not in html
    _apply(bakery, user, job, {"items_present": "1", "take_0": "1", "take_1": "1"})
    assert not Product.objects.exists() and not AssistantChange.objects.exists()


# ── применение ──────────────────────────────────────────────────────────────────────


def test_apply_creates_through_screen_writers(ai_off, bakery):
    user, job = _kuchen(bakery)
    resp = _apply(bakery, user, job, {"items_present": "1", "take_0": "1", "take_1": "1"})
    html = resp.content.decode()
    cat = Category.objects.get()
    product = Product.objects.get()
    assert product.category_id == cat.pk and product.base_price == Decimal("3.20")
    assert product.is_active and product.vat_rate == Decimal("7.00")  # как экран создания
    assert "data-assistant-applied" in html and "Rückgängig" in html
    change = AssistantChange.objects.get(job=job)
    assert [i["action"] for i in change.items] == ["category.create", "product.create"]


def test_post_edits_values_but_not_the_action(ai_off, bakery):
    user, job = _kuchen(bakery)
    _apply(
        bakery,
        user,
        job,
        {
            "items_present": "1",
            "take_1": "1",  # категорию не берём
            "f_1_name": "Käsekuchen groß",
            "f_1_price": "4,10",
            "f_1_category": "",
            "f_0_action": "order.delete",  # подмена — не поле спеки
        },
    )
    assert not Category.objects.exists()
    product = Product.objects.get()
    assert product.get_i18n("name") == "Käsekuchen groß" and product.base_price == Decimal("4.10")


def test_new_category_reference_requires_the_category(ai_off, bakery):
    user, job = _kuchen(bakery)
    _apply(bakery, user, job, {"items_present": "1", "take_1": "1"})  # item:0 не взят
    assert not Product.objects.exists() and not AssistantChange.objects.exists()


def test_double_post_applies_once(ai_off, bakery):
    user, job = _kuchen(bakery)
    data = {"items_present": "1", "take_0": "1", "take_1": "1"}
    _apply(bakery, user, job, data)
    _apply(bakery, user, job, data)
    assert Product.objects.count() == 1 and AssistantChange.objects.count() == 1


def test_all_or_nothing(ai_off, bakery, monkeypatch):
    from apps.catalog import writers

    user, job = _kuchen(bakery)

    def boom(*a, **k):
        raise writers.WriteError({"base_price": [{"message": "kaputt"}]})

    monkeypatch.setattr(writers, "create_product", boom)
    html = _apply(bakery, user, job, {"items_present": "1", "take_0": "1", "take_1": "1"})
    assert not Category.objects.exists() and not AssistantChange.objects.exists()
    assert "kaputt" in _html(bakery, user, job) or "kaputt" in html.content.decode()


def test_invalid_input_is_kept_with_error(ai_off, bakery):
    user, job = _kuchen(bakery)
    _apply(
        bakery, user, job, {"items_present": "1", "take_0": "1", "take_1": "1", "f_1_price": "abc"}
    )
    html = _html(bakery, user, job)
    assert 'value="abc"' in html and 'aria-invalid="true"' in html
    assert not Product.objects.exists()


def test_foreign_job_has_nothing_to_apply(ai_off, bakery):
    _owner, job = _kuchen(bakery)
    stranger = _user()
    _apply(bakery, stranger, job, {"items_present": "1", "take_0": "1", "take_1": "1"})
    assert not Product.objects.exists()


def test_expired_package(ai_off, bakery):
    html = _apply(bakery, _user(), "0" * 32).content.decode()
    assert "abgelaufen" in html


def test_lock_timeout_is_a_calm_message(ai_off, bakery, monkeypatch):
    from django.db import OperationalError

    user, job = _kuchen(bakery)

    class _Pg(Exception):
        sqlstate = "55P03"

    err = OperationalError("lock")
    err.__cause__ = _Pg()

    def busy(_tenant):
        raise err

    monkeypatch.setattr(assistant_actions, "_lock_tenant", busy)
    html = _apply(bakery, user, job, {"items_present": "1", "take_0": "1"}).content.decode()
    assert "Benutzung" in html and not Category.objects.exists()


def test_without_js_redirects_to_the_helper(ai_off, bakery):
    user, job = _kuchen(bakery)
    resp = _apply(bakery, user, job, {"items_present": "1", "take_0": "1"}, drawer=False)
    assert resp.status_code == 302 and f"antwort={job}" in resp["Location"]


def test_service_package_needs_booking(ai_off, isolated_ratelimit):  # noqa: F811
    from apps.booking.models import Service

    salon = TenantFactory(schema_name="public", business_type="friseur", name="Salon")
    user, got = _ask(salon, "neue Leistung Damenschnitt 45 €, 60 Minuten")
    _apply(salon, user, got["job"], {"items_present": "1", "take_0": "1"})
    service = Service.objects.get()
    assert service.price_cents == 4500 and service.duration_minutes == 60


# ── откат ───────────────────────────────────────────────────────────────────────────


def _applied(tenant):
    user, job = _kuchen(tenant)
    _apply(tenant, user, job, {"items_present": "1", "take_0": "1", "take_1": "1"})
    return user, job


def test_undo_in_reverse_order_with_own_stock_row(ai_off, bakery):
    user, job = _applied(bakery)
    _undo(bakery, user, job)
    assert not Product.objects.exists() and not Category.objects.exists()  # мягко удалены
    assert Product.all_objects.count() == 1
    change = AssistantChange.objects.get(job=job)
    assert change.undone_at and all(r["done"] for r in change.undo_report)


def test_undo_skips_changed_object(ai_off, bakery):
    user, job = _applied(bakery)
    Product.objects.update(base_price=Decimal("9.99"))
    _undo(bakery, user, job)
    assert Product.objects.count() == 1  # изменён вручную — остаётся
    assert Category.objects.count() == 1  # в ней живой товар — тоже остаётся


def test_undo_keeps_sold_product(ai_off, bakery):
    user, job = _applied(bakery)
    with mock.patch.object(assistant_actions, "_has_links", return_value=True):
        _undo(bakery, user, job)
    assert Product.objects.count() == 1


def test_undo_only_by_author_and_in_window(ai_off, bakery):
    user, job = _applied(bakery)
    _undo(bakery, _user(), job)  # чужой
    assert Product.objects.count() == 1
    AssistantChange.objects.update(undo_until=timezone.now() - timedelta(seconds=1))
    html = _undo(bakery, user, job).content.decode()
    assert Product.objects.count() == 1 and "10 Minuten" in html


def test_undo_twice_is_noop(ai_off, bakery):
    user, job = _applied(bakery)
    _undo(bakery, user, job)
    _undo(bakery, user, job)
    assert AssistantChange.objects.get(job=job).undone_at


def test_purge_removes_old_changes(ai_off, bakery):
    _user_, job = _applied(bakery)
    AssistantChange.objects.update(applied_at=timezone.now() - timedelta(days=400))
    assert assistant_actions.purge() == 1


def test_in_tail_stays_in_the_name_when_it_is_no_category(ai_off, bakery):
    user, got = _ask(bakery, "Produkt Brot in Scheiben 2,50 €")
    html = _html(bakery, user, got["job"])
    assert "Scheiben" in html  # «in Scheiben» — часть названия, а не категория


# ── ревью A-4a (django / security / database / a11y) ────────────────────────────────


def test_whole_euro_price_can_be_undone(ai_off, bakery):
    user, got = _ask(bakery, "Produkt Roggenbrot 5 €")
    _apply(bakery, user, got["job"], {"items_present": "1", "take_0": "1"})
    assert Product.objects.get().base_price == Decimal("5.00")
    _undo(bakery, user, got["job"])  # снимок «5.00», а не «5» — не «inzwischen geändert»
    assert not Product.objects.exists()


def test_nothing_undone_keeps_the_retry(ai_off, bakery):
    user, job = _applied(bakery)
    Product.objects.update(base_price=Decimal("9.99"))
    _undo(bakery, user, job)
    change = AssistantChange.objects.get(job=job)
    assert change.undone_at is None  # ничего не откатилось — пакет не помечен
    assert change.undo_report and not any(r["done"] for r in change.undo_report)
    Product.objects.update(base_price=Decimal("3.20"))  # владелец вернул цену
    _undo(bakery, user, job)  # повтор в том же окне откатывает
    assert not Product.objects.exists() and not Category.objects.exists()


def test_screen_gate_applies_to_actions(ai_off, bakery, monkeypatch):
    """Mini App / пакет: ассистент не создаёт то, чего не открыл бы экран создания."""
    from apps.core import setup_assistant

    user, job = _kuchen(bakery)
    monkeypatch.setattr(
        setup_assistant, "reachable", lambda request, name: name != "catalog:category-create"
    )
    html = _html(bakery, user, job)
    assert "data-assistant-action-blocked" in html
    _apply(bakery, user, job, {"items_present": "1", "take_0": "1", "take_1": "1"})
    assert not Category.objects.exists()


def test_failed_link_check_keeps_the_object(ai_off, bakery, monkeypatch):
    from apps.core import models as core_models

    user, job = _applied(bakery)

    def boom(*a, **k):
        raise RuntimeError("db hiccup")

    monkeypatch.setattr(core_models.Extra.objects, "filter", boom)
    _undo(bakery, user, job)
    assert Product.objects.count() == 1  # не смогли проверить — не удаляем


def test_unticked_item_stays_unticked_after_error(ai_off, bakery):
    user, job = _kuchen(bakery)
    _apply(bakery, user, job, {"items_present": "1", "take_0": "1", "f_0_name": ""})
    html = _html(bakery, user, job)
    assert 'name="take_0" value="1" checked' in html
    assert 'name="take_1" value="1" checked' not in html


def test_price_with_three_decimals_is_rejected_before_writing(ai_off, bakery):
    user, job = _kuchen(bakery)
    _apply(bakery, user, job, {"items_present": "1", "take_1": "1", "f_1_price": "3,999"})
    assert not Product.objects.exists() and 'aria-invalid="true"' in _html(bakery, user, job)
