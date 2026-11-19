-- Grain: one row per inpatient claim segment (claim_id, claim_segment) and CMS sample.
-- Renames and casts. Repeated code columns stay wide; intermediate models unpivot them.

with source as (
    {{ union_raw('inpatient_claims_s{sample}') }}
)

select
    {{ clean_code('CLM_ID') }} as claim_id,
    {{ to_integer('SEGMENT') }} as claim_segment,
    synpuf_sample,
    {{ clean_code('DESYNPUF_ID') }} as member_id,
    {{ parse_yyyymmdd('CLM_FROM_DT') }} as claim_from_date,
    {{ parse_yyyymmdd('CLM_THRU_DT') }} as claim_thru_date,
    {{ parse_yyyymmdd('CLM_ADMSN_DT') }} as admission_date,
    {{ parse_yyyymmdd('NCH_BENE_DSCHRG_DT') }} as discharge_date,
    {{ clean_code('PRVDR_NUM') }} as provider_id,
    {{ clean_code('AT_PHYSN_NPI') }} as attending_npi,
    {{ clean_code('OP_PHYSN_NPI') }} as operating_npi,
    {{ clean_code('OT_PHYSN_NPI') }} as other_npi,
    {{ to_amount('CLM_PMT_AMT') }} as claim_payment_amount,
    {{ to_amount('NCH_PRMRY_PYR_CLM_PD_AMT') }} as primary_payer_paid_amount,
    {{ to_amount('CLM_PASS_THRU_PER_DIEM_AMT') }} as pass_through_per_diem_amount,
    {{ to_amount('NCH_BENE_IP_DDCTBL_AMT') }} as inpatient_deductible_amount,
    {{ to_amount('NCH_BENE_PTA_COINSRNC_LBLTY_AM') }} as part_a_coinsurance_amount,
    {{ to_amount('NCH_BENE_BLOOD_DDCTBL_LBLTY_AM') }} as blood_deductible_amount,
    {{ to_integer('CLM_UTLZTN_DAY_CNT') }} as utilization_day_count,
    {{ clean_code('CLM_DRG_CD') }} as drg_code,
    {{ clean_code('ADMTNG_ICD9_DGNS_CD') }} as admitting_diagnosis_code,
    {%- for i in range(1, 11) %}
    {{ clean_code('ICD9_DGNS_CD_' ~ i) }} as diagnosis_code_{{ i }},
    {%- endfor %}
    {%- for i in range(1, 7) %}
    {{ clean_code('ICD9_PRCDR_CD_' ~ i) }} as procedure_code_{{ i }},
    {%- endfor %}
    {%- for i in range(1, 46) %}
    {{ clean_code('HCPCS_CD_' ~ i) }} as hcpcs_code_{{ i }},
    {%- endfor %}
    _loaded_at,
    _batch_id,
    _source_file
from source
