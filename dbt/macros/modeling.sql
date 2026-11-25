{#- Helpers shared by intermediate and mart models. -#}

{% macro date_from_parts(year, month, day) -%}
    {{ return(adapter.dispatch('date_from_parts')(year, month, day)) }}
{%- endmacro %}

{% macro bigquery__date_from_parts(year, month, day) -%}
    date({{ year }}, {{ month }}, {{ day }})
{%- endmacro %}

{% macro snowflake__date_from_parts(year, month, day) -%}
    date_from_parts({{ year }}, {{ month }}, {{ day }})
{%- endmacro %}

{% macro databricks__date_from_parts(year, month, day) -%}
    make_date({{ year }}, {{ month }}, {{ day }})
{%- endmacro %}

{% macro default__date_from_parts(year, month, day) -%}
    {{ exceptions.raise_compiler_error("date_from_parts has no implementation for " ~ target.type) }}
{%- endmacro %}

{#-
  Clustering keys only on BigQuery. On Snowflake, automatic clustering spends credits
  continuously and gains nothing on tables this small; Databricks uses Delta defaults.
-#}
{% macro bigquery_cluster_by(columns) -%}
    {{ return(columns if target.type == 'bigquery' else none) }}
{%- endmacro %}

{#- Integer yyyymmdd key. Missing dates map to -1, the unknown row in dim_date. -#}
{% macro date_key(date_column) -%}
    coalesce(
        cast(
            extract(year from {{ date_column }}) * 10000
            + extract(month from {{ date_column }}) * 100
            + extract(day from {{ date_column }})
        as {{ dbt.type_int() }}),
        -1
    )
{%- endmacro %}

{#- Integer yyyymm, used for partitioning because the sandbox expires old date partitions. -#}
{% macro year_month(date_column) -%}
    cast(extract(year from {{ date_column }}) * 100 + extract(month from {{ date_column }}) as {{ dbt.type_int() }})
{%- endmacro %}

{#-
  Surrogate key for a dimension. When the natural key is missing, the key is '-1',
  which points at the dimension's unknown row.
-#}
{% macro dimension_key(columns, required_column) -%}
    case
        when {{ required_column }} is null then '-1'
        else {{ dbt_utils.generate_surrogate_key(columns) }}
    end
{%- endmacro %}

{#- Pick column prefix_1 .. prefix_n by a line number column, for single-scan unpivots. -#}
{% macro pick_numbered(prefix, number_column, count) -%}
    case {{ number_column }}
        {%- for i in range(1, count + 1) %}
        when {{ i }} then {{ prefix }}_{{ i }}
        {%- endfor %}
    end
{%- endmacro %}

{#- Column names prefix_1 .. prefix_n as a list. -#}
{% macro numbered_columns(prefix, count) -%}
    {%- set columns = [] -%}
    {%- for i in range(1, count + 1) -%}
        {%- do columns.append(prefix ~ '_' ~ i) -%}
    {%- endfor -%}
    {{ return(columns) }}
{%- endmacro %}

{#-
  Joins dim_member twice: `member_version` is the version valid on the given date, and
  `member_current` is the latest version, used when no version covers the date (for
  example a missing service date). Select member_key with member_version_key().
-#}
{% macro join_member_versions(fact_alias, date_column) -%}
    left join {{ ref('dim_member') }} as member_version
        on member_version.member_id = {{ fact_alias }}.member_id
        and member_version.synpuf_sample = {{ fact_alias }}.synpuf_sample
        and {{ date_column }} between member_version.valid_from and member_version.valid_to
    left join {{ ref('dim_member') }} as member_current
        on member_current.member_id = {{ fact_alias }}.member_id
        and member_current.synpuf_sample = {{ fact_alias }}.synpuf_sample
        and member_current.is_current
{%- endmacro %}

{% macro member_version_key() -%}
    coalesce(member_version.member_key, member_current.member_key)
{%- endmacro %}

{#- Non-null values of several columns stacked into one column. Duplicates are kept. -#}
{% macro stack_columns(relation, columns, alias, extra_columns={}) -%}
    {%- for column in columns %}
    select
        {{ column }} as {{ alias }}
        {%- for name, value in extra_columns.items() %},
        {{ value }} as {{ name }}
        {%- endfor %}
    from {{ relation }}
    where {{ column }} is not null
    {% if not loop.last %}union all{% endif %}
    {%- endfor %}
{%- endmacro %}
