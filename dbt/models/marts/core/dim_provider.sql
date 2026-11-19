-- Grain: one row per provider and provider type, plus an unknown row (provider_key '-1').
-- Institutions are identified by CMS provider number, physicians by NPI. SynPUF has no
-- provider names or specialties, so the dimension holds IDs and activity dates.

with providers as (
    select
        provider_type,
        provider_id,
        min(service_from_date) as first_service_date,
        max(service_from_date) as last_service_date
    from {{ ref('int_medical_claim_lines') }}
    where provider_id is not null
    group by provider_type, provider_id
)

select
    {{ dimension_key(['provider_type', 'provider_id'], 'provider_id') }} as provider_key,
    provider_type,
    provider_id,
    first_service_date,
    last_service_date
from providers
union all
select
    '-1' as provider_key,
    'Unknown' as provider_type,
    cast(null as {{ dbt.type_string() }}) as provider_id,
    cast(null as date) as first_service_date,
    cast(null as date) as last_service_date
