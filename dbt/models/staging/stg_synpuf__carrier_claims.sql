-- Grain: one row per carrier (professional) claim and CMS sample, files A and B combined.
-- Renames and casts. The 13 repeated line columns stay wide with a _n suffix;
-- intermediate models unpivot them into claim lines.

{%- set line_columns = [
    ('PRF_PHYSN_NPI', 'line_performing_npi', 'code'),
    ('TAX_NUM', 'line_tax_number', 'code'),
    ('HCPCS_CD', 'line_hcpcs_code', 'code'),
    ('LINE_NCH_PMT_AMT', 'line_payment_amount', 'amount'),
    ('LINE_BENE_PTB_DDCTBL_AMT', 'line_part_b_deductible_amount', 'amount'),
    ('LINE_BENE_PRMRY_PYR_PD_AMT', 'line_primary_payer_paid_amount', 'amount'),
    ('LINE_COINSRNC_AMT', 'line_coinsurance_amount', 'amount'),
    ('LINE_ALOWD_CHRG_AMT', 'line_allowed_amount', 'amount'),
    ('LINE_PRCSG_IND_CD', 'line_processing_indicator_code', 'code'),
    ('LINE_ICD9_DGNS_CD', 'line_diagnosis_code', 'code'),
] %}

with source as (
    {{ union_raw('carrier_claims_a_s{sample}') }}
    union all
    {{ union_raw('carrier_claims_b_s{sample}') }}
)

select
    {{ clean_code('CLM_ID') }} as claim_id,
    synpuf_sample,
    {{ clean_code('DESYNPUF_ID') }} as member_id,
    {{ parse_yyyymmdd('CLM_FROM_DT') }} as claim_from_date,
    {{ parse_yyyymmdd('CLM_THRU_DT') }} as claim_thru_date,
    {%- for i in range(1, 9) %}
    {{ clean_code('ICD9_DGNS_CD_' ~ i) }} as diagnosis_code_{{ i }},
    {%- endfor %}
    {%- for source_name, name, kind in line_columns %}
    {%- for i in range(1, 14) %}
    {% if kind == 'amount' %}{{ to_amount(source_name ~ '_' ~ i) }}{% else %}{{ clean_code(source_name ~ '_' ~ i) }}{% endif %} as {{ name }}_{{ i }},
    {%- endfor %}
    {%- endfor %}
    _loaded_at,
    _batch_id,
    _source_file
from source
