-- Grain: one row per ICD-9-CM diagnosis code, plus an unknown row (diagnosis_key '-1').
-- SynPUF stores codes without the decimal point. formatted_code adds it back:
-- after 3 characters for numeric and V codes, after 4 for E codes.
-- Descriptions come from the CMS Version 32 titles; codes CMS retired have none.

with codes as (
    select diagnosis_code from {{ ref('int_diagnosis_codes') }}
),

titles as (
    select diagnosis_code as title_code, short_description, long_description
    from {{ ref('icd9_diagnosis_descriptions') }}
)

select
    {{ dimension_key(['codes.diagnosis_code'], 'codes.diagnosis_code') }} as diagnosis_key,
    codes.diagnosis_code,
    titles.short_description,
    titles.long_description,
    case
        when diagnosis_code like 'E%' and length(diagnosis_code) > 4
            then {{ dbt.concat(["substr(diagnosis_code, 1, 4)", "'.'", "substr(diagnosis_code, 5)"]) }}
        when diagnosis_code not like 'E%' and length(diagnosis_code) > 3
            then {{ dbt.concat(["substr(diagnosis_code, 1, 3)", "'.'", "substr(diagnosis_code, 4)"]) }}
        else diagnosis_code
    end as formatted_code,
    case
        when diagnosis_code like 'E%' then substr(diagnosis_code, 1, 4)
        else substr(diagnosis_code, 1, 3)
    end as category_code,
    case
        when diagnosis_code like 'V%' then 'Supplementary (V code)'
        when diagnosis_code like 'E%' then 'External cause (E code)'
        else 'Disease or injury'
    end as code_type
from codes
left join titles
    on codes.diagnosis_code = titles.title_code
union all
select
    '-1' as diagnosis_key,
    cast(null as {{ dbt.type_string() }}) as diagnosis_code,
    'Unknown' as short_description,
    'Unknown diagnosis' as long_description,
    cast(null as {{ dbt.type_string() }}) as formatted_code,
    cast(null as {{ dbt.type_string() }}) as category_code,
    'Unknown' as code_type
