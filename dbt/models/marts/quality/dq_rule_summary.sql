-- Grain: one row per data-quality rule. Violation counts and rates for the latest build,
-- with each rule's threshold. A test fails the build when a rate exceeds its threshold.

{%- set record_types = dq_record_types() %}
{%- set scale = var('dq_max_rate_scale') %}

with counts as (
    {%- for rule in dq_rules() %}
    {%- set record = record_types[rule.record_type] %}
    select
        '{{ rule.name }}' as rule_name,
        '{{ rule.record_type }}' as record_type,
        '{{ rule.reason }}' as failure_reason,
        count(*) as total_records,
        sum(case when {{ rule.column }} then 1 else 0 end) as violation_count,
        sum(case when {{ rule.column }} then {{ record.amount }} else 0 end) as violation_amount,
        cast({{ rule.max_violation_rate * scale }} as {{ dbt.type_float() }}) as max_violation_rate
    from {{ ref(record.model) }}
    {% if not loop.last %}union all{% endif %}
    {%- endfor %}
)

select
    *,
    {{ dbt_utils.safe_divide('violation_count', 'total_records') }} as violation_rate,
    {{ dbt_utils.safe_divide('violation_count', 'total_records') }} <= max_violation_rate as is_within_threshold
from counts
