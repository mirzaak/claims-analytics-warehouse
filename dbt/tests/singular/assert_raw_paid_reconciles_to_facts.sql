-- Reconciliation: total paid in the raw files must equal total paid in the facts, per
-- claim type, within one cent. Raw amounts are summed straight from the source tables,
-- so a dropped, duplicated or mis-cast row anywhere in between fails this test.

{%- set carrier_line_amounts = [] %}
{%- for i in range(1, 14) %}
    {%- do carrier_line_amounts.append('coalesce(' ~ to_amount('LINE_NCH_PMT_AMT_' ~ i) ~ ', 0)') %}
{%- endfor %}

with raw_amounts as (
    {%- for sample in var('synpuf_samples') %}
    {%- set suffix = '_s%02d' % sample %}
    select 'inpatient' as measure, sum({{ to_amount('CLM_PMT_AMT') }}) as amount
    from {{ source('synpuf', 'inpatient_claims' ~ suffix) }}
    union all
    select 'outpatient' as measure, sum({{ to_amount('CLM_PMT_AMT') }}) as amount
    from {{ source('synpuf', 'outpatient_claims' ~ suffix) }}
    union all
    {%- for part in ['a', 'b'] %}
    select 'carrier' as measure, sum({{ carrier_line_amounts | join(' + ') }}) as amount
    from {{ source('synpuf', 'carrier_claims_' ~ part ~ suffix) }}
    union all
    {%- endfor %}
    select 'pharmacy_gross_cost' as measure, sum({{ to_amount('TOT_RX_CST_AMT') }}) as amount
    from {{ source('synpuf', 'prescription_drug_events' ~ suffix) }}
    {% if not loop.last %}union all{% endif %}
    {%- endfor %}
),

raw_totals as (
    select measure, sum(amount) as amount
    from raw_amounts
    group by measure
),

fact_totals as (
    select claim_type as measure, sum(paid_amount) as amount
    from {{ ref('fact_medical_claim_line') }}
    group by claim_type
    union all
    select 'pharmacy_gross_cost' as measure, sum(gross_drug_cost_amount) as amount
    from {{ ref('fact_pharmacy_claim') }}
)

select
    coalesce(raw_totals.measure, fact_totals.measure) as measure,
    raw_totals.amount as raw_amount,
    fact_totals.amount as fact_amount
from raw_totals
full outer join fact_totals
    on raw_totals.measure = fact_totals.measure
where abs(coalesce(raw_totals.amount, 0) - coalesce(fact_totals.amount, 0)) > 0.01
