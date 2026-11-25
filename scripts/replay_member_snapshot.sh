#!/usr/bin/env bash
# Rebuild snap_member_coverage on Snowflake by replaying coverage years in order.
# A snapshot records changes between runs, and the source holds one state per year,
# so each run feeds dbt one year. Years must run oldest first.
set -euo pipefail

root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
dbt="$root/scripts/dbt.sh"

"$dbt" run-operation drop_member_snapshot --target snowflake
for year in 2008 2009 2010; do
  echo "Snapshotting coverage year $year"
  "$dbt" snapshot --target snowflake --vars "{snapshot_coverage_year: $year}"
done
