-- Grain: one row per procedure code and code system, plus an unknown row (procedure_key '-1').
-- HCPCS Level I codes (CPT) start with a digit; Level II codes start with a letter.

with codes as (
    select procedure_code_system, procedure_code from {{ ref('int_procedure_codes') }}
)

select
    {{ dimension_key(['procedure_code_system', 'procedure_code'], 'procedure_code') }} as procedure_key,
    procedure_code_system,
    procedure_code,
    case
        when procedure_code_system <> 'HCPCS' then cast(null as {{ dbt.type_string() }})
        when substr(procedure_code, 1, 1) between '0' and '9' then 'Level I (CPT)'
        else 'Level II'
    end as hcpcs_level
from codes
union all
select
    '-1' as procedure_key,
    'Unknown' as procedure_code_system,
    cast(null as {{ dbt.type_string() }}) as procedure_code,
    cast(null as {{ dbt.type_string() }}) as hcpcs_level
