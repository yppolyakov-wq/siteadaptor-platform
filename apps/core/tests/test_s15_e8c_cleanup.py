"""FB-33 стопка 15 E8c (S14-E8-cleanup): разовая чистка `site_search` вне страницы 404.

План — `docs/fb33-stack15-plan-2026-11-25.md` §2 E8c, §4 E8c, §14.1 A5, §9 №6. Команда
`drop_stray_site_search` снимает из `sections` и `page_blocks[host]` только блоки, которые
запрещает `banned_blocks(host)` и которые «только для 404» (`NOT_FOUND_ONLY_BLOCKS`): прочие
байты не трогает, `normalize` не зовёт, переводы по позиции едут за своими блоками (A5),
кэш витрины сбрасывается после коммита. Повтор — 0 изменений.
"""

import copy
import logging
import re
from io import StringIO
from unittest import mock

import psycopg
import pytest
from django.core.management import call_command
from django.core.management.base import CommandError
from django.db import OperationalError, connection

from apps.audit.models import AuditEvent
from apps.core import config_migration, pagecache
from apps.core.management.commands import drop_stray_site_search as cmd
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
    out, err = StringIO(), StringIO()
    call_command(CMD, *args, stdout=out, stderr=err)
    return out.getvalue() + err.getvalue()


#: поля итоговой строки — одни у `--dry-run` и у записи (ревью 1 п.6)
SUMMARY_FIELDS = (
    "схем",
    "сайтов с чисткой",
    "блоков",
    "страниц пустых",
    "переводов не выровнено",
    "с ошибкой формы",
    "исчезли",
    "занято",
    "откачено владельцем",
    "кэш не сброшен",
)


def _summary(out: str) -> dict:
    line = next(ln for ln in out.splitlines() if ln.startswith(("Проверка:", "Чистка:")))
    return {f: int(re.search(rf"{f} (\d+)", line).group(1)) for f in SUMMARY_FIELDS}


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


def test_only_site_search_removed_bytes_else_same():
    """№6: снят только `site_search` вне 404; всё прочее — байт в байт."""
    tenant = TenantFactory(site_config=_messy())
    _run()
    expected = _messy()
    expected["sections"] = [expected["sections"][0], TEXT, expected["sections"][3]]
    expected["page_blocks"]["catalog"] = [TEXT, {"weird": True}]
    expected["page_blocks"]["confirmation"] = [NEWS]
    assert _cfg(tenant) == expected


def test_not_found_kept():
    tenant = TenantFactory(site_config={"page_blocks": {"not_found": [SEARCH, TEXT]}})
    out = _run()
    assert _cfg(tenant)["page_blocks"]["not_found"] == [SEARCH, TEXT]
    assert f"{tenant.schema_name}:" not in out  # сайт без изменений не перечисляется


def test_idempotent():
    tenant = TenantFactory(site_config=_messy())
    _run()
    after = copy.deepcopy(_cfg(tenant))
    out = _run()
    assert _cfg(tenant) == after
    assert _summary(out)["сайтов с чисткой"] == 0


def test_dry_run_writes_nothing():
    tenant = TenantFactory(site_config=_messy())
    with mock.patch("apps.core.pagecache.bump_storefront_cache") as bump:
        out = _run("--dry-run")
    assert _cfg(tenant) == _messy()
    assert not bump.called
    assert f"{tenant.schema_name}:" in out and "catalog" in out
    assert _summary(out)["сайтов с чисткой"] == 1


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
    # и показ — тот же, что давало снятие при чтении: страница без блоков
    assert siteconfig.page_rows(siteconfig.normalize(_cfg(tenant)), "cart") == []


PROMO_GROUP = siteconfig.promo_group_host("Sale")


@pytest.mark.parametrize(
    "host", ["catalog", "cart", "catalog:x", "seite:x", "product", "category", PROMO_GROUP]
)
def test_shown_rows_same_as_read_time_drop(host):
    """План §1 E8c: вывод тот же, что сейчас (поиск уже снят при чтении)."""
    raw = {"page_blocks": {host: [SEARCH, TEXT] if host == "catalog" else [SEARCH]}}
    tenant = TenantFactory(site_config=copy.deepcopy(raw))
    before = siteconfig.page_rows(siteconfig.normalize(raw), host)
    _run()
    assert siteconfig.page_rows(siteconfig.normalize(_cfg(tenant)), host) == before
    assert siteconfig.has_own_schema(siteconfig.normalize(_cfg(tenant)), host) is (
        siteconfig.has_own_schema(siteconfig.normalize(raw), host)
    )


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


def test_cleanup_keeps_translations_on_their_blocks():
    """A5: переводы по позиции (`i18n[loc][sections|page_blocks][host][i]`) едут за своими
    блоками — после снятия поиска перевод «Infotext» стоит у «Infotext», не у соседа."""
    hero = {"key": "hero", "enabled": True}
    cfg = {
        # фикс-секция перед текстом; «мусор» — в хосте без поиска (его переводы не трогаем)
        "sections": [hero, SEARCH, TEXT],
        "page_blocks": {"catalog": [SEARCH2, TEXT], "services": [TEXT, {"weird": True}]},
        "i18n": {
            "ru": {
                "sections": [
                    {"title": "Баннер"},
                    {"data": {"title": "Поиск"}},
                    {"data": {"title": "Инфо"}},
                ],
                "page_blocks": {
                    "catalog": [{"data": {"title": "Найти"}}, {"data": {"title": "Инфо-к"}}],
                    "services": [{"data": {"title": "Инфо-у"}}, {"x": "мусор"}],
                },
                "hero_title": "Привет",
            }
        },
    }
    tenant = TenantFactory(site_config=copy.deepcopy(cfg))
    _run()
    saved = _cfg(tenant)
    ru = saved["i18n"]["ru"]
    assert ru["sections"] == [{"title": "Баннер"}, {"data": {"title": "Инфо"}}]
    assert ru["page_blocks"]["catalog"] == [{"data": {"title": "Инфо-к"}}]
    assert ru["page_blocks"]["services"] == [{"data": {"title": "Инфо-у"}}, {"x": "мусор"}]
    assert ru["hero_title"] == "Привет"
    shown = siteconfig.localize(siteconfig.normalize(saved), "ru")
    text = next(b for b in shown["sections"] if b.get("id") == "t1")
    assert text["data"]["title"] == "Инфо"
    cat = next(b for b in shown["page_blocks"]["catalog"] if b.get("id") == "t1")
    assert cat["data"]["title"] == "Инфо-к"


def test_deploy_runs_cleanup_after_form_i18n_realign_with_warn():
    """План §2 E8c: шаг `deploy.sh` после `form_i18n_realign`, сбой — WARN, не остановка."""
    from pathlib import Path

    sh = Path("scripts/deploy.sh").read_text()
    step = sh.index(f"if ! $COMPOSE exec -T web python manage.py {CMD}; then")
    assert sh.index("manage.py form_i18n_realign; then") < step
    assert sh.index(f"!!! WARN: {CMD} FAILED", step) > step


# --- ревью 1 -------------------------------------------------------------------------------


def _lock_timeout(*_a, **_k):
    """Настоящее исключение psycopg 3 (у него `sqlstate`, а не `pgcode`)."""
    try:
        raise psycopg.errors.LockNotAvailable("canceling statement due to lock timeout")
    except psycopg.errors.LockNotAvailable as cause:
        raise OperationalError("lock timeout") from cause


def test_busy_detected_by_sqlstate():
    """п.1: «занято» узнаётся по `sqlstate` — во всех трёх командах переноса."""
    from apps.core import quick_links_migration as qlm
    from apps.core.management.commands import form_i18n_realign
    from apps.core.tests.test_fb33_m2c_detach import _cfg as ql_cfg
    from apps.core.tests.test_fb33_m2i5b_before import POSITIONAL

    assert not hasattr(psycopg.errors.LockNotAvailable("x"), "pgcode")
    mine = TenantFactory(site_config=_messy())
    form = TenantFactory(site_config=copy.deepcopy(POSITIONAL))
    quick = TenantFactory(site_config=ql_cfg("friseur"))
    with mock.patch.object(config_migration, "write_with_snapshot", side_effect=_lock_timeout):
        assert cmd.apply_tenant(mine.pk).status == "busy"
        assert form_i18n_realign.apply_tenant(form.pk) == "busy"
        assert qlm.apply_tenant(quick).action == qlm.BUSY
    assert config_migration.is_lock_timeout(_catch(_lock_timeout))
    assert not config_migration.is_lock_timeout(OperationalError("connection lost"))


def _catch(fn):
    try:
        fn()
    except Exception as exc:  # noqa: BLE001
        return exc
    raise AssertionError("no exception")


@pytest.mark.django_db(transaction=True)
def test_cache_bump_failure_logged_and_reported(caplog):
    """п.2: сбой сброса кэша виден — в логе со схемой, в итоге и ненулевым выходом."""
    tenant = TenantFactory(site_config=_messy())
    out, err = StringIO(), StringIO()
    caplog.set_level(logging.WARNING)
    with mock.patch.object(pagecache.cache, "set", side_effect=ConnectionError("redis down")):
        assert pagecache.bump_storefront_cache("acme") is False
        with pytest.raises(CommandError, match="кэш"):
            call_command(CMD, stdout=out, stderr=err)
    assert any("acme" in r.getMessage() for r in caplog.records)
    assert any(tenant.schema_name in r.getMessage() for r in caplog.records)
    assert _summary(out.getvalue())["кэш не сброшен"] == 1
    assert pagecache.bump_storefront_cache("acme") is True


def test_realign_with_unnormalized_stored_sections():
    """п.3: хранимый список не равен нормализованному (мусор между блоками) — по какой
    позиции стоят переводы, не угадываем: переводы не трогаем, строка в выводе и в итоге."""
    junk = {"key": "unknown_junk", "x": 1}
    ru = [{"data": {"title": "Поиск"}}, {"x": "?"}, {"data": {"title": "Инфо"}}]
    tenant = TenantFactory(
        site_config={"sections": [SEARCH, junk, TEXT], "i18n": {"ru": {"sections": ru}}}
    )
    out = _run()
    saved = _cfg(tenant)
    assert saved["sections"] == [junk, TEXT]
    assert saved["i18n"]["ru"]["sections"] == ru
    line = next(ln for ln in out.splitlines() if "переводы не выровнены" in ln)
    assert line.startswith(f"{tenant.schema_name}:") and "home" in line
    assert _summary(out)["переводов не выровнено"] == 1


def test_undo_restores_snapshot_and_audit_written():
    """п.4–5: запись — снимком (`--undo` возвращает), событие аудита на каждый сайт."""
    tenant = TenantFactory(site_config=_messy())
    TenantFactory(site_config={"page_blocks": {"not_found": [SEARCH]}})
    AuditEvent.objects.all().delete()
    _run()
    events = AuditEvent.objects.filter(action="tenant.site_config_cleanup")
    assert [(e.tenant_schema, e.resource_id) for e in events] == [
        (tenant.schema_name, str(tenant.pk))
    ]
    assert not AuditEvent.objects.filter(action="tenant.updated").exists()
    _run("--undo")
    assert _cfg(tenant) == _messy()


def test_malformed_shapes_reported():
    """п.6: кривые формы конфига — счётчик и строка на сайт; годная часть чистится."""
    bad = [
        TenantFactory(site_config=["not", "a", "dict"]),
        TenantFactory(site_config={"sections": "x"}),
        TenantFactory(site_config={"page_blocks": "x"}),
        TenantFactory(site_config={"page_blocks": {"catalog": "x", "cart": [SEARCH]}}),
    ]
    dry = _run("--dry-run")
    out = _run()
    for tenant in bad:
        assert any(
            ln.startswith(f"{tenant.schema_name}:") and "ошибка формы" in ln
            for ln in out.splitlines()
        )
    assert _summary(out)["с ошибкой формы"] == 4
    assert _summary(out)["сайтов с чисткой"] == 1
    assert _cfg(bad[3])["page_blocks"] == {"catalog": "x", "cart": []}
    assert _summary(dry) == _summary(out)  # одни поля и те же числа


def test_gone_tenant():
    """п.6: сайт исчез во время прогона — «gone», а не «dropped»."""
    assert cmd.apply_tenant(10**9).status == "gone"
    tenant = TenantFactory(site_config=_messy())
    with mock.patch.object(
        config_migration, "write_with_snapshot", side_effect=Tenant.DoesNotExist
    ):
        assert cmd.apply_tenant(tenant.pk).status == "gone"


def test_dry_run_summary_matches_real_run():
    TenantFactory(site_config=_messy())
    TenantFactory(site_config={"page_blocks": {"cart": [SEARCH]}})
    TenantFactory(site_config={"page_blocks": {"not_found": [SEARCH]}})
    dry = _run("--dry-run")
    real = _run()
    assert _summary(dry) == _summary(real)
    assert _summary(real)["сайтов с чисткой"] == 2


def test_schema_option_cleans_one_site():
    one = TenantFactory(site_config={"page_blocks": {"cart": [SEARCH]}})
    other = TenantFactory(site_config={"page_blocks": {"cart": [SEARCH]}})
    _run("--schema", one.schema_name)
    assert _cfg(one)["page_blocks"]["cart"] == []
    assert _cfg(other)["page_blocks"]["cart"] == [SEARCH]
    with pytest.raises(CommandError):
        _run("--schema", "no_such_site")
    with pytest.raises(CommandError):
        _run("--schema", "public")


def test_one_site_fails_others_cleaned():
    """Сбой одного сайта не останавливает остальные; в stderr — только тип исключения."""
    broken = TenantFactory(site_config={"page_blocks": {"cart": [SEARCH]}, "boom": 1})
    fine = TenantFactory(site_config={"page_blocks": {"cart": [SEARCH]}})
    real = cmd.clean

    def flaky(cfg):
        if isinstance(cfg, dict) and cfg.get("boom"):
            raise ValueError("geheime Kundendaten")
        return real(cfg)

    out, err = StringIO(), StringIO()
    with mock.patch.object(cmd, "clean", side_effect=flaky):
        with pytest.raises(CommandError, match=broken.schema_name):
            call_command(CMD, stdout=out, stderr=err)
    assert _cfg(fine)["page_blocks"]["cart"] == []
    assert f"{broken.schema_name}: ОШИБКА ValueError" in err.getvalue()
    assert "geheime" not in err.getvalue() + out.getvalue()


def test_deploy_collects_warn_steps_in_final_summary():
    """п.7: шаги с WARN копятся и печатаются итогом в конце деплоя."""
    from pathlib import Path

    sh = Path("scripts/deploy.sh").read_text()
    warns = sh.count('\techo "!!! WARN:')
    assert warns >= 7
    marked = re.findall(r'then\n\twarn_step "[^"]+"\n\techo "!!! WARN:', sh)
    assert len(marked) == warns == sh.count("\twarn_step ")
    summary = sh.index('"${DEPLOY_WARNS[@]}"')
    assert summary > sh.index(f"manage.py {CMD}; then")
    assert summary < sh.index('curl -fsS "$HEALTH_URL"')
