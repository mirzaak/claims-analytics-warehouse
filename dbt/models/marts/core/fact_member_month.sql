-- Grain: one row per member, sample and calendar month of each coverage year.
-- SynPUF reports coverage as a count of months per year, not as monthly flags (D4).
-- Assumption: covered months run from January forward and stop after the month of death.
-- Medical enrollment uses the larger of Part A and Part B months; pharmacy uses Part D.
-- The 0/1 member-month columns are the PMPM denominators.

{{ config(cluster_by=['member_key']) }}

with member_years as (
    select
        member_id,
        synpuf_sample,
        coverage_year,
        death_date,
        greatest(part_a_coverage_months, part_b_coverage_months) as medical_coverage_months,
        part_d_coverage_months
    from {{ ref('stg_synpuf__beneficiaries') }}
),

months as (
    -- generate_series returns FLOAT64 on BigQuery, so cast to integer.
    select cast(generated_number as {{ dbt.type_int() }}) as generated_number
    from ({{ dbt_utils.generate_series(12) }}) as series
),

member_months as (
    select
        member_years.*,
        months.generated_number as month_number,
        {{ date_from_parts('member_years.coverage_year', 'months.generated_number', 1) }} as month_start_date
    from member_years
    cross join months
),

flagged as (
    select
        *,
        (death_date is null or month_start_date <= death_date) as is_alive_at_month_start,
        month_number <= medical_coverage_months as is_within_medical_months,
        month_number <= part_d_coverage_months as is_within_pharmacy_months
    from member_months
)

select
    {{ dbt_utils.generate_surrogate_key(['flagged.member_id', 'flagged.synpuf_sample', 'flagged.month_start_date']) }}
        as member_month_key,
    {{ member_version_key() }} as member_key,
    flagged.member_id,
    flagged.synpuf_sample,
    {{ date_key('flagged.month_start_date') }} as month_date_key,
    {{ year_month('flagged.month_start_date') }} as year_month,
    flagged.coverage_year,
    flagged.month_number,
    flagged.is_within_medical_months and flagged.is_alive_at_month_start as is_enrolled_medical,
    flagged.is_within_pharmacy_months and flagged.is_alive_at_month_start as is_enrolled_pharmacy,
    case when flagged.is_within_medical_months and flagged.is_alive_at_month_start then 1 else 0 end
        as medical_member_months,
    case when flagged.is_within_pharmacy_months and flagged.is_alive_at_month_start then 1 else 0 end
        as pharmacy_member_months
from flagged
{{ join_member_versions('flagged', 'flagged.month_start_date') }}
