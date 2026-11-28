#!/usr/bin/env bash
# Export load-ready files and upload them to the Databricks landing volume.
# Needs the Databricks CLI, authenticated by DATABRICKS_HOST and DATABRICKS_TOKEN
# (load .env first) or by a profile from databricks auth login.
# Usage: scripts/databricks_land_files.sh [catalog] [schema]
set -euo pipefail

root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
catalog="${1:-workspace}"
schema="${2:-raw}"
volume="landing"
export_dir="$root/data/export"

cd "$root"
.venv/bin/claims-ingest export --sample 1 --out "$export_dir" --log-level WARNING

databricks schemas create "$schema" "$catalog" >/dev/null 2>&1 || true
databricks volumes create "$catalog" "$schema" "$volume" MANAGED >/dev/null 2>&1 || true

target="dbfs:/Volumes/$catalog/$schema/$volume"
for table_dir in "$export_dir"/*/; do
  table="$(basename "$table_dir")"
  # Replace the whole folder, so it holds only the current batch file.
  databricks fs rm -r "$target/$table" >/dev/null 2>&1 || true
  databricks fs cp -r "$table_dir" "$target/$table"
  echo "landed $table"
done
