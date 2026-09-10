"""LAY-6d — переводы списков не «съезжают» при правке базы.

`faq`, `testimonials`, `process`, `team` оверлеятся ПОЗИЦИОННО (`_deep_overlay`
мёржит списки по индексу). Пока владелец только добавляет в конец, это работает.
Стоит ему удалить второй вопрос или поменять порядок — переводы садятся на чужие
элементы: русский ответ появляется под немецким вопросом, к которому не относится.

Дефект существует уже сегодня (демо-переводы кладутся сидингом), а с LAY-6b, когда
переводы начнёт писать и владелец, он станет массовым. У моделей задача решена
приёмом `core.i18n_seq.apply_seq_overlay` (волна I18N-12) — здесь нужен тот же.

Замки написаны ДО правок и краснеют на текущем коде.
"""

import pytest

from apps.tenants import siteconfig

pytestmark = pytest.mark.django_db


def _cfg(faq, ru):
    return {"faq": faq, "i18n": {"ru": {"faq": ru}}}


def test_removing_an_item_keeps_the_remaining_translations_aligned():
    """Удалили ПЕРВЫЙ вопрос — перевод второго остаётся при своём вопросе."""
    old = [{"q": "Parkplatz?", "a": "Ja."}, {"q": "Lieferung?", "a": "Ab 30 €."}]
    ru = [{"q": "Парковка?", "a": "Да."}, {"q": "Доставка?", "a": "От 30 €."}]
    new = [{"q": "Lieferung?", "a": "Ab 30 €."}]
    cfg = siteconfig.realign_list_overlays(_cfg(old, ru), {"faq": new}, key_fields={"faq": "q"})
    assert cfg["i18n"]["ru"]["faq"] == [{"q": "Доставка?", "a": "От 30 €."}]


def test_reordering_items_moves_the_translations_with_them():
    old = [{"q": "A?", "a": "1"}, {"q": "B?", "a": "2"}]
    ru = [{"q": "А?", "a": "1ru"}, {"q": "Б?", "a": "2ru"}]
    new = [{"q": "B?", "a": "2"}, {"q": "A?", "a": "1"}]
    cfg = siteconfig.realign_list_overlays(_cfg(old, ru), {"faq": new}, key_fields={"faq": "q"})
    assert cfg["i18n"]["ru"]["faq"] == [{"q": "Б?", "a": "2ru"}, {"q": "А?", "a": "1ru"}]


def test_new_item_gets_no_translation_and_does_not_steal_one():
    old = [{"q": "A?", "a": "1"}]
    ru = [{"q": "А?", "a": "1ru"}]
    new = [{"q": "Neu?", "a": "x"}, {"q": "A?", "a": "1"}]
    cfg = siteconfig.realign_list_overlays(_cfg(old, ru), {"faq": new}, key_fields={"faq": "q"})
    assert cfg["i18n"]["ru"]["faq"] == [{}, {"q": "А?", "a": "1ru"}]


def test_config_without_overlay_is_untouched():
    """Без переводов функция ничего не создаёт (presence-minimal)."""
    cfg = siteconfig.realign_list_overlays({"faq": [{"q": "A?"}]}, {"faq": [{"q": "B?"}]})
    assert "i18n" not in cfg


def test_builder_save_realigns_the_overlay():
    """Сквозной путь: Save билдера с удалённым вопросом не сбивает переводы."""
    from types import SimpleNamespace

    from django.contrib.messages.middleware import MessageMiddleware
    from django.contrib.sessions.middleware import SessionMiddleware
    from django.test import RequestFactory

    from apps.core import views
    from apps.tenants.tests.factories import TenantFactory

    tenant = TenantFactory(schema_name="public", slug="lay6d", name="LAY6D")
    tenant.site_config = siteconfig.normalize(
        _cfg(
            [{"q": "Parkplatz?", "a": "Ja."}, {"q": "Lieferung?", "a": "Ab 30 €."}],
            [{"q": "Парковка?", "a": "Да."}, {"q": "Доставка?", "a": "От 30 €."}],
        )
    )
    tenant.save(update_fields=["site_config"])

    req = RequestFactory().post(
        "/dashboard/site/home/",
        {
            "content_sections_present": "1",
            "faq_present": "1",
            "faq_q_0": "Lieferung?",
            "faq_a_0": "Ab 30 €.",
        },
    )
    SessionMiddleware(lambda r: None).process_request(req)
    MessageMiddleware(lambda r: None).process_request(req)
    req.user = SimpleNamespace(is_authenticated=True)
    req.tenant = tenant
    assert views.home_builder_view(req).status_code == 302
    tenant.refresh_from_db()
    assert tenant.site_config["faq"] == [{"q": "Lieferung?", "a": "Ab 30 €."}]
    assert tenant.site_config["i18n"]["ru"]["faq"] == [{"q": "Доставка?", "a": "От 30 €."}]
