-- Grain: one row per member coverage version (member, sample and valid_from).
-- Builds SCD Type 2 history from the yearly beneficiary files with gaps-and-islands.
-- A new version starts when a tracked attribute changes or a coverage year is skipped.
-- This replaces `dbt snapshot`, because the BigQuery sandbox does not allow DML (D1).

{%- set tracked = [
    'state_code', 'county_code', 'has_esrd',
    'part_a_coverage_months', 'part_b_coverage_months',
    'hmo_coverage_months', 'part_d_coverage_months',
] %}

with yearly as (
    select
        member_id,
        synpuf_sample,
        coverage_year,
        {{ tracked | join(',\n        ') }},
        {{ dbt_utils.generate_surrogate_key(tracked) }} as attribute_hash,
        max(coverage_year) over (partition by synpuf_sample) as latest_coverage_year
    from {{ ref('stg_synpuf__beneficiaries') }}
),

flagged as (
    select
        *,
        case
            when lag(attribute_hash) over (
                    partition by member_id, synpuf_sample order by coverage_year
                ) = attribute_hash
                and lag(coverage_year) over (
                    partition by member_id, synpuf_sample order by coverage_year
                ) = coverage_year - 1
            then 0
            else 1
        end as starts_version
    from yearly
),

numbered as (
    select
        *,
        sum(starts_version) over (
            partition by member_id, synpuf_sample
            order by coverage_year
            rows between unbounded preceding and current row
        ) as version_number
    from flagged
),

versions as (
    select
        member_id,
        synpuf_sample,
        version_number,
        {{ tracked | join(',\n        ') }},
        min(coverage_year) as first_coverage_year,
        max(coverage_year) as last_coverage_year,
        max(latest_coverage_year) as latest_coverage_year
    from numbered
    group by
        member_id,
        synpuf_sample,
        version_number,
        {{ tracked | join(',\n        ') }}
),

final as (
    select
        *,
        {{ date_from_parts('first_coverage_year', 1, 1) }} as valid_from,
        case
            when version_number = max(version_number) over (partition by member_id, synpuf_sample)
                and last_coverage_year = latest_coverage_year
            then cast('9999-12-31' as date)
            else {{ date_from_parts('last_coverage_year', 12, 31) }}
        end as valid_to,
        version_number = max(version_number) over (partition by member_id, synpuf_sample)
            as is_current
    from versions
)

select * from final
