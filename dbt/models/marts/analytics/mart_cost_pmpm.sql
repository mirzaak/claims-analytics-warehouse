-- Grain: one row per calendar month of the 2008 to 2010 coverage years.
-- Medical PMPM = Medicare paid on medical claim lines / medical member months.
-- Pharmacy PMPM = plan paid (gross drug cost minus patient pay) / pharmacy member months.
-- Costs and member months are kept, so a yearly PMPM is sum(cost) / sum(member months),
-- never an average of monthly PMPMs. Claim lines with no service date, or dated outside
-- the coverage years (December 2007), have no member months to divide by and are left out.

with member_months as (
    select
        year_month,
        coverage_year as plan_year,
        month_number,
        sum(medical_member_months) as medical_member_months,
        sum(pharmacy_member_months) as pharmacy_member_months
    from {{ ref('fact_member_month') }}
    group by year_month, coverage_year, month_number
),

medical as (
    select
        service_year_month as year_month,
        sum(paid_amount) as medical_paid_amount
    from {{ ref('fact_medical_claim_line') }}
    where service_year_month is not null
    group by service_year_month
),

pharmacy as (
    select
        fill_year_month as year_month,
        sum(plan_paid_amount) as pharmacy_paid_amount,
        sum(gross_drug_cost_amount) as pharmacy_gross_cost_amount
    from {{ ref('fact_pharmacy_claim') }}
    group by fill_year_month
),

combined as (
    select
        member_months.year_month,
        member_months.plan_year,
        member_months.month_number,
        member_months.medical_member_months,
        member_months.pharmacy_member_months,
        coalesce(medical.medical_paid_amount, 0) as medical_paid_amount,
        coalesce(pharmacy.pharmacy_paid_amount, 0) as pharmacy_paid_amount,
        coalesce(pharmacy.pharmacy_gross_cost_amount, 0) as pharmacy_gross_cost_amount
    from member_months
    left join medical
        on member_months.year_month = medical.year_month
    left join pharmacy
        on member_months.year_month = pharmacy.year_month
)

select
    *,
    {{ dbt_utils.safe_divide('medical_paid_amount', 'medical_member_months') }} as medical_pmpm,
    {{ dbt_utils.safe_divide('pharmacy_paid_amount', 'pharmacy_member_months') }} as pharmacy_pmpm,
    {{ dbt_utils.safe_divide('medical_paid_amount', 'medical_member_months') }}
        + {{ dbt_utils.safe_divide('pharmacy_paid_amount', 'pharmacy_member_months') }} as total_pmpm
from combined
