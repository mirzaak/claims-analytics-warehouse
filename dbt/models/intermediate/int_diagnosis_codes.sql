-- Grain: one row per distinct ICD-9-CM diagnosis code used anywhere in the medical claims,
-- including secondary and line-level diagnoses that the fact table does not key on.

{%- set institutional = ['admitting_diagnosis_code'] + numbered_columns('diagnosis_code', 10) %}
{%- set carrier = numbered_columns('diagnosis_code', 8) + numbered_columns('line_diagnosis_code', 13) %}

with stacked as (
    {{ stack_columns(ref('stg_synpuf__inpatient_claims'), institutional, 'diagnosis_code') }}
    union all
    {{ stack_columns(ref('stg_synpuf__outpatient_claims'), institutional, 'diagnosis_code') }}
    union all
    {{ stack_columns(ref('stg_synpuf__carrier_claims'), carrier, 'diagnosis_code') }}
)

select distinct diagnosis_code
from stacked
