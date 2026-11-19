-- Grain: one row per procedure code and code system, plus an unknown row (procedure_key '-1').
-- HCPCS Level I codes (CPT) start with a digit; Level II codes start with a letter.
-- Only ICD-9-CM procedure codes get descriptions: CPT titles are copyrighted by the AMA.

with codes as (
    select procedure_code_system, procedure_code from {{ ref('int_procedure_codes') }}
),

titles as (
    select procedure_code as title_code, short_description, long_description
    from {{ ref('icd9_procedure_descriptions') }}
)

select
    {{ dimension_key(['codes.procedure_code_system', 'codes.procedure_code'], 'codes.procedure_code') }}
        as procedure_key,
    codes.procedure_code_system,
    codes.procedure_code,
    titles.short_description,
    titles.long_description,
    case
        when codes.procedure_code_system <> 'HCPCS' then cast(null as {{ dbt.type_string() }})
        when substr(codes.procedure_code, 1, 1) between '0' and '9' then 'Level I (CPT)'
        else 'Level II'
    end as hcpcs_level
from codes
left join titles
    on codes.procedure_code_system = 'ICD-9-CM procedure'
    and codes.procedure_code = titles.title_code
union all
select
    '-1' as procedure_key,
    'Unknown' as procedure_code_system,
    cast(null as {{ dbt.type_string() }}) as procedure_code,
    'Unknown' as short_description,
    'Unknown procedure' as long_description,
    cast(null as {{ dbt.type_string() }}) as hcpcs_level
