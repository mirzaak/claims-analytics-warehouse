-- Grain: one row per member and plan year, for members above the 95th percentile of total
-- annual cost among members enrolled that year (cost_percentile > 0.95).
-- Total cost = Medicare paid on medical claim lines + plan paid on prescription fills,
-- by service or fill year. Members enrolled with no claims count as zero cost, so the
-- percentile reflects the whole enrolled population.

with enrolled as (
    select
        member_id,
        synpuf_sample,
        coverage_year as plan_year,
        sum(months.medical_member_months) as medical_member_months,
        sum(months.pharmacy_member_months) as pharmacy_member_months
    from {{ ref('fact_member_month') }} as months
    group by member_id, synpuf_sample, coverage_year
    -- Qualified, because BigQuery resolves a bare name in HAVING to the output alias.
    having sum(months.medical_member_months) + sum(months.pharmacy_member_months) > 0
),

medical as (
    select
        member_id,
        synpuf_sample,
        extract(year from service_from_date) as plan_year,
        sum(paid_amount) as medical_paid_amount
    from {{ ref('fact_medical_claim_line') }}
    where service_from_date is not null
    group by member_id, synpuf_sample, extract(year from service_from_date)
),

pharmacy as (
    select
        member_id,
        synpuf_sample,
        extract(year from fill_date) as plan_year,
        sum(plan_paid_amount) as pharmacy_paid_amount
    from {{ ref('fact_pharmacy_claim') }}
    group by member_id, synpuf_sample, extract(year from fill_date)
),

annual as (
    select
        enrolled.*,
        coalesce(medical.medical_paid_amount, 0) as medical_paid_amount,
        coalesce(pharmacy.pharmacy_paid_amount, 0) as pharmacy_paid_amount,
        coalesce(medical.medical_paid_amount, 0) + coalesce(pharmacy.pharmacy_paid_amount, 0)
            as total_paid_amount
    from enrolled
    left join medical
        on enrolled.member_id = medical.member_id
        and enrolled.synpuf_sample = medical.synpuf_sample
        and enrolled.plan_year = medical.plan_year
    left join pharmacy
        on enrolled.member_id = pharmacy.member_id
        and enrolled.synpuf_sample = pharmacy.synpuf_sample
        and enrolled.plan_year = pharmacy.plan_year
),

ranked as (
    select
        *,
        percent_rank() over (partition by plan_year order by total_paid_amount) as cost_percentile,
        rank() over (partition by plan_year order by total_paid_amount desc) as cost_rank,
        count(*) over (partition by plan_year) as enrolled_member_count,
        sum(total_paid_amount) over (partition by plan_year) as plan_year_total_paid_amount
    from annual
),

chronic_conditions as (
    select
        member_id,
        synpuf_sample,
        coverage_year as plan_year,
        {% for flag in [
            'has_alzheimers_or_dementia', 'has_heart_failure', 'has_chronic_kidney_disease',
            'has_cancer', 'has_copd', 'has_depression', 'has_diabetes',
            'has_ischemic_heart_disease', 'has_osteoporosis',
            'has_rheumatoid_or_osteo_arthritis', 'has_stroke_or_tia'
        ] -%}
        case when {{ flag }} then 1 else 0 end{% if not loop.last %} +{% endif %}
        {% endfor -%}
        as chronic_condition_count
    from {{ ref('stg_synpuf__beneficiaries') }}
)

select
    ranked.member_id,
    ranked.synpuf_sample,
    ranked.plan_year,
    members.member_key,
    members.sex,
    ranked.plan_year - extract(year from members.birth_date) as age_at_year_end,
    chronic_conditions.chronic_condition_count,
    ranked.medical_member_months,
    ranked.pharmacy_member_months,
    ranked.medical_paid_amount,
    ranked.pharmacy_paid_amount,
    ranked.total_paid_amount,
    ranked.cost_percentile,
    ranked.cost_rank,
    ranked.enrolled_member_count,
    {{ dbt_utils.safe_divide('ranked.total_paid_amount', 'ranked.plan_year_total_paid_amount') }}
        as share_of_plan_year_cost,
    min(ranked.total_paid_amount) over (partition by ranked.plan_year) as high_cost_threshold_amount
from ranked
inner join {{ ref('dim_member') }} as members
    on ranked.member_id = members.member_id
    and ranked.synpuf_sample = members.synpuf_sample
    and ranked.plan_year between members.first_coverage_year and members.last_coverage_year
left join chronic_conditions
    on ranked.member_id = chronic_conditions.member_id
    and ranked.synpuf_sample = chronic_conditions.synpuf_sample
    and ranked.plan_year = chronic_conditions.plan_year
where ranked.cost_percentile > 0.95
