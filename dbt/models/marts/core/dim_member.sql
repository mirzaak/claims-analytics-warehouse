-- Grain: one row per member coverage version (SCD Type 2).
-- Coverage and residence attributes are versioned. Birth date, death date, sex and race
-- do not change in the source and are repeated on every version.
-- Facts pick the version whose valid_from to valid_to range contains the service date.

with versions as (
    select * from {{ ref('int_member_coverage_versions') }}
),

members as (
    select
        member_id,
        synpuf_sample,
        max(birth_date) as birth_date,
        max(death_date) as death_date,
        max(sex_code) as sex_code,
        max(race_code) as race_code
    from {{ ref('stg_synpuf__beneficiaries') }}
    group by member_id, synpuf_sample
)

select
    {{ dbt_utils.generate_surrogate_key(['versions.member_id', 'versions.synpuf_sample', 'versions.valid_from']) }}
        as member_key,
    versions.member_id,
    versions.synpuf_sample,
    versions.version_number,
    versions.valid_from,
    versions.valid_to,
    versions.is_current,
    members.birth_date,
    members.death_date,
    members.sex_code,
    case members.sex_code when '1' then 'Male' when '2' then 'Female' end as sex,
    members.race_code,
    case members.race_code
        when '1' then 'White'
        when '2' then 'Black'
        when '3' then 'Other'
        when '5' then 'Hispanic'
    end as race,
    versions.state_code,
    versions.county_code,
    versions.has_esrd,
    versions.part_a_coverage_months,
    versions.part_b_coverage_months,
    versions.hmo_coverage_months,
    versions.part_d_coverage_months,
    versions.first_coverage_year,
    versions.last_coverage_year
from versions
inner join members
    on versions.member_id = members.member_id
    and versions.synpuf_sample = members.synpuf_sample
