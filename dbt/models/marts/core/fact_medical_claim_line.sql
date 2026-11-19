-- Grain: one row per medical claim line (claim type, claim, segment, line, sample).
-- Carrier claims contribute one row per populated line. Inpatient and outpatient claims
-- contribute one row per claim segment, with paid amount at claim level and no allowed
-- amount, because SynPUF has no institutional line payments (D5).
--
-- Partitioned by integer service_year_month, not by date: the BigQuery sandbox expires
-- date partitions older than 60 days, which would delete every 2008 to 2010 row (D2).
-- Clustered by member_key, because most analysis filters or groups by member.
-- The range starts in 2007 because 67 institutional claims begin in December 2007.

{{ config(
    partition_by=(
        {
            'field': 'service_year_month',
            'data_type': 'int64',
            'range': {'start': 200701, 'end': 201201, 'interval': 1}
        } if target.type == 'bigquery' else none
    ),
    cluster_by=['member_key'],
) }}

with lines as (
    select * from {{ ref('int_medical_claim_lines') }}
)

select
    {{ dbt_utils.generate_surrogate_key([
        'lines.claim_type', 'lines.claim_id', 'lines.claim_segment',
        'lines.line_number', 'lines.synpuf_sample'
    ]) }} as medical_claim_line_key,
    lines.claim_type,
    lines.claim_id,
    lines.claim_segment,
    lines.line_number,
    lines.synpuf_sample,
    {{ member_version_key() }} as member_key,
    lines.member_id,
    member_version.member_key is not null as is_member_version_matched,
    {{ dimension_key(['lines.provider_type', 'lines.provider_id'], 'lines.provider_id') }} as provider_key,
    {{ date_key('lines.service_from_date') }} as service_from_date_key,
    {{ date_key('lines.service_thru_date') }} as service_thru_date_key,
    {{ year_month('lines.service_from_date') }} as service_year_month,
    {{ dimension_key(['lines.diagnosis_code'], 'lines.diagnosis_code') }} as diagnosis_key,
    {{ dimension_key(['lines.procedure_code_system', 'lines.procedure_code'], 'lines.procedure_code') }}
        as procedure_key,
    lines.service_from_date,
    lines.service_thru_date,
    lines.paid_amount,
    lines.allowed_amount,
    lines.primary_payer_paid_amount,
    lines.beneficiary_responsibility_amount
from lines
{{ join_member_versions('lines', 'lines.service_from_date') }}
