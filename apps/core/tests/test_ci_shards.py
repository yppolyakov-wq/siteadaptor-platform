"""Инвариант шардов CI (W11-5, 2026-08-06).

Прогон уперся в жёсткий 15-минутный лимит job'а → тесты разделены на два
параллельных шарда. Опасность разделения — молчаливо потерять покрытие: пакет,
исключённый из одного шарда и не добавленный в другой, просто перестаёт
проверяться, а CI остаётся зелёным. Здесь проверяется, что шарды покрывают
все `apps/*` вместе.
"""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
CI = ROOT / ".github" / "workflows" / "ci.yml"


def _shard_commands() -> dict[str, str]:
    """{шард: строка вызова pytest} из workflow.

    Читаем как текст (без yaml-парсера: pyyaml — лишь транзитивная зависимость,
    тест инфраструктуры не должен от неё зависеть).
    """
    lines = [
        ln.strip()
        for ln in CI.read_text().splitlines()
        # именно вызовы, а не упоминания pytest в комментариях
        if "run pytest" in ln and not ln.lstrip().startswith("#")
    ]
    assert len(lines) == 2, f"ожидались две ветки шардов, найдено: {lines}"
    # Ветка с --ignore = «rest», вторая = «core».
    rest = next(ln for ln in lines if "--ignore=" in ln)
    core = next(ln for ln in lines if ln is not rest)
    return {"core": core, "rest": rest}


def test_shard_union_covers_every_app():
    """Пакеты, исключённые из «rest», обязаны явно гоняться в «core»."""
    cmds = _shard_commands()
    ignored = set(re.findall(r"--ignore=(apps/[a-z_]+)", cmds["rest"]))
    explicit = set(re.findall(r"(?<![=\w])(apps/[a-z_]+)", cmds["core"]))

    assert ignored, "шард «rest» обязан что-то исключать — иначе шардинга нет"
    assert ignored == explicit, (
        f"рассинхрон шардов: «rest» исключает {sorted(ignored)}, "
        f"а «core» гоняет {sorted(explicit)} — часть тестов не выполняется нигде"
    )


def test_ignored_packages_exist():
    """Опечатка в --ignore ничего не исключит (шард молча удвоится по времени)."""
    ignored = {p for p in re.findall(r"--ignore=apps/([a-z_]+)", _shard_commands()["rest"])}
    packages = {
        p.name for p in (ROOT / "apps").iterdir() if p.is_dir() and (p / "__init__.py").exists()
    }
    assert ignored <= packages, f"несуществующие пакеты в --ignore: {sorted(ignored - packages)}"
