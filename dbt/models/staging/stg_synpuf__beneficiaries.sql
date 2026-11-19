-- Grain: one row per member, coverage year and CMS sample.
-- Renames and casts the yearly beneficiary summaries. No business logic.

{%- set chronic_conditions = {
    'SP_ALZHDMTA': 'has_alzheimers_or_dementia',
    'SP_CHF': 'has_heart_failure',
    'SP_CHRNKIDN': 'has_chronic_kidney_disease',
    'SP_CNCR': 'has_cancer',
    'SP_COPD': 'has_copd',
    'SP_DEPRESSN': 'has_depression',
    'SP_DIABETES': 'has_diabetes',
    'SP_ISCHMCHT': 'has_ischemic_heart_disease',
    'SP_OSTEOPRS': 'has_osteoporosis',
    'SP_RA_OA': 'has_rheumatoid_or_osteo_arthritis',
    'SP_STRKETIA': 'has_stroke_or_tia',
} %}

{%- set annual_amounts = {
    'MEDREIMB_IP': 'inpatient_medicare_reimbursement_amount',
    'BENRES_IP': 'inpatient_beneficiary_responsibility_amount',
    'PPPYMT_IP': 'inpatient_primary_payer_amount',
    'MEDREIMB_OP': 'outpatient_medicare_reimbursement_amount',
    'BENRES_OP': 'outpatient_beneficiary_responsibility_amount',
    'PPPYMT_OP': 'outpatient_primary_payer_amount',
    'MEDREIMB_CAR': 'carrier_medicare_reimbursement_amount',
    'BENRES_CAR': 'carrier_beneficiary_responsibility_amount',
    'PPPYMT_CAR': 'carrier_primary_payer_amount',
} %}

with source as (
    {%- for year in [2008, 2009, 2010] %}
    {{ union_raw('beneficiary_' ~ year ~ '_s{sample}', {'coverage_year': year}) }}
    {% if not loop.last %}union all{% endif %}
    {%- endfor %}
)

select
    {{ clean_code('DESYNPUF_ID') }} as member_id,
    coverage_year,
    synpuf_sample,
    {{ parse_yyyymmdd('BENE_BIRTH_DT') }} as birth_date,
    {{ parse_yyyymmdd('BENE_DEATH_DT') }} as death_date,
    {{ clean_code('BENE_SEX_IDENT_CD') }} as sex_code,
    {{ clean_code('BENE_RACE_CD') }} as race_code,
    case {{ clean_code('BENE_ESRD_IND') }} when 'Y' then true when '0' then false end as has_esrd,
    {{ clean_code('SP_STATE_CODE') }} as state_code,
    {{ clean_code('BENE_COUNTY_CD') }} as county_code,
    {{ to_integer('BENE_HI_CVRAGE_TOT_MONS') }} as part_a_coverage_months,
    {{ to_integer('BENE_SMI_CVRAGE_TOT_MONS') }} as part_b_coverage_months,
    {{ to_integer('BENE_HMO_CVRAGE_TOT_MONS') }} as hmo_coverage_months,
    {{ to_integer('PLAN_CVRG_MOS_NUM') }} as part_d_coverage_months,
    {%- for column, name in chronic_conditions.items() %}
    {{ one_two_flag(column) }} as {{ name }},
    {%- endfor %}
    {%- for column, name in annual_amounts.items() %}
    {{ to_amount(column) }} as {{ name }},
    {%- endfor %}
    _loaded_at,
    _batch_id,
    _source_file
from source
