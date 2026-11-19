#!/usr/bin/env bash
# Run dbt with settings from .env.
# Usage: scripts/dbt.sh build --select staging
set -euo pipefail

root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
if [[ -f "$root/.env" ]]; then
  set -a
  # shellcheck disable=SC1091
  source "$root/.env"
  set +a
fi

export DBT_PROJECT_DIR="$root/dbt"
export DBT_PROFILES_DIR="$root/dbt"

dbt_bin="$root/.venv/bin/dbt"
if [[ ! -x "$dbt_bin" ]]; then
  dbt_bin="dbt"
fi
exec "$dbt_bin" "$@"
