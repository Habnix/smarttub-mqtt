"""Regression tests for source-tree artifact hygiene."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_quality_check_keeps_generated_outputs_outside_the_source_tree() -> None:
    quality_check = (ROOT / "scripts/quality-check.sh").read_text(encoding="utf-8")

    assert 'mktemp -d "${TMPDIR:-/tmp}/smarttub-mqtt-quality.' in quality_check
    assert 'export PYTHONDONTWRITEBYTECODE="1"' not in quality_check
    assert "export PYTHONDONTWRITEBYTECODE=1" in quality_check
    assert 'export COVERAGE_FILE="$quality_artifacts/.coverage"' in quality_check
    assert 'ruff check . --cache-dir "$quality_artifacts/ruff"' in quality_check
    assert 'mypy --cache-dir "$quality_artifacts/mypy"' in quality_check
    assert "-p no:cacheprovider" in quality_check


def test_clean_task_has_an_explicit_non_runtime_scope() -> None:
    clean_task = ROOT / "scripts/clean.sh"
    clean_text = clean_task.read_text(encoding="utf-8")

    assert clean_task.stat().st_mode & 0o111
    assert "config/" in clean_text
    assert "logs/" in clean_text
    assert "git clean" not in clean_text
    assert '"$project_root/config"' not in clean_text
    assert '"$project_root/logs"' not in clean_text
    assert '"$project_root/build"' in clean_text
    assert '"$project_root/src/smarttub_mqtt.egg-info"' in clean_text
