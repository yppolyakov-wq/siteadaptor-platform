"""Сайдбар кабинета владельца: иконки модулей + групп-заголовки (S3).

Навигация собирается из реестра модулей (context-processor modules_nav по
request.tenant). Рендерим дашборд напрямую через RequestFactory (urls_tenant как
ROOT_URLCONF, чтобы reverse пунктов меню разрешался).
"""

import pytest
from django.contrib.auth import get_user_model
from django.contrib.messages.middleware import MessageMiddleware
from django.contrib.sessions.middleware import SessionMiddleware

from apps.core.views import dashboard
from apps.tenants.tests.factories import TenantFactory


def _request(rf, user, tenant):
    request = rf.get("/dashboard/")
    SessionMiddleware(lambda r: None).process_request(request)
    MessageMiddleware(lambda r: None).process_request(request)
    request.user = user
    request.tenant = tenant
    return request


@pytest.mark.django_db
def test_dashboard_nav_shows_icons_and_group_headers(rf, settings):
    settings.ROOT_URLCONF = "config.urls_tenant"
    # disabled_modules=[] → активны все модули (в т.ч. многопунктовые).
    # onboarding.completed → дашборд не гейтит на мастер (AB5), а рендерит сайдбар.
    tenant = TenantFactory(
        schema_name="t_nav",
        name="Nav Co",
        disabled_modules=[],
        site_config={"onboarding": {"step": 7, "skipped": [], "completed": True}},
    )
    user = get_user_model().objects.create_user("o", "o@test.de", "pw12345678")

    # render() shortcut уже вернул отрендеренный ответ (исключение бы упало здесь).
    resp = dashboard(_request(rf, user, tenant))
    html = resp.content.decode()

    # Иконка модуля рядом с пунктом (Angebote).
    assert "📦" in html
    # ST-4b (осознанная замена AB1-групп, одобрено 2026-07-19): компактный
    # сайдбар — плоские якоря хабов; группы AB1 остаются в classic_ui (замок в
    # test_sidebar_st4b). Здесь — состав компакт-вида.
    assert "Mein Geschäft" not in html
    assert 'href="/dashboard/marketing/"' in html
    assert 'href="/dashboard/integrationen/"' in html
    assert "Einstellungen" in html
    # «➕ Funktion hinzufügen» → страница «Module».
    assert "Add function" in html or "➕" in html
    # AB1 (язык задач): пункты сайдбара в языке задач, не техтермины/англ. сущности.
    # S2: продажи сведены в один пункт-хаб «Verkäufe» (Bestellungen/Termine и др. —
    # теперь вкладки хаба на его страницах, а не отдельные пункты сайдбара).
    assert "Verkäufe" in html  # свод продаж, язык задач
    # ST-4b: якорь «Website» (короткая метка компакт-вида; «Website gestalten»
    # остаётся в classic-группах).
    assert "Website" in html
    # S4a→ST-4b: «Marketing» — якорь компакт-сайдбара (ведёт в центр ST-6).
    assert "Marketing" in html
    assert ">Orders<" not in html and ">Booking<" not in html  # старые англ-метки ушли
    # Регрессия: текст шаблонного комментария не должен утекать в разметку
    # (многострочный {# #} не комментарий — нужен {% comment %}).
    assert "apps.core.modules" not in html
    assert "групп-заголовок" not in html


@pytest.mark.django_db
def test_header_shows_mode_toggle_and_language_link(rf, settings):
    """W3-fix (видимость): режим Einfach/Experte и «Sprachen» — прямо в шапке
    кабинета (были не найдены: режим в «Erweitert», языки в табах настроек)."""
    settings.ROOT_URLCONF = "config.urls_tenant"
    tenant = TenantFactory(
        schema_name="t_hdr",
        name="Hdr Co",
        disabled_modules=[],
        site_config={"onboarding": {"step": 7, "skipped": [], "completed": True}},
    )
    user = get_user_model().objects.create_user("oh", "oh@test.de", "pw12345678")
    html = dashboard(_request(rf, user, tenant)).content.decode()

    # Тумблер режима в шапке (POST на set-ui-mode).
    assert "/dashboard/ui-mode/" in html
    assert "Einfach" in html and "Experte" in html
    # Ссылка на «Sprachen» (языки витрины) в шапке.
    assert "/dashboard/settings/languages/" in html
    assert "Sprachen" in html
