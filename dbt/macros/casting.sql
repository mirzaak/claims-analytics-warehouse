{#-
  Casting helpers for raw SynPUF text columns. Blank text becomes null.
  Warehouse-specific SQL lives in dispatched macros, so models stay portable
  between BigQuery and Snowflake.
-#}

{% macro blank_to_null(column) -%}
    nullif(trim({{ column }}), '')
{%- endmacro %}

{% macro clean_code(column) -%}
    nullif(upper(trim({{ column }})), '')
{%- endmacro %}

{% macro to_amount(column) -%}
    {{ dbt.safe_cast(blank_to_null(column), dbt.type_numeric()) }}
{%- endmacro %}

{% macro to_integer(column) -%}
    {{ dbt.safe_cast(blank_to_null(column), dbt.type_int()) }}
{%- endmacro %}

{% macro parse_yyyymmdd(column) -%}
    {{ return(adapter.dispatch('parse_yyyymmdd')(column)) }}
{%- endmacro %}

{% macro bigquery__parse_yyyymmdd(column) -%}
    safe.parse_date('%Y%m%d', {{ blank_to_null(column) }})
{%- endmacro %}

{% macro default__parse_yyyymmdd(column) -%}
    try_to_date({{ blank_to_null(column) }}, 'YYYYMMDD')
{%- endmacro %}

{#- SynPUF flags use 1 for yes and 2 for no. -#}
{% macro one_two_flag(column) -%}
    case trim({{ column }}) when '1' then true when '2' then false end
{%- endmacro %}

{#- Cast by type name, used by the columns_castable test. -#}
{% macro cast_as(column, to) -%}
    {%- if to == 'date' -%}
        {{ parse_yyyymmdd(column) }}
    {%- elif to == 'integer' -%}
        {{ to_integer(column) }}
    {%- elif to == 'amount' -%}
        {{ to_amount(column) }}
    {%- else -%}
        {{ exceptions.raise_compiler_error("cast_as: unknown type '" ~ to ~ "'") }}
    {%- endif -%}
{%- endmacro %}
