-- Grain: one row per prescription fill (pde_id) and CMS sample.
-- Renames and casts. ndc_code keeps the source product code text, upper-cased and trimmed.

with source as (
    {{ union_raw('prescription_drug_events_s{sample}') }}
)

select
    {{ clean_code('PDE_ID') }} as pde_id,
    synpuf_sample,
    {{ clean_code('DESYNPUF_ID') }} as member_id,
    {{ parse_yyyymmdd('SRVC_DT') }} as service_date,
    {{ clean_code('PROD_SRVC_ID') }} as ndc_code,
    {{ to_amount('QTY_DSPNSD_NUM') }} as quantity_dispensed,
    {{ to_integer('DAYS_SUPLY_NUM') }} as days_supply,
    {{ to_amount('PTNT_PAY_AMT') }} as patient_pay_amount,
    {{ to_amount('TOT_RX_CST_AMT') }} as gross_drug_cost_amount,
    _loaded_at,
    _batch_id,
    _source_file
from source
