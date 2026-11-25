{#-
  Grain: one row per member coverage version, captured by dbt's own SCD Type 2 snapshot.
  Snowflake only: snapshots update existing rows, which the BigQuery sandbox does not allow.

  The source files hold one state per year, so the snapshot is replayed year by year with
  scripts/replay_member_snapshot.sh. Each run snapshots one coverage year, and
  updated_at makes dbt_valid_from the first day of that year. A singular test checks the
  result against int_member_coverage_versions, the window-function version.
-#}
{% snapshot snap_member_coverage %}

{{ config(
    enabled=(target.type == 'snowflake'),
    schema='snapshots',
    unique_key='member_natural_key',
    strategy='check',
    check_cols=[
        'state_code', 'county_code', 'has_esrd',
        'part_a_coverage_months', 'part_b_coverage_months',
        'hmo_coverage_months', 'part_d_coverage_months',
    ],
    updated_at='coverage_start_date',
    hard_deletes='invalidate',
) }}

select
    {{ dbt.concat(['member_id', "'|'", dbt.safe_cast('synpuf_sample', dbt.type_string())]) }}
        as member_natural_key,
    member_id,
    synpuf_sample,
    {{ date_from_parts('coverage_year', 1, 1) }} as coverage_start_date,
    state_code,
    county_code,
    has_esrd,
    part_a_coverage_months,
    part_b_coverage_months,
    hmo_coverage_months,
    part_d_coverage_months
from {{ ref('stg_synpuf__beneficiaries') }}
where coverage_year = {{ var('snapshot_coverage_year') }}

{% endsnapshot %}
