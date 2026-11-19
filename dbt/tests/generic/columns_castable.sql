{#-
  Fails for every non-blank value that cannot be cast to `to` (date, integer or amount).
  Columns are chosen by a regular expression, so one test covers repeated columns
  such as LINE_NCH_PMT_AMT_1 to LINE_NCH_PMT_AMT_13 in a single scan.
-#}
{% test columns_castable(model, pattern, to) %}

{%- set columns = [] -%}
{%- if execute -%}
    {%- for column in adapter.get_columns_in_relation(model) if modules.re.search(pattern, column.name) -%}
        {%- do columns.append(column.name) -%}
    {%- endfor -%}
    {%- if columns | length == 0 -%}
        {{ exceptions.raise_compiler_error("columns_castable: no column in " ~ model ~ " matches " ~ pattern) }}
    {%- endif -%}
{%- endif -%}

{%- for column in columns %}
select
    '{{ column }}' as column_name,
    {{ column }} as invalid_value
from {{ model }}
where {{ blank_to_null(column) }} is not null
    and {{ cast_as(column, to) }} is null
{% if not loop.last %}union all{% endif %}
{%- endfor %}

{%- if columns | length == 0 %}
select 'none' as column_name, 'none' as invalid_value
from {{ model }}
where 1 = 0
{%- endif %}

{% endtest %}
