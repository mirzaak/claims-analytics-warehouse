-- Grain: one row per National Drug Code, plus an unknown row (drug_key '-1').
-- SynPUF has no drug names or brand flags, so generic vs brand is not derivable (D6).
-- An 11-character NDC splits into labeler (5), product (4) and package (2) segments.

with codes as (
    select distinct ndc_code
    from {{ ref('stg_synpuf__prescription_drug_events') }}
    where ndc_code is not null
)

select
    {{ dimension_key(['ndc_code'], 'ndc_code') }} as drug_key,
    ndc_code,
    length(ndc_code) = 11 as is_standard_ndc,
    case when length(ndc_code) = 11 then substr(ndc_code, 1, 5) end as labeler_code,
    case when length(ndc_code) = 11 then substr(ndc_code, 6, 4) end as product_code,
    case when length(ndc_code) = 11 then substr(ndc_code, 10, 2) end as package_code
from codes
union all
select
    '-1' as drug_key,
    cast(null as {{ dbt.type_string() }}) as ndc_code,
    false as is_standard_ndc,
    cast(null as {{ dbt.type_string() }}) as labeler_code,
    cast(null as {{ dbt.type_string() }}) as product_code,
    cast(null as {{ dbt.type_string() }}) as package_code
