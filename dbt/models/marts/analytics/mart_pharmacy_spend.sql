-- Grain: one row per National Drug Code filled at least once, 2008 to 2010.
-- SynPUF has no drug names or brand flags, so generic vs brand is not derivable (D6).
-- Filter on cost_rank for the top drugs.

with fills as (
    select
        drug_key,
        days_supply,
        gross_drug_cost_amount,
        plan_paid_amount,
        patient_pay_amount,
        {{ dbt.concat(['member_id', "'|'", dbt.safe_cast('synpuf_sample', dbt.type_string())]) }}
            as member_ref
    from {{ ref('fact_pharmacy_claim') }}
),

by_drug as (
    select
        drug_key,
        count(*) as fill_count,
        count(distinct member_ref) as member_count,
        sum(days_supply) as total_days_supply,
        sum(gross_drug_cost_amount) as gross_cost_amount,
        sum(plan_paid_amount) as plan_paid_amount,
        sum(patient_pay_amount) as patient_pay_amount
    from fills
    group by drug_key
)

select
    by_drug.drug_key,
    drugs.ndc_code,
    drugs.labeler_code,
    drugs.is_standard_ndc,
    by_drug.fill_count,
    by_drug.member_count,
    by_drug.total_days_supply,
    by_drug.gross_cost_amount,
    by_drug.plan_paid_amount,
    by_drug.patient_pay_amount,
    {{ dbt_utils.safe_divide('by_drug.gross_cost_amount', 'by_drug.fill_count') }} as gross_cost_per_fill,
    {{ dbt_utils.safe_divide('by_drug.gross_cost_amount', 'sum(by_drug.gross_cost_amount) over ()') }}
        as share_of_gross_cost,
    rank() over (order by by_drug.gross_cost_amount desc) as cost_rank
from by_drug
inner join {{ ref('dim_drug') }} as drugs
    on by_drug.drug_key = drugs.drug_key
