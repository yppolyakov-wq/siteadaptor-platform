"""FB-33 стопка 15 E8c (S14-E8-cleanup): разовая чистка `site_search` вне страницы 404.

План — `docs/fb33-stack15-plan-2026-11-25.md` §2 E8c, §4 E8c, §14.1 A5, §9 №6. Команда
`drop_stray_site_search` снимает из `sections` и `page_blocks[host]` только блоки, которые
запрещает `banned_blocks(host)` и которые «только для 404» (`NOT_FOUND_ONLY_BLOCKS`): прочие
байты не трогает, `normalize` не зовёт, переводы по позиции едут за своими блоками (A5),
кэш витрины сбрасывается после коммита. Повтор — 0 изменений.
"""

import copy
from unittest import mock

import pytest
from django.core.management import call_command
from django.db import connection

from apps.core import config_migration
from apps.tenants import siteconfig
from apps.tenants.models import Tenant
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db

CMD = "drop_stray_site_search"
SEARCH = {"key": "site_search", "id": "s1", "enabled": True, "data": {}}
SEARCH2 = {"key": "site_search", "id": "s2", "enabled": True, "data": {"title": "Finden"}}
TEXT = {"key": "text", "id": "t1", "enabled": True, "data": {"title": "Infotext"}}
NEWS = {"key": "newsletter", "id": "n1", "enabled": True, "data": {}}


def _run(*args):
    from io import StringIO

    out, err = StringIO(), StringIO()
    call_command(CMD, *args, stdout=out, stderr=err)
    return out.getvalue() + err.getvalue()


def _cfg(tenant):
    return Tenant.objects.get(pk=tenant.pk).site_config


def _messy():
    """Конфиг со «шумом», который normalize переписал бы: чистка его трогать не должна."""
    return {
        "sections": [
            {"key": "hero", "enabled": True, "extra": "kept"},
            SEARCH,
            TEXT,
            {"key": "unknown_junk", "x": 1},
        ],
        "page_blocks": {
            "catalog": [SEARCH2, TEXT, {"weird": True}],
            "not_found": [SEARCH, TEXT],
            # на подтверждении «newsletter» тоже запрещён, но чистит команда только поиск
            "confirmation": [NEWS, SEARCH],
            "services": "not-a-list",
        },
        "site_defaults": {"radius": 8, "zzz": None},
        "custom_key": [3, 2, 1],
    }


@pytest.mark.xfail(strict=True, reason="E8c: команды ещё нет")
def test_only_site_search_removed_bytes_else_same():
    """№6: снят только `site_search` вне 404; всё прочее — байт в байт."""
    tenant = TenantFactory(site_config=_messy())
    _run()
    expected = _messy()
    expected["sections"] = [expected["sections"][0], TEXT, expected["sections"][3]]
    expected["page_blocks"]["catalog"] = [TEXT, {"weird": True}]
    expected["page_blocks"]["confirmation"] = [NEWS]
    assert _cfg(tenant) == expected


@pytest.mark.xfail(strict=True, reason="E8c: команды ещё нет")
def test_not_found_kept():
    tenant = TenantFactory(site_config={"page_blocks": {"not_found": [SEARCH, TEXT]}})
    out = _run()
    assert _cfg(tenant)["page_blocks"]["not_found"] == [SEARCH, TEXT]
    assert f"{tenant.schema_name}:" not in out  # сайт без изменений не перечисляется


@pytest.mark.xfail(strict=True, reason="E8c: команды ещё нет")
def test_idempotent():
    tenant = TenantFactory(site_config=_messy())
    _run()
    after = copy.deepcopy(_cfg(tenant))
    out = _run()
    assert _cfg(tenant) == after
    assert "сайтов изменено 0" in out


@pytest.mark.xfail(strict=True, reason="E8c: команды ещё нет")
def test_dry_run_writes_nothing():
    tenant = TenantFactory(site_config=_messy())
    with mock.patch("apps.core.pagecache.bump_storefront_cache") as bump:
        out = _run("--dry-run")
    assert _cfg(tenant) == _messy()
    assert not bump.called
    assert f"{tenant.schema_name}:" in out and "catalog" in out
    assert "сайтов к чистке 1" in out


@pytest.mark.xfail(strict=True, reason="E8c: команды ещё нет")
def test_empty_host_reported():
    """№8 (§9 №6): хост, где поиск был единственным, остаётся `[]` и помечен «ПУСТО»."""
    tenant = TenantFactory(
        site_config={"page_blocks": {"cart": [SEARCH], "catalog": [SEARCH, TEXT]}}
    )
    out = _run()
    assert _cfg(tenant)["page_blocks"] == {"cart": [], "catalog": [TEXT]}
    line = next(ln for ln in out.splitlines() if ln.startswith(f"{tenant.schema_name}:"))
    assert "cart" in line and "ПУСТО" in line
    assert line.count("ПУСТО") == 1
    # и показ: пустой список хранится — блоков по умолчанию не появляется
    assert siteconfig.normalize(_cfg(tenant))["page_blocks"]["cart"] == []


@pytest.mark.xfail(strict=True, reason="E8c: команды ещё нет")
def test_under_lock():
    """№9: строка сайта читается и пишется под `select_for_update` внутри транзакции."""
    tenant = TenantFactory(site_config=_messy())
    outer = len(connection.atomic_blocks)
    seen = []
    real = config_migration.lock

    def spy(model, pk):
        seen.append((model, pk, len(connection.atomic_blocks) > outer))
        return real(model, pk)

    with mock.patch.object(config_migration, "lock", side_effect=spy):
        _run()
    assert seen == [(Tenant, tenant.pk, True)]


@pytest.mark.xfail(strict=True, reason="E8c: команды ещё нет")
def test_cache_bumped_on_commit(django_capture_on_commit_callbacks):
    """№13: сброс кэша витрины — после коммита, а не до."""
    tenant = TenantFactory(site_config=_messy())
    TenantFactory(site_config={"page_blocks": {"not_found": [SEARCH]}})  # без изменений
    with mock.patch("apps.core.pagecache.bump_storefront_cache") as bump:
        with django_capture_on_commit_callbacks(execute=False) as callbacks:
            _run()
        assert not bump.called
        for cb in callbacks:
            cb()
    bump.assert_called_once_with(tenant.schema_name)


@pytest.mark.xfail(strict=True, reason="E8c: команды ещё нет")
def test_cleanup_keeps_translations_on_their_blocks():
    """A5: переводы по позиции (`i18n[loc][sections|page_blocks][host][i]`) едут за своими
    блоками — после снятия поиска перевод «Infotext» стоит у «Infotext», не у соседа."""
    cfg = {
        "sections": [SEARCH, TEXT],
        "page_blocks": {"catalog": [SEARCH2, TEXT], "services": [TEXT]},
        "i18n": {
            "ru": {
                "sections": [{"data": {"title": "Поиск"}}, {"data": {"title": "Инфо"}}],
                "page_blocks": {
                    "catalog": [{"data": {"title": "Найти"}}, {"data": {"title": "Инфо-к"}}],
                    "services": [{"data": {"title": "Инфо-у"}}],
                },
                "hero_title": "Привет",
            }
        },
    }
    tenant = TenantFactory(site_config=copy.deepcopy(cfg))
    _run()
    saved = _cfg(tenant)
    ru = saved["i18n"]["ru"]
    assert ru["sections"] == [{"data": {"title": "Инфо"}}]
    assert ru["page_blocks"]["catalog"] == [{"data": {"title": "Инфо-к"}}]
    assert ru["page_blocks"]["services"] == [{"data": {"title": "Инфо-у"}}]  # не тронут
    assert ru["hero_title"] == "Привет"
    shown = siteconfig.localize(siteconfig.normalize(saved), "ru")
    text = next(b for b in shown["sections"] if b.get("id") == "t1")
    assert text["data"]["title"] == "Инфо"
    cat = next(b for b in shown["page_blocks"]["catalog"] if b.get("id") == "t1")
    assert cat["data"]["title"] == "Инфо-к"
