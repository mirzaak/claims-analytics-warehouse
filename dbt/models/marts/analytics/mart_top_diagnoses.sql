-- Grain: one row per ICD-9-CM diagnosis that is the primary diagnosis on at least one
-- medical claim line, 2008 to 2010. Cost is attributed by each line's diagnosis: the line
-- diagnosis for carrier claims, the first claim diagnosis for inpatient and outpatient.
-- Lines with no diagnosis are left out. Filter on cost_rank or member_rank for a top N.

with lines as (
    select
        diagnosis_key,
        claim_type,
        paid_amount,
        {{ dbt.concat(['claim_type', "'|'", 'claim_id', "'|'", dbt.safe_cast('synpuf_sample', dbt.type_string())]) }}
            as claim_ref,
        {{ dbt.concat(['member_id', "'|'", dbt.safe_cast('synpuf_sample', dbt.type_string())]) }}
            as member_ref
    from {{ ref('fact_medical_claim_line') }}
    where diagnosis_key <> '-1'
),

by_diagnosis as (
    select
        diagnosis_key,
        sum(paid_amount) as total_paid_amount,
        sum(case when claim_type = 'inpatient' then paid_amount else 0 end) as inpatient_paid_amount,
        sum(case when claim_type = 'outpatient' then paid_amount else 0 end) as outpatient_paid_amount,
        sum(case when claim_type = 'carrier' then paid_amount else 0 end) as professional_paid_amount,
        count(distinct claim_ref) as claim_count,
        count(distinct member_ref) as member_count
    from lines
    group by diagnosis_key
)

select
    by_diagnosis.diagnosis_key,
    diagnoses.diagnosis_code,
    diagnoses.formatted_code,
    diagnoses.short_description,
    diagnoses.long_description,
    diagnoses.code_type,
    by_diagnosis.total_paid_amount,
    by_diagnosis.inpatient_paid_amount,
    by_diagnosis.outpatient_paid_amount,
    by_diagnosis.professional_paid_amount,
    by_diagnosis.claim_count,
    by_diagnosis.member_count,
    {{ dbt_utils.safe_divide('by_diagnosis.total_paid_amount', 'sum(by_diagnosis.total_paid_amount) over ()') }}
        as share_of_paid_amount,
    rank() over (order by by_diagnosis.total_paid_amount desc) as cost_rank,
    rank() over (order by by_diagnosis.member_count desc) as member_rank
from by_diagnosis
inner join {{ ref('dim_diagnosis') }} as diagnoses
    on by_diagnosis.diagnosis_key = diagnoses.diagnosis_key
