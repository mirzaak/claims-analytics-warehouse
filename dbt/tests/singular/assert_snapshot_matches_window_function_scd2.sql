-- Snowflake only. dbt's snapshot and the window-function model must produce the same
-- member versions: the same members, each with versions starting on the same dates.
-- Any row returned is a version found by one method and not the other.

{{ config(enabled=(target.type == 'snowflake')) }}

with snapshot_versions as (
    select member_id, synpuf_sample, cast(dbt_valid_from as date) as valid_from
    from {{ ref('snap_member_coverage') }}
),

model_versions as (
    select member_id, synpuf_sample, valid_from
    from {{ ref('int_member_coverage_versions') }}
),

only_in_snapshot as (
    select * from snapshot_versions
    except
    select * from model_versions
),

only_in_model as (
    select * from model_versions
    except
    select * from snapshot_versions
)

select 'only in snapshot' as found_in, * from only_in_snapshot
union all
select 'only in model' as found_in, * from only_in_model
