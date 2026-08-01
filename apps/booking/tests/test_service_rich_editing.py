"""Наполнение богатой карточки услуги владельцем (2026-08-01).

`Service.attributes`/`faq` завёл UA4-3, но заполнялись они только демо-китами —
формы в кабинете не было. Здесь замки на ввод: сентинелы (иначе компактная строка
списка стирала бы наполнение) и выравнивание переводов по выжившим пунктам.
"""

import pytest
from django.contrib.auth import get_user_model
from django.test import RequestFactory

from apps.booking import views
from apps.booking.models import Service
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _urlconf(settings):
    settings.ROOT_URLCONF = "config.urls_tenant"


def _post(data, tenant):
    req = RequestFactory().post("/dashboard/booking/services/", data)
    req.tenant = tenant
    req.user = get_user_model()(username="o", is_active=True)
    from django.contrib.messages.storage.fallback import FallbackStorage

    req.session = {}
    req._messages = FallbackStorage(req)
    return req


def _tenant(slug, locales=("de",)):
    return TenantFactory(schema_name="public", slug=slug, name="S", enabled_locales=list(locales))


def _base(service, **extra):
    data = {
        "action": "update",
        "service": str(service.pk),
        "duration": "30",
        "price_eur": "10",
        "description": service.description,
    }
    data.update(extra)
    return data


def test_owner_can_fill_details_and_faq():
    tenant = _tenant("rich1")
    svc = Service.objects.create(name="Massage", duration_minutes=30)
    views.services_view(
        _post(
            _base(
                svc,
                attributes_present="1",
                attributes="Handtücher inklusive\n\n  Warmes Öl  ",
                faq_present="1",
                faq_q_0="Wie lange?",
                faq_a_0="60 Minuten",
                faq_q_1="",
                faq_a_1="",
            ),
            tenant,
        )
    )
    svc.refresh_from_db()
    assert svc.attributes_list == ["Handtücher inklusive", "Warmes Öl"]  # пустая строка выброшена
    assert svc.faq_list == [{"q": "Wie lange?", "a": "60 Minuten"}]  # пустая пара не сохранена


def test_save_without_sentinels_keeps_existing_content():
    """Инвариант W0: `action=update` шлётся и из компактной строки списка, где
    этих полей нет, — такой Save не должен стирать наполнение."""
    tenant = _tenant("rich2")
    svc = Service.objects.create(
        name="Massage",
        duration_minutes=30,
        attributes=["Handtücher inklusive"],
        faq=[{"q": "Wie lange?", "a": "60 Minuten"}],
    )
    views.services_view(_post(_base(svc), tenant))
    svc.refresh_from_db()
    assert svc.attributes_list == ["Handtücher inklusive"]
    assert svc.faq_list == [{"q": "Wie lange?", "a": "60 Minuten"}]


def test_clearing_question_removes_the_pair():
    tenant = _tenant("rich3")
    svc = Service.objects.create(
        name="X", duration_minutes=30, faq=[{"q": "A?", "a": "a"}, {"q": "B?", "a": "b"}]
    )
    views.services_view(
        _post(
            _base(svc, faq_present="1", faq_q_0="", faq_a_0="a", faq_q_1="B?", faq_a_1="b"),
            tenant,
        )
    )
    svc.refresh_from_db()
    assert svc.faq_list == [{"q": "B?", "a": "b"}]


def test_translations_follow_surviving_items_not_row_numbers():
    """Удалили пункт из СЕРЕДИНЫ — переводы оставшихся не должны съехать."""
    tenant = _tenant("rich4", ("de", "en"))
    svc = Service.objects.create(name="X", duration_minutes=30)
    views.services_view(
        _post(
            _base(
                svc,
                attributes_present="1",
                attributes="Eins\n\nDrei",  # вторая строка стёрта
                attributes_en="One\nTwo\nThree",
                faq_present="1",
                faq_q_0="A?",
                faq_a_0="a",
                faq_q_0_en="A-en?",
                faq_a_0_en="a-en",
                faq_q_1="",  # пункт удалён вместе со своим переводом
                faq_a_1="b",
                faq_q_1_en="B-en?",
                faq_a_1_en="b-en",
                faq_q_2="C?",
                faq_a_2="c",
                faq_q_2_en="C-en?",
                faq_a_2_en="c-en",
            ),
            tenant,
        )
    )
    svc.refresh_from_db()
    assert svc.attributes_list == ["Eins", "Drei"]
    assert svc.attributes_localized("en") == ["One", "Three"]  # НЕ ["One", "Two"]
    assert svc.faq_list == [{"q": "A?", "a": "a"}, {"q": "C?", "a": "c"}]
    assert svc.faq_localized("en") == [
        {"q": "A-en?", "a": "a-en"},
        {"q": "C-en?", "a": "c-en"},
    ]


def test_blank_translation_falls_back_to_base():
    tenant = _tenant("rich5", ("de", "en"))
    svc = Service.objects.create(name="X", duration_minutes=30)
    views.services_view(
        _post(
            _base(
                svc,
                attributes_present="1",
                attributes="Eins\nZwei",
                attributes_en="One\n",  # второй пункт не переведён
            ),
            tenant,
        )
    )
    svc.refresh_from_db()
    assert svc.attributes_localized("en") == ["One", "Zwei"]


def test_form_renders_inputs_with_existing_content():
    tenant = _tenant("rich6", ("de", "en"))
    Service.objects.create(
        name="X",
        duration_minutes=30,
        attributes=["Eins"],
        attributes_i18n={"en": ["One"]},
        faq=[{"q": "A?", "a": "a"}],
        faq_i18n={"en": [{"q": "A-en?", "a": "a-en"}]},
    )
    req = RequestFactory().get("/dashboard/booking/services/")
    req.tenant = tenant
    req.user = get_user_model()(username="o", is_active=True)
    body = views.services_view(req).content.decode()
    assert 'name="attributes_present"' in body and 'name="faq_present"' in body
    assert "Eins" in body and "One" in body
    assert 'name="faq_q_0"' in body and "A-en?" in body
    assert 'name="faq_q_1"' in body  # пустая пара для добавления нового вопроса


def test_single_locale_tenant_gets_no_translation_inputs():
    tenant = _tenant("rich7")
    Service.objects.create(name="X", duration_minutes=30, attributes=["Eins"])
    req = RequestFactory().get("/dashboard/booking/services/")
    req.tenant = tenant
    req.user = get_user_model()(username="o", is_active=True)
    body = views.services_view(req).content.decode()
    assert 'name="attributes_en"' not in body
