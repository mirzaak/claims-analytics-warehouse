-- Grain: one row per distinct procedure code and code system used in the medical claims.
-- HCPCS codes come from carrier lines and outpatient claims. ICD-9-CM procedure codes come
-- from inpatient and outpatient claims. They are separate code systems.

{%- set hcpcs = {'procedure_code_system': "'HCPCS'"} %}
{%- set icd9 = {'procedure_code_system': "'ICD-9-CM procedure'"} %}

with stacked as (
    {{ stack_columns(ref('stg_synpuf__carrier_claims'), numbered_columns('line_hcpcs_code', 13), 'procedure_code', hcpcs) }}
    union all
    {{ stack_columns(ref('stg_synpuf__outpatient_claims'), numbered_columns('hcpcs_code', 45), 'procedure_code', hcpcs) }}
    union all
    {{ stack_columns(ref('stg_synpuf__inpatient_claims'), numbered_columns('hcpcs_code', 45), 'procedure_code', hcpcs) }}
    union all
    {{ stack_columns(ref('stg_synpuf__inpatient_claims'), numbered_columns('procedure_code', 6), 'procedure_code', icd9) }}
    union all
    {{ stack_columns(ref('stg_synpuf__outpatient_claims'), numbered_columns('procedure_code', 6), 'procedure_code', icd9) }}
)

select distinct procedure_code_system, procedure_code
from stacked
