-- Reconciliation: cost in mart_cost_pmpm plus cost the mart leaves out (no service date,
-- or a month outside the coverage years) must equal the fact totals, within one cent.
-- This proves the mart neither loses nor double-counts money.

with mart_months as (
    select year_month from {{ ref('mart_cost_pmpm') }}
),

mart_totals as (
    select
        sum(medical_paid_amount) as medical_amount,
        sum(pharmacy_paid_amount) as pharmacy_amount
    from {{ ref('mart_cost_pmpm') }}
),

medical as (
    select
        sum(paid_amount) as fact_amount,
        sum(
            case
                when service_year_month is null
                    or service_year_month not in (select year_month from mart_months)
                then paid_amount
                else 0
            end
        ) as excluded_amount
    from {{ ref('fact_medical_claim_line') }}
),

pharmacy as (
    select
        sum(plan_paid_amount) as fact_amount,
        sum(
            case
                when fill_year_month not in (select year_month from mart_months)
                then plan_paid_amount
                else 0
            end
        ) as excluded_amount
    from {{ ref('fact_pharmacy_claim') }}
),

compared as (
    select
        'medical' as measure,
        mart_totals.medical_amount + medical.excluded_amount as mart_plus_excluded_amount,
        medical.fact_amount
    from mart_totals
    cross join medical
    union all
    select
        'pharmacy' as measure,
        mart_totals.pharmacy_amount + pharmacy.excluded_amount as mart_plus_excluded_amount,
        pharmacy.fact_amount
    from mart_totals
    cross join pharmacy
)

select *
from compared
where abs(coalesce(mart_plus_excluded_amount, 0) - coalesce(fact_amount, 0)) > 0.01
