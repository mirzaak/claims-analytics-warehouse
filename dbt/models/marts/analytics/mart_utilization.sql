-- Grain: one row per calendar month of the 2008 to 2010 coverage years.
-- Admissions are distinct inpatient claims, outpatient visits are distinct outpatient claims,
-- and professional claims are distinct carrier claims, each counted in the month the claim
-- starts. Per-1,000 rates are annualized: count / medical member months * 12,000.
-- For a yearly rate, sum the counts and member months first, then apply the same formula.

with member_months as (
    select
        year_month,
        coverage_year as plan_year,
        month_number,
        sum(medical_member_months) as medical_member_months
    from {{ ref('fact_member_month') }}
    group by year_month, coverage_year, month_number
),

claims as (
    select
        service_year_month as year_month,
        count(distinct case when claim_type = 'inpatient' then claim_id end) as inpatient_admissions,
        count(distinct case when claim_type = 'outpatient' then claim_id end) as outpatient_visits,
        count(distinct case when claim_type = 'carrier' then claim_id end) as professional_claims
    from {{ ref('fact_medical_claim_line') }}
    where service_year_month is not null
    group by service_year_month
),

combined as (
    select
        member_months.year_month,
        member_months.plan_year,
        member_months.month_number,
        member_months.medical_member_months,
        coalesce(claims.inpatient_admissions, 0) as inpatient_admissions,
        coalesce(claims.outpatient_visits, 0) as outpatient_visits,
        coalesce(claims.professional_claims, 0) as professional_claims
    from member_months
    left join claims
        on member_months.year_month = claims.year_month
)

select
    *,
    {{ dbt_utils.safe_divide('inpatient_admissions * 12000', 'medical_member_months') }}
        as admissions_per_1000,
    {{ dbt_utils.safe_divide('outpatient_visits * 12000', 'medical_member_months') }}
        as outpatient_visits_per_1000,
    {{ dbt_utils.safe_divide('professional_claims * 12000', 'medical_member_months') }}
        as professional_claims_per_1000
from combined
