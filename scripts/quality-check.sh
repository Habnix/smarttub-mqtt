#!/usr/bin/env bash
# The required local and CI quality gate. Browser smoke tests are deliberately
# separate because they require a Chromium-capable runner.

set -euo pipefail

project_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$project_root"

# Keep interpreter, linter, type-checker, pytest and coverage caches outside
# the source tree. The directory is private to this invocation and removed on
# both success and failure.
quality_artifacts="$(mktemp -d "${TMPDIR:-/tmp}/smarttub-mqtt-quality.XXXXXX")"
trap 'rm -rf "$quality_artifacts"' EXIT
export PYTHONDONTWRITEBYTECODE=1
export COVERAGE_FILE="$quality_artifacts/.coverage"

python_bin="${PYTHON:-python}"
if [[ -x .venv/bin/python ]]; then
  python_bin=.venv/bin/python
fi

"$python_bin" -m ruff check . --cache-dir "$quality_artifacts/ruff"
"$python_bin" -m ruff format --check . --cache-dir "$quality_artifacts/ruff"
"$python_bin" -m mypy --cache-dir "$quality_artifacts/mypy" src/
"$python_bin" -m pytest -p no:cacheprovider -q --ignore=tests/test_web_browser_smoke.py \
  --cov=src --cov-report=term-missing:skip-covered --cov-fail-under=65
