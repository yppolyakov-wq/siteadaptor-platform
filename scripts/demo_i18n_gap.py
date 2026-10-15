"""Покрытие переводов ДЕМО-контента: сколько текста витрин-демо реально
переведено на en/ru/uk/tr (аудит 2026-08-13).

Зачем отдельный инструмент. `scripts/i18n_gap.py` гейтит ХРОМ (msgid в коде vs
`.po`), но контент демо-китов живёт не в каталогах gettext, а в словарях
`apps/tenants/demo_i18n_<loc>.json`, и доезжает до витрины через два обхода
(`overlay_config` для site_config и `translate_tenant_content` для моделей).
Строка, которой нет в словаре — или которую обход не берёт, — молча выводится
по-немецки на любой локали. Этот скрипт делает разрыв видимым.

Что считает:
  * ROUTED — строки, у которых путь перевода ЕСТЬ (обход их берёт): для них
    покрытие = наличие записи в словаре локали;
  * GAP — строки БЕЗ пути перевода (модель без i18n-поля, ключ вне обхода):
    запись в словаре им не поможет, нужна доработка (список — в отчёте).

Запуск:  uv run python scripts/demo_i18n_gap.py [--missing ru]
"""

from __future__ import annotations

import os
import sys
from collections import defaultdict

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.test")

import django  # noqa: E402

django.setup()

from apps.tenants import demo_i18n  # noqa: E402
from apps.tenants.demo_i18n_measure import (  # noqa: E402,F401
    LOCALES,
    measure,
)


def main() -> int:
    # `--kit <key>` — замер одного кита (иначе список «нет перевода» смешивает
    # все витрины и по нему нельзя доводить конкретный архетип).
    only = sys.argv[sys.argv.index("--kit") + 1] if "--kit" in sys.argv else ""
    per_kit, routed_all, gap_all, skip_all = measure(only)

    print("ПОКРЫТИЕ ПЕРЕВОДА ДЕМО-ВИТРИН (строки с путём перевода)\n")
    header = f"{'демо-кит':<14}{'строк':>7}{'без пути':>10}" + "".join(
        f"{loc:>8}" for loc in LOCALES
    )
    print(header)
    print("-" * len(header))
    for row in sorted(per_kit, key=lambda r: -r["routed"]):
        pct = "".join(f"{100 * row[loc] / max(row['routed'], 1):>7.0f}%" for loc in LOCALES)
        print(f"{row['kit']:<14}{row['routed']:>7}{row['gap']:>10}{pct}")
    print("-" * len(header))

    print(f"\nУникальных строк с путём перевода: {len(routed_all)}")
    for loc in LOCALES:
        have = sum(1 for txt in routed_all if demo_i18n.t(txt, loc))
        print(f"  {loc}: {have}/{len(routed_all)} = {100 * have / max(len(routed_all), 1):.1f}%")
    print(f"Не требуют перевода (имена собственные, коды размеров): {len(skip_all)}")

    groups = defaultdict(list)
    for txt, (group, _where) in routed_all.items():
        groups[group].append(txt)
    print("\nПо группам контента:")
    for group in sorted(groups, key=lambda g: -len(groups[g])):
        txts = groups[group]
        pct = "".join(
            f"{100 * sum(1 for t in txts if demo_i18n.t(t, loc)) / len(txts):>7.0f}%"
            for loc in LOCALES
        )
        print(f"  {group:<18}{len(txts):>5}{pct}")

    if gap_all:
        gap_groups = defaultdict(int)
        for _txt, (group, _where) in gap_all.items():
            gap_groups[group] += 1
        print(f"\nБЕЗ пути перевода — {len(gap_all)} строк (нужна доработка, а не словарь):")
        for group, count in sorted(gap_groups.items(), key=lambda x: -x[1]):
            print(f"  {group:<18}{count:>5}")

    if "--missing" in sys.argv:
        loc = sys.argv[sys.argv.index("--missing") + 1]
        missing = sorted(t for t in routed_all if not demo_i18n.t(t, loc))
        print(f"\nНет перевода на {loc} ({len(missing)}):")
        for txt in missing:
            print(f"  {routed_all[txt][0]:<16} {txt}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
