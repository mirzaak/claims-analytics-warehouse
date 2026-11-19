-- Grain: one row per failing record and rule. A record that breaks two rules appears twice.
-- Failing records stay in the facts, flagged; this table lists them with the reason, so
-- they can be reviewed or excluded without searching every fact.

{%- set record_types = dq_record_types() %}

{%- for rule in dq_rules() %}
{%- set record = record_types[rule.record_type] %}
select
    {{ dbt_utils.generate_surrogate_key(["'" ~ rule.name ~ "'", record.key]) }} as quarantine_key,
    '{{ rule.name }}' as rule_name,
    '{{ rule.record_type }}' as record_type,
    {{ record.key }} as record_key,
    {{ record.claim_id }} as claim_id,
    member_id,
    synpuf_sample,
    {{ record.service_date }} as service_date,
    {{ record.amount }} as amount,
    '{{ rule.reason }}' as failure_reason,
    {{ dbt.current_timestamp() }} as detected_at
from {{ ref(record.model) }}
where {{ rule.column }}
{% if not loop.last %}union all{% endif %}
{%- endfor %}
