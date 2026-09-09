"""STU-14: у каждого типа страниц есть что редактировать, и обещания исполняются.

План — `docs/stu14-page-coverage-plan-2026-09-09.md`. Проверка STU-13 §4 показала три
класса дыр, и каждый замок ниже закрывает свой:

* **пустая панель** — тип страницы есть, а настроек и блоков у него нет вовсе
  (`tours`, `checkout`): владелец открывает страницу и видит пустоту;
* **обещание без исполнения** — хост C-блоков объявлен, но ни один шаблон витрины его
  не выводит (так жили `team`/`gallery`/`reviews` под общим хостом `info`: блок
  добавлялся, а на странице не появлялся);
* **страница вне реестра** — попадает в переключатель «Seite ▾», но типа не имеет
  (четыре архетип-лендинга).
"""

import pathlib
import re

from apps.core import studio_pages
from apps.tenants import siteconfig

TPL_DIR = pathlib.Path("templates/storefront")


def _rendered_hosts() -> set[str]:
    """Хосты, которые реально выводит хоть один шаблон витрины (`{% page_blocks "x" %}`)."""
    hosts: set[str] = set()
    for tpl in TPL_DIR.rglob("*.html"):
        for m in re.finditer(r'page_blocks\s+"([a-z_]+)"', tpl.read_text()):
            hosts.add(m.group(1))
    return hosts


def test_no_page_type_has_an_empty_panel():
    """У каждого типа страницы есть настройки ИЛИ блоки — панель не бывает пустой.

    `other` — намеренная заглушка «неизвестная страница» (STU-7), её исключаем.
    """
    empty = [
        p.code
        for p in studio_pages.PAGE_TYPES
        if p.code != "other" and not p.settings and not p.block_host
    ]
    assert not empty, f"типы страниц с пустой панелью: {empty}"


def test_every_declared_block_host_is_actually_rendered():
    """Хост C-блоков обещан → шаблон витрины обязан его выводить.

    Иначе владелец ставит блок, сохраняет и не находит его на странице.
    """
    rendered = _rendered_hosts()
    missing = sorted(h for h in siteconfig.PAGE_BLOCK_HOSTS if h not in rendered)
    assert not missing, f"хосты объявлены, но не выводятся ни одним шаблоном: {missing}"


def test_text_pages_have_their_own_hosts():
    """`/team/`, `/galerie/`, `/bewertungen/` — свои хосты, а не общий с «О нас».

    С общим хостом блок, добавленный на одну страницу, показывался бы на всех четырёх —
    и (по факту) не показывался ни на одной, кроме `/ueber-uns/`.
    """
    for host in ("team", "gallery", "reviews"):
        assert host in siteconfig.PAGE_BLOCK_HOSTS, f"нет своего хоста блоков: {host}"


def test_archetype_landings_have_a_page_type():
    """Лендинги архетипа доступны из «Seite ▾» → у них обязан быть тип страницы.

    Без типа панель «Diese Seite» пуста: владелец переходит и упирается в ничто.
    """
    known = {name for p in studio_pages.PAGE_TYPES for name in p.url_names}
    for url_name in (
        "storefront-loyalty",
        "storefront-gutschein",
        "storefront-anfrage",
        "storefront-message",
    ):
        assert url_name in known, f"лендинг вне реестра типов страниц: {url_name}"


def test_side_pages_are_known_to_the_registry():
    """Merkzettel · Kombis · Finder · Lookbook — тоже страницы витрины, не «прочее»."""
    known = {name for p in studio_pages.PAGE_TYPES for name in p.url_names}
    for url_name in (
        "storefront-wishlist",
        "storefront-combos",
        "storefront-finder",
        "storefront-lookbook",
    ):
        assert url_name in known, f"страница вне реестра типов: {url_name}"


def test_new_hosts_do_not_materialise_config_keys():
    """Расширение whitelist'а хостов НЕ добавляет ключей в конфиг (golden целы).

    `normalize_page_blocks` фильтрует уже существующие данные; пустой конфиг обязан
    остаться пустым, иначе каждый тенант получил бы новые ключи на ровном месте.
    """
    assert siteconfig.normalize_page_blocks({}) == {}
