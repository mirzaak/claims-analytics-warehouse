-- Grain: one row per medical claim line, across inpatient, outpatient and carrier claims.
-- Carrier claims give one row per populated line (1 to 13), unpivoted with a single scan.
-- Inpatient and outpatient claims only have claim-level payment in SynPUF, so each claim
-- segment is one row with line_number 1 and no allowed amount (D5).

with line_numbers as (
    -- generate_series returns FLOAT64 on BigQuery, so cast to integer.
    select cast(generated_number as {{ dbt.type_int() }}) as generated_number
    from ({{ dbt_utils.generate_series(13) }}) as series
),

carrier_unpivoted as (
    select
        'carrier' as claim_type,
        claims.claim_id,
        1 as claim_segment,
        line_numbers.generated_number as line_number,
        claims.synpuf_sample,
        claims.member_id,
        claims.claim_from_date as service_from_date,
        claims.claim_thru_date as service_thru_date,
        'physician' as provider_type,
        {{ pick_numbered('claims.line_performing_npi', 'line_numbers.generated_number', 13) }} as provider_id,
        coalesce(
            {{ pick_numbered('claims.line_diagnosis_code', 'line_numbers.generated_number', 13) }},
            claims.diagnosis_code_1
        ) as diagnosis_code,
        'HCPCS' as procedure_code_system,
        {{ pick_numbered('claims.line_hcpcs_code', 'line_numbers.generated_number', 13) }} as procedure_code,
        {{ pick_numbered('claims.line_payment_amount', 'line_numbers.generated_number', 13) }} as paid_amount,
        {{ pick_numbered('claims.line_allowed_amount', 'line_numbers.generated_number', 13) }} as allowed_amount,
        {{ pick_numbered('claims.line_primary_payer_paid_amount', 'line_numbers.generated_number', 13) }}
            as primary_payer_paid_amount,
        coalesce({{ pick_numbered('claims.line_part_b_deductible_amount', 'line_numbers.generated_number', 13) }}, 0)
            + coalesce({{ pick_numbered('claims.line_coinsurance_amount', 'line_numbers.generated_number', 13) }}, 0)
            as beneficiary_responsibility_amount
    from {{ ref('stg_synpuf__carrier_claims') }} as claims
    cross join line_numbers
),

-- An empty line slot has no code, no provider and no money.
carrier_lines as (
    select *
    from carrier_unpivoted
    where procedure_code is not null
        or provider_id is not null
        or coalesce(paid_amount, 0) <> 0
        or coalesce(allowed_amount, 0) <> 0
        or coalesce(primary_payer_paid_amount, 0) <> 0
        or beneficiary_responsibility_amount <> 0
),

inpatient_lines as (
    select
        'inpatient' as claim_type,
        claim_id,
        claim_segment,
        1 as line_number,
        synpuf_sample,
        member_id,
        claim_from_date as service_from_date,
        claim_thru_date as service_thru_date,
        'institution' as provider_type,
        provider_id,
        coalesce(diagnosis_code_1, admitting_diagnosis_code) as diagnosis_code,
        'ICD-9-CM procedure' as procedure_code_system,
        procedure_code_1 as procedure_code,
        claim_payment_amount as paid_amount,
        cast(null as {{ dbt.type_numeric() }}) as allowed_amount,
        primary_payer_paid_amount,
        coalesce(inpatient_deductible_amount, 0)
            + coalesce(part_a_coinsurance_amount, 0)
            + coalesce(blood_deductible_amount, 0) as beneficiary_responsibility_amount
    from {{ ref('stg_synpuf__inpatient_claims') }}
),

outpatient_lines as (
    select
        'outpatient' as claim_type,
        claim_id,
        claim_segment,
        1 as line_number,
        synpuf_sample,
        member_id,
        claim_from_date as service_from_date,
        claim_thru_date as service_thru_date,
        'institution' as provider_type,
        provider_id,
        coalesce(diagnosis_code_1, admitting_diagnosis_code) as diagnosis_code,
        'HCPCS' as procedure_code_system,
        hcpcs_code_1 as procedure_code,
        claim_payment_amount as paid_amount,
        cast(null as {{ dbt.type_numeric() }}) as allowed_amount,
        primary_payer_paid_amount,
        coalesce(blood_deductible_amount, 0)
            + coalesce(part_b_deductible_amount, 0)
            + coalesce(part_b_coinsurance_amount, 0) as beneficiary_responsibility_amount
    from {{ ref('stg_synpuf__outpatient_claims') }}
)

select * from inpatient_lines
union all
select * from outpatient_lines
union all
select * from carrier_lines
