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
    # сайдбар — плоские якоря хабов (замок в
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
    # свёрнут в хабы).
    assert "Website" in html
    # S4a→ST-4b: «Marketing» — якорь компакт-сайдбара (ведёт в центр ST-6).
    assert "Marketing" in html
    assert ">Orders<" not in html and ">Booking<" not in html  # старые англ-метки ушли
    # Регрессия: текст шаблонного комментария не должен утекать в разметку
    # (многострочный {# #} не комментарий — нужен {% comment %}).
    assert "apps.core.modules" not in html
    assert "групп-заголовок" not in html


@pytest.mark.django_db
def test_header_shows_language_link_without_mode_toggle(rf, settings):
    """W3-fix: «Sprachen» — прямо в шапке кабинета. SM-1 (2026-08-10): тумблер
    Einfach/Experte снесён вместе с режимом — в шапке его быть НЕ должно."""
    settings.ROOT_URLCONF = "config.urls_tenant"
    tenant = TenantFactory(
        schema_name="t_hdr",
        name="Hdr Co",
        disabled_modules=[],
        site_config={"onboarding": {"step": 7, "skipped": [], "completed": True}},
    )
    user = get_user_model().objects.create_user("oh", "oh@test.de", "pw12345678")
    html = dashboard(_request(rf, user, tenant)).content.decode()

    assert "/dashboard/ui-mode/" not in html  # режима больше нет
    # Ссылка на «Sprachen» (языки витрины) в шапке.
    assert "/dashboard/settings/languages/" in html
    assert "Sprachen" in html


@pytest.mark.django_db
def test_simple_expert_mode_is_gone(rf, settings):
    """SM-1 (решение владельца 2026-08-10): функционал один для всех.

    Замок держит снос: ни функций режима в реестре модулей, ни ключа ui_mode
    после normalize, ни экрана Ansicht в реестре навигации."""
    from apps.core import modules, nav_registry
    from apps.tenants import siteconfig

    for name in ("ui_mode", "is_simple", "simple_hidden_modules", "simple_hidden_labels"):
        assert not hasattr(modules, name), f"механизм режима вернулся: modules.{name}"
    assert "ui_mode" not in siteconfig.normalize({"ui_mode": "simple"})
    assert all(e.nav_key != "ansicht" for e in nav_registry.ENTRIES)
