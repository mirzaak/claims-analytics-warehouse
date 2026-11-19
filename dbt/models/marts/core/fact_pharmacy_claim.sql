-- Grain: one row per prescription fill (pde_id and sample).
-- plan_paid_amount is derived as gross drug cost minus patient pay, because SynPUF does
-- not report the plan's share directly.

{{ config(cluster_by=['member_key']) }}

with fills as (
    select * from {{ ref('stg_synpuf__prescription_drug_events') }}
)

select
    {{ dbt_utils.generate_surrogate_key(['fills.pde_id', 'fills.synpuf_sample']) }} as pharmacy_claim_key,
    fills.pde_id,
    fills.synpuf_sample,
    {{ member_version_key() }} as member_key,
    fills.member_id,
    member_version.member_key is not null as is_member_version_matched,
    {{ dimension_key(['fills.ndc_code'], 'fills.ndc_code') }} as drug_key,
    {{ date_key('fills.service_date') }} as fill_date_key,
    {{ year_month('fills.service_date') }} as fill_year_month,
    fills.service_date as fill_date,
    fills.days_supply,
    fills.quantity_dispensed,
    fills.gross_drug_cost_amount,
    fills.patient_pay_amount,
    fills.gross_drug_cost_amount - fills.patient_pay_amount as plan_paid_amount
from fills
{{ join_member_versions('fills', 'fills.service_date') }}
