{#-
  Business rules, defined once. Each rule is a boolean dq_ column on a fact, computed in
  that fact's model. Rows that fail are flagged and kept, never dropped. dq_quarantine
  lists every failing row with its reason; dq_rule_summary compares each rule's
  violation rate with max_violation_rate, and a test fails the build when a rule
  degrades past it.

  Thresholds sit at about two to three times the rate measured on Sample 1, or at zero
  for rules that never fired. Run with --vars '{dq_max_rate_scale: 0}' to force every
  rule with a violation to fail, for example to test alerting.
-#}

{% macro dq_record_types() -%}
    {{ return({
        'medical_claim_line': {
            'model': 'fact_medical_claim_line',
            'key': 'medical_claim_line_key',
            'claim_id': 'claim_id',
            'service_date': 'service_from_date',
            'amount': 'paid_amount',
        },
        'pharmacy_claim': {
            'model': 'fact_pharmacy_claim',
            'key': 'pharmacy_claim_key',
            'claim_id': 'pde_id',
            'service_date': 'fill_date',
            'amount': 'gross_drug_cost_amount',
        },
    }) }}
{%- endmacro %}

{% macro dq_rules() -%}
    {{ return([
        {
            'name': 'negative_paid_amount',
            'record_type': 'medical_claim_line',
            'column': 'dq_negative_paid_amount',
            'reason': 'Paid amount is below zero.',
            'max_violation_rate': 0.001,
        },
        {
            'name': 'missing_service_date',
            'record_type': 'medical_claim_line',
            'column': 'dq_missing_service_date',
            'reason': 'Claim has no service start date.',
            'max_violation_rate': 0.005,
        },
        {
            'name': 'service_date_after_thru_date',
            'record_type': 'medical_claim_line',
            'column': 'dq_service_date_after_thru_date',
            'reason': 'Service start date is after the service end date.',
            'max_violation_rate': 0,
        },
        {
            'name': 'member_not_enrolled_in_service_month',
            'record_type': 'medical_claim_line',
            'column': 'dq_member_not_enrolled_in_month',
            'reason': 'Member has no medical enrollment in the month of service.',
            'max_violation_rate': 0.02,
        },
        {
            'name': 'negative_drug_cost',
            'record_type': 'pharmacy_claim',
            'column': 'dq_negative_drug_cost',
            'reason': 'Gross drug cost is below zero.',
            'max_violation_rate': 0,
        },
        {
            'name': 'patient_pay_exceeds_drug_cost',
            'record_type': 'pharmacy_claim',
            'column': 'dq_patient_pay_exceeds_drug_cost',
            'reason': 'Patient pay is higher than the gross drug cost.',
            'max_violation_rate': 0.10,
        },
        {
            'name': 'zero_days_supply',
            'record_type': 'pharmacy_claim',
            'column': 'dq_zero_days_supply',
            'reason': 'Fill has zero days supply.',
            'max_violation_rate': 0.05,
        },
        {
            'name': 'member_not_enrolled_in_part_d_month',
            'record_type': 'pharmacy_claim',
            'column': 'dq_member_not_enrolled_in_month',
            'reason': 'Member has no Part D enrollment in the month of the fill.',
            'max_violation_rate': 0.03,
        },
    ]) }}
{%- endmacro %}

{#- True when any dq_ flag of the record type is set. -#}
{% macro dq_any_issue(record_type) -%}
    (
        {%- for rule in dq_rules() if rule.record_type == record_type %}
        {{ rule.column }}{% if not loop.last %} or{% endif %}
        {%- endfor %}
    )
{%- endmacro %}
