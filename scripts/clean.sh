#!/usr/bin/env bash
# Remove only known generated project artifacts. Runtime configuration and
# user data under config/ and logs/ are deliberately outside this cleanup.

set -euo pipefail

project_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

for generated_path in \
  "$project_root/build" \
  "$project_root/dist" \
  "$project_root/.mypy_cache" \
  "$project_root/.pytest_cache" \
  "$project_root/.ruff_cache" \
  "$project_root/__pycache__" \
  "$project_root/smarttub_mqtt.egg-info" \
  "$project_root/src/smarttub_mqtt.egg-info"; do
  if [[ -e "$generated_path" ]]; then
    rm -rf "$generated_path"
    printf 'removed %s\n' "${generated_path#"$project_root"/}"
  fi
done

# __pycache__ directories are generated only below source, test, and script
# trees. Do not traverse the virtualenv, .git, config, or runtime directories.
while IFS= read -r -d '' cache_path; do
  rm -rf "$cache_path"
  printf 'removed %s\n' "${cache_path#"$project_root"/}"
done < <(
  find "$project_root/src" "$project_root/tests" "$project_root/scripts" \
    -type d -name __pycache__ -print0
)

# Remove bytecode files left directly in the project-owned source trees.
find "$project_root/src" "$project_root/tests" "$project_root/scripts" \
  -type f \( -name '*.pyc' -o -name '*.pyo' \) -delete
