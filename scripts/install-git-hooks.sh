#!/bin/bash
# Включает хуки из .githooks (сейчас — pre-commit с i18n-проверками, I18N-13).
# Выполнить один раз после клона: bash scripts/install-git-hooks.sh
set -euo pipefail
cd "$(git rev-parse --show-toplevel)"
git config core.hooksPath .githooks
echo "git hooks: core.hooksPath = .githooks (pre-commit: i18n)"
echo "Отключить: git config --unset core.hooksPath"
